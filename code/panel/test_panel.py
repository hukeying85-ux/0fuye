import hashlib
import http.client
import json
import pathlib
import re
import tempfile
import threading
import unittest

from server import Store, make_server, receipt_status


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.results = self.root / "results"
        p = self.results / "sample/status"
        p.mkdir(parents=True)
        (p / "hub_sync_receipt.json").write_text(
            json.dumps(
                {
                    "repo": "0fuye",
                    "branch": "arena/89735ee7-0fuye",
                    "tasks_all_ok": True,
                    "tasks_executed": [{"step": "check", "exit_code": 0, "stdout": "SECRET_NOT_TO_EXPOSE"}],
                }
            ),
            encoding="utf-8",
        )
        self.s = Store(self.root / "data", self.results, self.root / "hub")

    def tearDown(self):
        self.tmp.cleanup()

    def test_receipt_is_not_running(self):
        self.assertEqual(receipt_status({"tasks_all_ok": True}), "completed")
        self.assertEqual(receipt_status({}), "no_receipt")

    def test_discovers_and_hides_raw_output(self):
        data = self.s.snapshot()
        self.assertEqual(len(data["sessions"]), 1)
        self.assertNotIn("SECRET_NOT_TO_EXPOSE", json.dumps(data))
        self.assertEqual(data["sessions"][0]["prompt_source"], "unrecorded")
        self.assertEqual(data["version"], "2.8.0")
        self.assertEqual(data["repo_info"]["repo"], "0fuye")
        self.assertTrue(data["repo_info"]["private"])
        # Ensure zero school-name strings leak anywhere in state snapshot
        full_dump = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("鲁东", full_dump)
        self.assertNotIn("ludong", full_dump.lower())

    def test_catalog_connectors_and_three_account_gh(self):
        data = self.s.snapshot()
        pkg_ids = {x["id"] for x in data["software_catalog"]["scan"]["items"]}
        self.assertIn("pymol-open-source", pkg_ids)
        self.assertIn("lark-formatter", pkg_ids)
        self.assertIn("gh-cli", pkg_ids)
        conn_slugs = {c["slug"] for c in data["connectors"]}
        self.assertEqual(
            conn_slugs,
            {
                "github",
                "google_drive",
                "google_docs",
                "google_sheets",
                "google_slides",
                "notion",
                "gmail",
                "linear",
                "google_calendar",
                "dropbox",
            },
        )
        gh_logins = {a["login"] for a in data["gh_auth"]["multi_accounts"]}
        self.assertEqual(gh_logins, {"mqgg5630-cyber", "shaohuawen03-cyber", "hukeying85-ux"})
        self.assertTrue(data["gh_auth"]["default_invariant_ok"])

    def test_personal_hub_redacts_pii(self):
        data = self.s.snapshot()
        raw_ph = json.dumps(data["personal_hub"], ensure_ascii=False)
        # Ensure no unmasked 18-digit mainland ID card or 11-digit mobile number leaks
        self.assertIsNone(re.search(r"\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b", raw_ph))
        self.assertIsNone(re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", raw_ph))
        self.assertGreaterEqual(len(data["personal_hub"]["drive_folders"]), 6)
        tracks = data["personal_hub"]["career_tracks"]
        self.assertGreaterEqual(len(tracks), 3)
        # Verify owner track is primary, school name removed, friend data strictly isolated, and love_hub populated
        self.assertEqual(tracks[0]["scope"], "owner")
        self.assertNotIn("鲁东", tracks[0]["person"])
        self.assertTrue(any(t.get("scope") == "friend_isolated" for t in tracks))
        love_cols = data["personal_hub"]["love_hub"]["collections"]
        self.assertEqual(len(love_cols), 4)
        self.assertEqual(sum(len(c["items"]) for c in love_cols), 18)
        self.assertTrue(all(len(f.get("concrete_items", [])) >= 1 for f in data["personal_hub"]["drive_folders"]))

    def test_prompt_persists_and_unknown_id_rejected(self):
        self.s.record({"id": "sample", "title": "测试", "prompt": "记录任务结果"})
        self.assertEqual(self.s.sessions()[0]["prompt"], "记录任务结果")
        with self.assertRaises(ValueError):
            self.s.record({"id": "../escape", "prompt": "x"})

    def test_protects_hub_and_arbitrary_command(self):
        for name in ["git-sync-hub", "arena-desk-panel", "x;shutdown", "../something"]:
            with self.assertRaises(ValueError):
                self.s.control(name, "stop")

    def test_secret_block(self):
        with self.assertRaises(ValueError):
            self.s.record({"id": "sample", "title": "x", "prompt": "token=private-test-secret"})

    def test_corrupt_json(self):
        (self.results / "sample/status/hub_sync_receipt.json").write_text("{bad", encoding="utf-8")
        self.assertEqual(self.s.sessions()[0]["status"], "no_receipt")

    def test_manifest(self):
        (self.results / "sample/status/session_manifest.json").write_text('{"user_prompt":"hello"}', encoding="utf-8")
        self.assertEqual(self.s.sessions()[0]["prompt_source"], "manifest")

    def test_http_v21_endpoints_thesis_coord_media_and_security(self):
        sample_mp4 = self.root / "ocean.mp4"
        sample_mp4.write_bytes(b"0123456789ABCDEF" * 64)
        (self.root / "data/custom-media.json").write_text(json.dumps([str(sample_mp4)]), encoding="utf-8")
        self.s.ops.refresh_media_index()
        mid = hashlib.sha1(str(sample_mp4).encode("utf-8")).hexdigest()[:16]

        server = make_server("127.0.0.1", 0, self.s)
        threading.Thread(target=server.serve_forever, daemon=True).start()

        def req(path, method="GET", headers=None, body=None):
            c = http.client.HTTPConnection("127.0.0.1", server.server_port)
            c.request(method, path, body=body, headers=headers or {})
            r = c.getresponse()
            data = r.read()
            hdrs = dict(r.getheaders())
            c.close()
            return r.status, data, hdrs

        try:
            st, body, _ = req("/api/bootstrap")
            self.assertEqual(st, 200)
            boot_j = json.loads(body)
            self.assertEqual(boot_j["version"], "2.8.0")
            csrf = boot_j["csrf"]
            st_wt, wt_b, _ = req(
                "/api/watcher/toggle",
                method="POST",
                headers={"Content-Type": "application/json", "X-CSRF-Token": csrf, "Origin": f"http://127.0.0.1:{server.server_port}"},
                body=b'{"target":"S3","enabled":false}',
            )
            self.assertEqual(st_wt, 200)
            self.assertFalse(json.loads(wt_b)["watcher_state"]["sessions"]["S3"]["enabled"])
            st_tc, tc_b, _ = req(
                "/api/tri-chat/send",
                method="POST",
                headers={"Content-Type": "application/json", "X-CSRF-Token": csrf, "Origin": f"http://127.0.0.1:{server.server_port}"},
                body="{\"slot\":\"S3\",\"message\":\"开启值守\"}".encode("utf-8"),
            )
            self.assertEqual(st_tc, 200)
            self.assertTrue(json.loads(tc_b)["watcher"]["sessions"]["S3"]["enabled"])

            # v2.6 Android Richer-Install PWA, Maskable Icon, Screenshots, ISO QR SVG & MP4 Range Streaming
            self.assertEqual(req("/mobile")[0], 200)
            self.assertEqual(req("/mobile/mobile.js")[0], 200)
            self.assertEqual(req("/mobile/manifest.webmanifest")[0], 200)
            self.assertEqual(req("/mobile/sw.js")[0], 200)
            self.assertEqual(req("/mobile/icon-192.png")[0], 200)
            self.assertEqual(req("/mobile/icon-512.png")[0], 200)
            self.assertEqual(req("/mobile/icon-maskable-512.png")[0], 200)
            self.assertEqual(req("/mobile/screen-narrow.png")[0], 200)
            self.assertEqual(req("/mobile/screen-wide.png")[0], 200)
            st_qr, qr_b, _ = req("/api/mobile/qr")
            self.assertEqual(st_qr, 200)
            qr_json = json.loads(qr_b)
            self.assertIn("<svg", qr_json["lan_qr_svg"])
            self.assertIn("<svg", qr_json["ntfy_qr_svg"])
            st_bv, bv_b, bv_h = req("/assets/dsh-boot.mp4", headers={"Range": "bytes=0-31"})
            self.assertEqual(st_bv, 206)
            self.assertEqual(len(bv_b), 32)
            self.assertIn("bytes 0-31/", bv_h.get("Content-Range", ""))
            st_bgv, bgv_b, _ = req("/assets/dsh-bg.mp4", headers={"Range": "bytes=0-31"})
            self.assertEqual(st_bgv, 206)
            self.assertEqual(len(bgv_b), 32)

            st_mob, mob_bytes, _ = req("/api/mobile/state")
            self.assertEqual(st_mob, 200)
            mob_json = json.loads(mob_bytes)
            self.assertIn("beacon", mob_json)
            self.assertEqual(len(mob_json["war_room"]["roster"]), 5)
            self.assertGreaterEqual(len(mob_json["quota"]["pools"]), 4)
            st_amp, amp_bytes, _ = req("/api/quota/amp-calc?seq=GIGKFLHSAKKFGKAFVGEIMNS")
            self.assertEqual(st_amp, 200)
            self.assertGreater(json.loads(amp_bytes)["net_charge_ph74"], 2.0)

            # Custom icon & assets
            st_ico, ico_bytes, _ = req("/favicon.ico")
            self.assertEqual(st_ico, 200)
            self.assertEqual(ico_bytes[:4], b"\x00\x00\x01\x00")
            self.assertEqual(req("/assets/icon.svg")[0], 200)
            self.assertEqual(req("/assets/whale.svg")[0], 200)
            self.assertEqual(req("/assets/../../server.py")[0], 404)

            # Cross-PC Bootstrap Script Generator
            st_ps, ps_bytes, _ = req("/api/script?os=windows&mode=install&pymol=1&base=1&drive=D:")
            self.assertEqual(st_ps, 200)
            self.assertIn(b"$InstallPyMOL = $true", ps_bytes)
            st_sh, sh_bytes, _ = req("/api/script?os=linux&mode=install&pymol=1")
            self.assertEqual(st_sh, 200)
            self.assertIn(b"--install-pymol", sh_bytes)

            # HTTP 206 Range media streaming
            st_rng, rng_bytes, rng_hdrs = req(f"/api/media/{mid}", headers={"Range": "bytes=4-19"})
            self.assertEqual(st_rng, 206)
            self.assertEqual(len(rng_bytes), 16)
            self.assertIn("bytes 4-19/", rng_hdrs.get("Content-Range", ""))

            # Host & CSRF security
            self.assertEqual(req("/api/state", headers={"Host": "evil.example"})[0], 403)
            self.assertEqual(req("/../../server.py")[0], 404)
            self.assertEqual(req("/api/control", "POST", body="{}")[0], 403)

            headers = {
                "Origin": f"http://127.0.0.1:{server.server_port}",
                "X-CSRF-Token": server.csrf,
                "Content-Type": "application/json",
            }
            self.assertEqual(
                req("/api/control", "POST", headers, json.dumps({"name": "git-sync-hub", "action": "stop"}))[0],
                400,
            )
            self.assertEqual(
                req("/api/session", "POST", headers, json.dumps({"id": "sample", "title": "ok", "prompt": "user task"}))[0],
                200,
            )
            st_app, app_bytes, _ = req(
                "/api/appearance",
                "POST",
                headers,
                json.dumps({"theme": "amber-forge", "surface_opacity": 0.72, "glass_blur": 22}),
            )
            self.assertEqual(st_app, 200)
            self.assertEqual(json.loads(app_bytes)["appearance"]["theme"], "amber-forge")

            # Multi-session coordination: lease contention & protected resources
            st_l1, b_l1, _ = req(
                "/api/coord/lease",
                "POST",
                headers,
                json.dumps({"resource": "git-sync-hub", "holder": "peer-session"}),
            )
            self.assertEqual(st_l1, 400)  # git-sync-hub is protected read-only

            st_l2, _, _ = req(
                "/api/coord/lease",
                "POST",
                headers,
                json.dumps({"resource": "thesis-formatter", "holder": "leanrea-4d729933-leanrea", "ttl_sec": 60}),
            )
            self.assertEqual(st_l2, 200)

            # While peer holds thesis-formatter lease, /api/thesis/format must refuse conflicting write
            st_busy, busy_bytes, _ = req(
                "/api/thesis/format",
                "POST",
                headers,
                json.dumps({"use_sample": True}),
            )
            self.assertEqual(st_busy, 400)
            self.assertIn("leanrea-4d729933-leanrea", json.loads(busy_bytes)["error"])

            # Release peer lease, then run persistent thesis format + artifact downloads
            self.assertEqual(
                req(
                    "/api/coord/release",
                    "POST",
                    headers,
                    json.dumps({"resource": "thesis-formatter", "holder": "leanrea-4d729933-leanrea"}),
                )[0],
                200,
            )
            st_fmt, fmt_bytes, _ = req(
                "/api/thesis/format",
                "POST",
                headers,
                json.dumps({"use_sample": True, "profile_id": "academic_master_2026"}),
            )
            self.assertEqual(st_fmt, 200)
            fmt_res = json.loads(fmt_bytes)
            self.assertTrue(fmt_res["ok"])
            jid = fmt_res["job"]["job_id"]
            self.assertGreater(fmt_res["job"]["total_changes"], 50)

            st_dl, dl_bytes, _ = req(f"/api/thesis/download/{jid}/final")
            self.assertEqual(st_dl, 200)
            self.assertEqual(dl_bytes[:2], b"PK")  # valid .docx zip header

            # Post coordination handoff note & test v2.2 Mobile Quick-Cmd + Human Gate
            self.assertEqual(
                req("/api/coord/note", "POST", headers, json.dumps({"summary": "v2.2 unit test handoff ok"}))[0],
                200,
            )
            st_qc1, qc1_b, _ = req("/api/mobile/quick-cmd", "POST", headers, json.dumps({"cmd_id": "md_speed_check"}))
            self.assertEqual(st_qc1, 200)
            self.assertFalse(json.loads(qc1_b)["gated"])

            st_qc2, qc2_b, _ = req("/api/mobile/quick-cmd", "POST", headers, json.dumps({"cmd_id": "scancel_stuck_job"}))
            self.assertEqual(st_qc2, 200)
            qc2_res = json.loads(qc2_b)
            self.assertTrue(qc2_res["gated"])
            gid = qc2_res["gate"]["gate_id"]
            self.assertEqual(
                req("/api/war-room/gate", "POST", headers, json.dumps({"gate_id": gid, "decision": "reject"}))[0],
                200,
            )

            # v2.3 Tri-Account Federation, Martini CG-MD Generator & Cross-Session Dispatcher
            st_fed, fed_b, _ = req("/api/federation")
            self.assertEqual(st_fed, 200)
            fed_json = json.loads(fed_b)
            self.assertEqual(len(fed_json["tri_node_matrix"]), 3)

            st_cg, cg_b, _ = req("/api/federation/cgmd?name=AMP_Top1&us=2.5&membrane=bacterial_inner")
            self.assertEqual(st_cg, 200)
            cg_json = json.loads(cg_b)
            self.assertTrue(cg_json["ok"])
            self.assertIn("martinize2", cg_json["bundle"]["runner_script"])
            self.assertIn("POPE:3", cg_json["bundle"]["runner_script"])
            self.assertEqual(cg_json["bundle"]["nsteps"], 125_000_000)

            st_dp, dp_b, _ = req(
                "/api/federation/dispatch",
                "POST",
                headers,
                json.dumps(
                    {
                        "target_node": "desktop_hukeying",
                        "title": "Martini 3 CG-MD 2us Screening",
                        "objective": "Run bacterial membrane screening and notify mobile",
                        "peptide_seq": "GIGKFLHSAKKFGKAFVGEIMNS",
                    }
                ),
            )
            self.assertEqual(st_dp, 200)
            dp_res = json.loads(dp_b)
            self.assertTrue(dp_res["ok"])
            self.assertEqual(dp_res["dispatch"]["target_gh_account"], "hukeying85-ux")
            self.assertIn("node_agent.py", dp_res["dispatch"]["arena_prompt"])

            # v2.4 Douyin / Xiaohongshu / WeChat MP + Video Downloader + Computer Use Hub
            st_mc, mc_b, _ = req("/api/media-cua")
            self.assertEqual(st_mc, 200)
            mc_json = json.loads(mc_b)
            self.assertEqual(len(mc_json["platforms"]), 4)
            self.assertEqual(len(mc_json["cua_projects"]), 4)

            import urllib.parse

            dy_share = urllib.parse.quote("7.43 复制打开抖音 https://v.douyin.com/iYTest99/ 看看作品")
            st_mp1, mp1_b, _ = req(f"/api/media-cua/parse?q={dy_share}")
            self.assertEqual(st_mp1, 200)
            self.assertEqual(json.loads(mp1_b)["platform_id"], "douyin")
            self.assertEqual(json.loads(mp1_b)["clean_url"], "https://v.douyin.com/iYTest99/")

            xhs_share = urllib.parse.quote("小红书笔记分享 http://xhslink.com/a/AbCdEf，打开App查看")
            st_mp2, mp2_b, _ = req(f"/api/media-cua/parse?q={xhs_share}")
            self.assertEqual(st_mp2, 200)
            self.assertEqual(json.loads(mp2_b)["platform_id"], "xiaohongshu")

            import media_cua_hub

            wx_md = media_cua_hub.html_to_clean_markdown_snippet(
                '<meta property="og:title" content="抗菌肽与肠道菌群综述">'
                '<span id="js_name">生信前沿</span>'
                '<div id="js_content"><p>第一段正文</p><img data-src="https://mmbiz.qpic.cn/test1.jpg"/></div><script></script>'
            )
            self.assertEqual(wx_md["title"], "抗菌肽与肠道菌群综述")
            self.assertEqual(wx_md["image_count"], 1)
            self.assertIn("第一段正文", wx_md["markdown"])

            # Demo read-only protection + stateless sample-run in demo mode
            self.s.demo = True
            self.assertEqual(
                req("/api/session", "POST", headers, json.dumps({"id": "sample", "title": "bad", "prompt": "ignored"}))[0],
                403,
            )
            st_srun, srun_bytes, _ = req("/api/thesis/sample-run")
            self.assertEqual(st_srun, 200)
            self.assertTrue(json.loads(srun_bytes)["ok"])
            st_sdl, sdl_bytes, _ = req("/api/thesis/sample-download/final")
            self.assertEqual(st_sdl, 200)
            self.assertEqual(sdl_bytes[:2], b"PK")
            self.assertEqual(req("/api/thesis/sample-download/compare")[0], 200)
            self.assertEqual(req("/api/thesis/sample-download/report_md")[0], 200)
            self.assertEqual(req("/api/thesis/sample-download/csl")[0], 200)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
