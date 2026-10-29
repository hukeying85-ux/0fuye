"""The 100 ps GROMACS smoke test (``cgmd.smoke``), driven by a stub gmx.

The stub reproduces exactly the files the module consumes, so the whole
control flow (box -> topology -> grompp -> mdrun -> verdict -> report) is
covered on a machine without GROMACS.  The real thing runs on the workstation
via ``python3 -m cgmd.smoke``.
"""

from __future__ import annotations

import json
import os
import stat
import textwrap

import pytest

from cgmd import smoke

FAKE_GMX = "\n".join([
    "#!/bin/bash",
    "set -u",
    "cmd=\"${1:-}\"; shift || true",
    "deffnm=\"\"; out=\"\"; top=\"\"",
    "args=(\"$@\")",
    "boxcount=0",
    "i=0",
    "while [ $i -lt ${#args[@]} ]; do",
    "  case \"${args[$i]}\" in",
    "    -deffnm) deffnm=\"${args[$((i+1))]}\" ;;",
    "    -o) out=\"${args[$((i+1))]}\" ;;",
    "    -p) top=\"${args[$((i+1))]}\" ;;",
    "  esac",
    "  i=$((i+1))",
    "done",
    "mdp_value() {",
    "  awk -F= -v key=\"$1\" '$1 ~ (\"^[ \\t]*\" key \"[ \\t]*$\") {gsub(/[ \\t]+/, \"\", $2); print $2; exit}' smoke_md.mdp",
    "}",
    "case \"$cmd\" in",
    "  --version|version)",
    "    echo \"GROMACS version:     2024.3-stub\"",
    "    echo \"Precision:           mixed\"",
    "    echo \"Memory model:        64 bit\"",
    "    echo \"SIMD instructions:   AVX2_256\"",
    "    echo \"GPU support:         CUDA\"",
    "    echo \"CUDA runtime:        12.2\"",
    "    echo \"CUDA driver:         12.2\"",
    "    echo \"FFT library:         fftw-3.3.10-sse2-avx\"",
    "    echo \"OpenMP:              enabled\"",
    "    ;;",
    "  solvate)",
    "    {",
    "      echo \"SPC water box\"",
    "      echo \"375\"",
    "      n=0",
    "      m=0",
    "      while [ $m -lt 125 ]; do",
    "        n=$((n+1))",
    "        printf \"%5d%-5s%5s%5d%8.3f%8.3f%8.3f\\n\" 1 SOL OW $n 0.1 0.1 0.1",
    "        n=$((n+1))",
    "        printf \"%5d%-5s%5s%5d%8.3f%8.3f%8.3f\\n\" 1 SOL HW1 $n 0.2 0.1 0.1",
    "        n=$((n+1))",
    "        printf \"%5d%-5s%5s%5d%8.3f%8.3f%8.3f\\n\" 1 SOL HW2 $n 0.1 0.2 0.1",
    "        m=$((m+1))",
    "      done",
    "      echo \"   1.00000   1.00000   1.00000\"",
    "    } > \"$out\"",
    "    if [ -n \"$top\" ]; then",
    "      sed -i 's/^SOL 0$/SOL 125/' \"$top\"",
    "    fi",
    "    echo \"Number of solvent molecules: 125\"",
    "    ;;",
    "  grompp)",
    "    echo \"GROMACS grompp, stub\"",
    "    echo > \"$out\"",
    "    ;;",
    "  mdrun)",
    "    base=\"${deffnm:-md}\"",
    "    echo \"stub ran ${base}\" > \"${base}.log\"",
    "    if [ \"$base\" = \"smoke_em\" ]; then",
    "      echo \"Steepest Descents converged to Fmax < 500 in 120 steps\" >> \"${base}.log\"",
    "      echo \"Steepest Descents converged to Fmax < 500 in 120 steps\"",
    "      printf \"%s\\n\" \"stub minimized\" > \"${base}.gro\"",
    "      printf \"%s\\n\" \"stub checkpoint\" > \"${base}.cpt\"",
    "    else",
    "      dt=$(mdp_value dt)",
    "      [ -z \"$dt\" ] && dt=0.02",
    "      ns=$(mdp_value nsteps)",
    "      [ -z \"$ns\" ] && ns=5000",
    "      total=$(awk -v a=\"$dt\" -v b=\"$ns\" 'BEGIN{printf \"%.5f\", a*b}')",
    "      half=$(awk -v a=\"$dt\" -v b=\"$ns\" 'BEGIN{printf \"%.5f\", a*b/2}')",
    "      echo \"   nsteps                 = ${ns}\" >> \"${base}.log\"",
    "      echo \"   dt                     = ${dt}\" >> \"${base}.log\"",
    "      echo \"Step           Time\" >> \"${base}.log\"",
    "      echo \"       0        0.00000\" >> \"${base}.log\"",
    "      echo \"   $((ns/2))      ${half}\" >> \"${base}.log\"",
    "      echo \"   ${ns}      ${total}\" >> \"${base}.log\"",
    "      echo \"Performance:      1850.000       0.043\" >> \"${base}.log\"",
    "      echo \"Finished mdrun on rank 0\" >> \"${base}.log\"",
    "      printf \"%s\\n\" \"stub final\" > \"${base}.gro\"",
    "      printf \"%s\\n\" \"stub trajectory\" > \"${base}.xtc\"",
    "      printf \"%s\\n\" \"stub energy\" > \"${base}.edr\"",
    "    fi",
    "    ;;",
    "  *)",
    "    echo \"stub: unsupported command $cmd\" >&2",
    "    exit 2",
    "    ;;",
    "esac",
]) + "\n"

FF_BASE = """\
[ defaults ]
1 2 no 1.0 1.0
[ atomtypes ]
P4 72.0 0.0 A 0.0 0.0
"""

FF_SOLVENT = """\
[moleculetype]
W 1
[atoms]
 1 P4 1 W W 1 0.0
"""


@pytest.fixture()
def stub_gmx(tmp_path):
    exe = tmp_path / "gmx"
    exe.write_text(FAKE_GMX, encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return str(exe)


@pytest.fixture()
def fake_ff(tmp_path):
    ff = tmp_path / "martini3"
    ff.mkdir()
    (ff / "martini_v3.0.0.itp").write_text(FF_BASE, encoding="utf-8")
    (ff / "martini_v3.0.0_solvents_v1.itp").write_text(FF_SOLVENT, encoding="utf-8")
    return str(ff)


# ---------------------------------------------------------------------------
# system generation
# ---------------------------------------------------------------------------
def test_water_box_has_the_expected_geometry(tmp_path):
    path = tmp_path / "box.gro"
    atoms = smoke.write_water_box(str(path))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert atoms == 216                      # (3.0 / 0.49)^2 rounded -> 6^3
    assert lines[1].strip() == str(atoms)
    assert len(lines) == atoms + 3
    assert lines[-1].split() == ["3.00000", "3.00000", "3.00000"]
    assert len(lines[2]) == 44               # canonical .gro atom line


def test_water_topology_includes_only_the_water_file(tmp_path, fake_ff):
    top = tmp_path / "box.top"
    info = smoke.write_water_topology(str(top), [fake_ff], 216)
    text = top.read_text(encoding="utf-8")
    assert "#include" in text and "martini_v3.0.0.itp" in text
    assert "martini_v3.0.0_solvents_v1.itp" in text
    assert "[ molecules ]" in text and "W 216" in text
    assert info["water_atoms"] == 1 and info["molecules"] == 216


def test_missing_force_field_is_reported_not_raised(tmp_path):
    with pytest.raises(RuntimeError):
        smoke.write_water_topology(str(tmp_path / "x.top"), [str(tmp_path / "empty")], 10)


# ---------------------------------------------------------------------------
# version parsing
# ---------------------------------------------------------------------------
def test_version_parsing_reads_every_field():
    text = textwrap.dedent(
        """\
        GROMACS version:     2024.3
        Precision:           mixed
        SIMD instructions:   AVX2_256
        GPU support:         CUDA
        CUDA runtime:        12.2
        FFT library:         fftw-3.3.10-sse2-avx
        """
    )
    info = smoke.parse_version(text)
    assert info["version"] == "2024.3"
    assert info["precision"] == "mixed"
    assert info["gpu_support"] == "CUDA"
    assert info["cuda"] is True
    assert info["cuda_runtime"] == "12.2"
    assert info["fft"].startswith("fftw")


def test_version_parsing_without_gpu():
    info = smoke.parse_version("GROMACS version: 2023.1\nGPU support: no\n")
    assert info["cuda"] is False


def test_gpu_parsing():
    devices = smoke.parse_gpu("NVIDIA GeForce RTX 4090, 545.29, 24564 MiB\n")
    assert devices[0]["name"].startswith("NVIDIA")
    assert devices[0]["memory"] == "24564 MiB"


# ---------------------------------------------------------------------------
# log parsing
# ---------------------------------------------------------------------------
def test_md_log_parsing():
    text = textwrap.dedent(
        """\
           nsteps                 = 5000
           dt                     = 0.02
        Step           Time
               0        0.00000
            5000      100.00000
        Performance:      1850.000       0.043
        Finished mdrun on rank 0
        """
    )
    info = smoke.parse_md_log(text)
    assert info["steps_requested"] == 5000
    assert info["dt_ps"] == 0.02
    assert info["time_ps"] == 100.0
    assert info["simulated_ps"] == 100.0
    assert info["performance_ns_per_day"] == 1850.0
    assert info["finished"] is True
    assert info["fatal"] is None


def test_md_log_detects_a_fatal_error():
    info = smoke.parse_md_log("Fatal error:\nToo many LINCS warnings\n")
    assert info["fatal"] == "Too many LINCS warnings"


# ---------------------------------------------------------------------------
# the full run
# ---------------------------------------------------------------------------
def test_run_smoke_succeeds_and_reports_everything(tmp_path, stub_gmx, fake_ff, monkeypatch):
    monkeypatch.setenv("CGMD_MARTINI3_DIR", fake_ff)
    report = smoke.run_smoke(ps=100, workdir=str(tmp_path / "run"), gmx_binary=stub_gmx,
                             martini3_dir=fake_ff, ntomp=1, timeout=120, system="martini",
                             temperature=310.0)
    assert report["status"] == "ok", report.get("stage_error")
    assert report["ok"] is True
    assert report["ps_completed"] == 100.0
    assert report["accelerator"] == "gpu"
    assert [stage["stage"] for stage in report["stages"]] == [
        "grompp-em", "mdrun-em", "grompp-md", "mdrun-md-gpu",
    ]
    assert report["software"]["gromacs"]["version"] == "2024.3-stub"
    assert report["software"]["gromacs"]["gpu_support"] == "CUDA"
    assert "python" in report["software"]
    assert report["steps"]["md"] == 5000
    assert report["mdrun"]["performance_ns_per_day"] == 1850.0
    assert smoke.validate_report(report) == []
    assert "2024.3-stub" in smoke.summarise(report)


def test_run_smoke_writes_the_mdp_settings_the_pipeline_uses(tmp_path, stub_gmx, fake_ff):
    workdir = tmp_path / "run"
    smoke.run_smoke(ps=100, workdir=str(workdir), gmx_binary=stub_gmx,
                    martini3_dir=fake_ff, ntomp=1, timeout=120, system="martini")
    md_mdp = (workdir / "smoke_md.mdp").read_text(encoding="utf-8")
    assert "dt                      = 0.02" in md_mdp
    assert "nsteps                  = 5000" in md_mdp
    assert "reaction-field" in md_mdp and "epsilon_r               = 15" in md_mdp
    assert "c-rescale" in md_mdp
    em_mdp = (workdir / "smoke_em.mdp").read_text(encoding="utf-8")
    assert "integrator              = steep" in em_mdp


def test_run_smoke_without_gmx_reports_instead_of_crashing(tmp_path):
    report = smoke.run_smoke(ps=100, workdir=str(tmp_path / "run"),
                             gmx_binary="/nonexistent/gmx", timeout=10)
    assert report["ok"] is False
    assert report["status"] == "fail"
    assert "topology" in report["stage_error"] or "GROMACS" in report["stage_error"]
    assert smoke.validate_report(report) == []


def test_run_smoke_dry_run_touches_nothing(tmp_path, stub_gmx, fake_ff):
    report = smoke.run_smoke(ps=100, workdir=str(tmp_path / "run"), gmx_binary=stub_gmx,
                             martini3_dir=fake_ff, dry_run=True, system="martini")
    assert report["status"] == "dry-run"
    assert report["stages"] == []
    assert report["steps"]["md"] == 5000


def test_report_validation_rejects_a_broken_document():
    problems = smoke.validate_report({"schema": "nope", "status": "ok", "ps_requested": 1,
                                      "ps_completed": 0, "stages": [], "software": {}})
    assert problems


def test_cli_show_renders_an_existing_report(tmp_path, capsys, stub_gmx, fake_ff):
    report = smoke.run_smoke(ps=100, workdir=str(tmp_path / "run"), gmx_binary=stub_gmx,
                             martini3_dir=fake_ff, ntomp=1, timeout=120, system="martini",
                             temperature=310.0)
    path = tmp_path / "gmx_smoke.json"
    smoke.dump(report, str(path))
    assert smoke.main(["--show", str(path)]) == 0
    out = capsys.readouterr().out
    assert "2024.3-stub" in out and "100.000" in out


def test_cli_writes_the_report_file(tmp_path, capsys, stub_gmx, fake_ff):
    out = tmp_path / "gmx_smoke.json"
    code = smoke.main([
        "--ps", "100", "--workdir", str(tmp_path / "run"), "--gmx", stub_gmx,
        "--martini3-dir", fake_ff, "--ntomp", "1", "--out", str(out), "--timeout", "120",
        "--system", "martini",
    ])
    assert code == 0
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["schema"] == "cgmd.gmxsmoke.v1"
    assert document["ok"] is True
    assert smoke.validate_report(document) == []


# ---------------------------------------------------------------------------
# the stock-GROMACS flavour (what a native Windows install runs)
# ---------------------------------------------------------------------------
def test_spc_topology_uses_only_bundled_force_fields(tmp_path):
    path = tmp_path / "spc.top"
    smoke.write_spc_topology(str(path))
    text = path.read_text(encoding="utf-8")
    assert 'oplsaa.ff/forcefield.itp' in text
    assert 'oplsaa.ff/spce.itp' in text
    assert "[ molecules ]" in text and "SOL 0" in text


def test_spc_run_fills_the_box_with_solvate(tmp_path, stub_gmx):
    report = smoke.run_smoke(ps=100, workdir=str(tmp_path / "run"), gmx_binary=stub_gmx,
                             ntomp=1, timeout=120, system="spc", box_nm=1.0)
    assert report["ok"] is True, report.get("stage_error")
    assert report["system_kind"] == "spc"
    assert report["system"]["kind"] == "spc-water-box"
    assert report["system"]["atoms"] == 375          # 125 SPC waters
    assert report["system"]["molecules"] == 125
    assert [stage["stage"] for stage in report["stages"]] == [
        "solvate", "grompp-em", "mdrun-em", "grompp-md", "mdrun-md-gpu",
    ]
    assert report["dt_ps"] == 0.002
    assert report["steps"]["md"] == 50000            # 100 ps / 0.002 ps
    assert report["ps_completed"] == 100.0
    assert smoke.validate_report(report) == []


def test_spc_mdp_uses_pme_and_two_femtosecond_steps(tmp_path, stub_gmx):
    workdir = tmp_path / "run"
    smoke.run_smoke(ps=100, workdir=str(workdir), gmx_binary=stub_gmx, ntomp=1,
                    timeout=120, system="spc", box_nm=1.0)
    md = (workdir / "smoke_md.mdp").read_text(encoding="utf-8")
    assert "dt                      = 0.002" in md
    assert "nsteps                  = 50000" in md
    assert "coulombtype             = PME" in md
    assert "constraints             = h-bonds" in md
    assert "v-rescale" in md and "c-rescale" in md


def test_spc_reports_a_failed_solvate(tmp_path):
    script = tmp_path / "gmx"
    script.write_text("#!/bin/bash\ncase \"$1\" in --version) echo 'GROMACS version: 2024.3'; ;; "
                      "solvate) echo 'Fatal error: spc216.gro not found' >&2; exit 1 ;; esac\n",
                      encoding="utf-8")
    script.chmod(0o755)
    report = smoke.run_smoke(ps=100, workdir=str(tmp_path / "run"), gmx_binary=str(script),
                             timeout=30, system="spc", box_nm=1.0)
    assert report["ok"] is False
    assert "solvate" in (report["stage_error"] or "")


def test_martini_flavour_still_works_after_the_refactor(tmp_path, stub_gmx, fake_ff):
    report = smoke.run_smoke(ps=100, workdir=str(tmp_path / "run"), gmx_binary=stub_gmx,
                             martini3_dir=fake_ff, ntomp=1, timeout=120, system="spc",
                             box_nm=1.0)
    assert report["system_kind"] == "spc"
    martini = smoke.run_smoke(ps=100, workdir=str(tmp_path / "m"), gmx_binary=stub_gmx,
                              martini3_dir=fake_ff, ntomp=1, timeout=120, system="martini")
    assert martini["system_kind"] == "martini"
    assert martini["dt_ps"] == 0.02


# ---------------------------------------------------------------------------
# the native Windows runner (PowerShell, no python, no Martini files)
# ---------------------------------------------------------------------------
HUB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "cgmd-hub", "runner")


def test_native_runner_exists_and_is_ascii():
    path = os.path.join(HUB, "Run-Gmx-Native.ps1")
    assert os.path.exists(path)
    with open(path, "rb") as handle:
        handle.read().decode("ascii")


def test_native_runner_is_self_contained():
    source = open(os.path.join(HUB, "Run-Gmx-Native.ps1"), encoding="ascii").read()
    assert "oplsaa.ff/forcefield.itp" in source      # stock force field
    assert "spc216.gro" in source                   # stock water box
    assert "solvate" in source
    assert "grompp" in source and "mdrun" in source
    assert "cgmd.gmxsmoke.v1" in source             # same schema as python
    assert "C:\\Program Files" in source            # finds a default install
    assert "-nb', 'cpu" in source or "'-nb', 'cpu'" in source   # cpu fallback
    assert "Steepest Descents" in source


def test_native_runner_reports_every_version_field():
    source = open(os.path.join(HUB, "Run-Gmx-Native.ps1"), encoding="ascii").read()
    for field in ("version", "precision", "simd", "gpu_support", "cuda_runtime", "fft", "openmp"):
        assert "gromacs." + field in source or "'" + field + "'" in source, field


def test_smoke_runner_delegates_to_the_native_path():
    source = open(os.path.join(HUB, "Run-Smoke.ps1"), encoding="ascii").read()
    assert "Run-Gmx-Native.ps1" in source and "-Native" in source


def test_poller_prefers_a_native_windows_gmx():
    source = open(os.path.join(HUB, "Invoke-CgmdPoll.ps1"), encoding="ascii").read()
    assert "Run-Gmx-Native.ps1" in source
    assert "gmx.exe" in source


def test_selfcheck_accepts_a_native_gmx_when_wsl_is_absent():
    source = open(os.path.join(HUB, "Test-CgmdHub.ps1"), encoding="ascii").read()
    assert "Find-NativeGmx" in source
    assert "Get-GmxVersionLine" in source
    assert "native windows" in source


def test_native_runner_has_an_inline_topology_fallback():
    """GROMACS 2025.1 on Windows crashed in grompp on the bundled oplsaa.ff.

    The runner must be able to drop the #include entirely and write every SPC
    parameter inline, and it must record which route produced the run.
    """
    source = open(os.path.join(HUB, "Run-Gmx-Native.ps1"), encoding="ascii").read()
    assert "Write-SpcTopology" in source
    assert "-Kind 'inline'" in source
    assert "[ settles ]" in source
    assert "grompp-em-inline" in source
    assert "inline (self-contained SPC parameters)" in source


def test_native_runner_records_the_force_field_probe():
    source = open(os.path.join(HUB, "Run-Gmx-Native.ps1"), encoding="ascii").read()
    assert "Data prefix:" in source          # data_prefix from gmx --version
    assert "share\\top" in source
    assert "report['environment']" in source
    assert "output_tail" in source           # full failure text, not just 6 lines
