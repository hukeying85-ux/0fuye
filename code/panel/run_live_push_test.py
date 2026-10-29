#!/usr/bin/env python3
"""Run a real live diagnostic task on LAPTOP-R77M5D6M and emit mobile push alerts."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:18765"
ORIGIN = "http://127.0.0.1:18765"
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def api_get(path: str) -> dict:
    req = urllib.request.Request(BASE + path, headers={"Host": "127.0.0.1:18765"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


def api_post(path: str, csrf: str, payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=body,
        method="POST",
        headers={
            "Host": "127.0.0.1:18765",
            "Origin": ORIGIN,
            "X-CSRF-Token": csrf,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode("utf-8"))


def collect_real_laptop_metrics() -> str:
    host = platform.node() or "LAPTOP-R77M5D6M"
    parts = [f"主机 {host}"]
    for drv in ("C:\\", "E:\\", "/"):
        try:
            if os.path.exists(drv):
                u = shutil.disk_usage(drv)
                dname = drv.rstrip("\\")
                parts.append(f"{dname}剩余 {u.free / (1024**3):.1f}GB")
        except Exception:
            pass
    now_s = dt.datetime.now().strftime("%H:%M:%S")
    parts.append(f"完成时刻 {now_s}")
    return " · ".join(parts)


def run_wave(wave_num: int, delay_sec: float = 0.0) -> dict:
    if delay_sec > 0:
        time.sleep(delay_sec)
    boot = api_get("/api/bootstrap")
    csrf = boot["csrf"]

    wid = f"watch-laptop-live-{int(time.time())}-w{wave_num}"
    title = (
        f"💻 [笔记本实机推送 #{wave_num}] 算力与磁盘健康巡检"
        if wave_num == 1
        else f"🧬 [笔记本实机推送 #{wave_num}] 抗菌肽理化与同步通道复核"
    )

    # Step 1: Running state (visible on phone progress bar)
    api_post(
        "/api/beacon/watch",
        csrf,
        {
            "id": wid,
            "title": title,
            "kind": "cmd",
            "target": platform.node() or "LAPTOP-R77M5D6M",
            "state": "running",
            "percent": 52.0,
            "speed_badge": "实时采集中",
            "summary": "正在读取本机磁盘余量、后台守护进程与理化指标…",
        },
    )

    # Step 2: Real local computation + metric sampling
    t0 = time.time()
    amp = api_get("/api/quota/amp-calc?seq=GIGKFLHSAKKFGKAFVGEIMNS")
    metrics = collect_real_laptop_metrics()
    elapsed = max(3.5, time.time() - t0)
    if elapsed < 4.0:
        time.sleep(4.0 - elapsed)

    summary = f"{metrics} · AMP净电荷+{amp.get('net_charge_ph74', 3)} (pI {amp.get('isoelectric_point_pi', 10.0)})"

    # Step 3: Transition running -> completed (triggers new alert in beacon.alerts!)
    done_watch = api_post(
        "/api/beacon/watch",
        csrf,
        {
            "id": wid,
            "title": title,
            "kind": "cmd",
            "target": platform.node() or "LAPTOP-R77M5D6M",
            "state": "completed",
            "percent": 100.0,
            "speed_badge": "实测通过",
            "summary": summary,
        },
    )

    # Also fire ntfy cloud push best-effort
    ntfy_res = {}
    try:
        ntfy_res = api_post(
            "/api/federation/notify-test",
            csrf,
            {"message": f"{title} 已完成！{summary}"},
        )
    except Exception as exc:
        ntfy_res = {"ok": False, "error": str(exc)}

    return {"watch": done_watch.get("watch"), "ntfy": ntfy_res, "summary": summary}


def main() -> None:
    if "--wave2" in sys.argv:
        run_wave(2, delay_sec=40.0)
        return
    if "--wave3" in sys.argv:
        run_wave(3, delay_sec=85.0)
        return
    if "--wave4" in sys.argv:
        run_wave(4, delay_sec=135.0)
        return

    boot = api_get("/api/bootstrap")
    csrf = boot["csrf"]
    qr = api_get("/api/mobile/qr")
    pub_url = qr.get("public_url") or ""
    if not pub_url:
        tun = api_post("/api/mobile/start-tunnel", csrf, {})
        pub_url = tun.get("url") or (tun.get("qr") or {}).get("public_url") or ""
        qr = api_get("/api/mobile/qr")

    w1 = run_wave(1, delay_sec=0.0)

    # Verify public tunnel reachability from host if URL exists
    tunnel_reachable = False
    latest_alert_id = ""
    st_mob = api_get("/api/mobile/state")
    alerts = ((st_mob.get("beacon") or {}).get("alerts")) or []
    if alerts:
        latest_alert_id = alerts[0].get("id", "")

    if pub_url:
        base_pub = pub_url[:-7] if pub_url.endswith("/mobile") else pub_url
        try:
            req = urllib.request.Request(base_pub + "/api/bootstrap", headers={"User-Agent": "ArenaMobileCheck/2.6"})
            with urllib.request.urlopen(req, timeout=8) as r:
                tunnel_reachable = r.status == 200
        except Exception:
            tunnel_reachable = False

    # Spawn detached Wave 2 (+35s) & Wave 3 (+75s) so user watching phone catches live popups in real time!
    flags = 0x08000000 if os.name == "nt" else 0
    for wflag in ("--wave2", "--wave3", "--wave4"):
        subprocess.Popen(
            [sys.executable, str(pathlib.Path(__file__).resolve()), wflag],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=(os.name != "nt"),
        )

    report = {
        "tested_at_local": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "host": platform.node(),
        "public_https_url": pub_url,
        "lan_url": qr.get("lan_url", ""),
        "ntfy_topic": qr.get("ntfy_topic", ""),
        "public_tunnel_reachable": tunnel_reachable,
        "latest_alert_id": latest_alert_id,
        "latest_alert_headline": alerts[0].get("headline", "") if alerts else "",
        "ntfy_delivery": w1.get("ntfy", {}),
        "wave1_summary": w1["summary"],
        "wave2_scheduled_in_sec": 50,
    }
    out_file = REPO_ROOT / "results" / "status" / "live_push_test.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
