#!/usr/bin/env bash
# =============================================================================
# CGMD-Engine - WSL2 environment setup / self-check
#
#   bash code/cgmd/setup_env.sh --check      # verify only (default)
#   bash code/cgmd/setup_env.sh --install    # pip install the python side
#   bash code/cgmd/setup_env.sh --install --yes
#
# What it checks
#   python3 >= 3.9, pip, numpy, matplotlib, MDAnalysis, vermouth (martinize2),
#   insane (Martini membrane builder), martini-forcefields (Martini 3 itp set),
#   GROMACS (gmx) with CUDA GPU support, nvidia-smi inside WSL2.
#
# GROMACS itself is never installed silently: the script prints the exact
# command for your distro instead, because a GPU-enabled build must match the
# installed CUDA driver.
# =============================================================================
set -u -o pipefail

MODE="check"
ASSUME_YES="0"
VENV_DIR="${CGMD_VENV:-}"
PYTHON_BIN="${CGMD_PYTHON:-python3}"

while [ $# -gt 0 ]; do
    case "$1" in
        --check) MODE="check" ;;
        --install) MODE="install" ;;
        --yes|-y) ASSUME_YES="1" ;;
        --venv) shift; VENV_DIR="${1:-}" ;;
        --python) shift; PYTHON_BIN="${1:-python3}" ;;
        -h|--help)
            sed -n '2,20p' "$0"
            exit 0
            ;;
        *)
            echo "unknown option: $1" >&2
            exit 2
            ;;
    esac
    shift
done

RED=""; GREEN=""; YELLOW=""; NC=""
if [ -t 1 ]; then
    RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"; NC="\033[0m"
fi

PROBLEMS=0
REPORT=()

ok()   { printf "${GREEN}[ok]${NC}   %s\n" "$1"; REPORT+=("ok   $1"); }
warn() { printf "${YELLOW}[warn]${NC} %s\n" "$1"; REPORT+=("warn $1"); }
fail() { printf "${RED}[fail]${NC} %s\n" "$1"; REPORT+=("fail $1"); PROBLEMS=$((PROBLEMS+1)); }
info() { printf "       %s\n" "$1"; }

echo "=============================================================="
echo " CGMD-Engine environment $MODE"
echo " host: $(uname -srm)"
echo "=============================================================="

# --- 1. python ---------------------------------------------------------------
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    fail "python3 not found (sudo apt install python3 python3-venv python3-pip)"
    PYTHON_BIN=""
else
    PY_VERSION="$($PYTHON_BIN -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)"
    if [ -z "$PY_VERSION" ]; then
        fail "python3 is not runnable"
    else
        ok "python $PY_VERSION ($(command -v "$PYTHON_BIN"))"
        case "$PY_VERSION" in
            3.[0-8]) warn "python $PY_VERSION is older than the recommended 3.9+" ;;
        esac
    fi
fi

if [ -n "$VENV_DIR" ]; then
    if [ -d "$VENV_DIR" ]; then
        ok "virtualenv exists: $VENV_DIR"
    elif [ "$MODE" = "install" ]; then
        if [ -n "$PYTHON_BIN" ]; then
            "$PYTHON_BIN" -m venv "$VENV_DIR" && ok "virtualenv created: $VENV_DIR" || fail "could not create venv $VENV_DIR"
        fi
    else
        warn "virtualenv $VENV_DIR does not exist (run with --install)"
    fi
    if [ -x "$VENV_DIR/bin/python" ]; then
        PYTHON_BIN="$VENV_DIR/bin/python"
        info "using $PYTHON_BIN"
    fi
fi

# --- 2. python packages ------------------------------------------------------
if [ -n "$PYTHON_BIN" ]; then
    check_py() {
        local module="$1" label="$2" required="$3"
        if "$PYTHON_BIN" -c "import $module" >/dev/null 2>&1; then
            local version
            version="$("$PYTHON_BIN" -c "import $module; print(getattr($module,'__version__','?'))" 2>/dev/null)"
            ok "$label ${version}"
            return 0
        fi
        if [ "$required" = "required" ]; then
            fail "$label missing"
        else
            warn "$label missing (optional)"
        fi
        return 1
    }

    MISSING_PKGS=""
    check_py numpy numpy required || MISSING_PKGS="$MISSING_PKGS numpy"
    check_py matplotlib matplotlib optional || MISSING_PKGS="$MISSING_PKGS matplotlib"
    check_py MDAnalysis MDAnalysis required || MISSING_PKGS="$MISSING_PKGS MDAnalysis"
    check_py vermouth "vermouth (martinize2)" required || MISSING_PKGS="$MISSING_PKGS vermouth"
    check_py insane "insane (membrane builder)" required || MISSING_PKGS="$MISSING_PKGS insane"
    check_py martini_forcefields "martini-forcefields" required || MISSING_PKGS="$MISSING_PKGS martini-forcefields"

    for tool in martinize2 insane; do
        if command -v "$tool" >/dev/null 2>&1; then
            ok "$tool on PATH ($(command -v "$tool"))"
        else
            fail "$tool not on PATH"
            MISSING_PKGS="$MISSING_PKGS $tool"
        fi
    done

    if [ "$MODE" = "install" ] && [ -n "$MISSING_PKGS" ]; then
        info "installing python packages:$MISSING_PKGS"
        EXTRA=""
        if [ "$ASSUME_YES" = "1" ]; then EXTRA="--quiet"; fi
        if "$PYTHON_BIN" -m pip install --upgrade pip $EXTRA >/dev/null 2>&1; then
            info "pip upgraded"
        fi
        if "$PYTHON_BIN" -m pip install $EXTRA \
            numpy matplotlib MDAnalysis vermouth insane martini-forcefields; then
            ok "python packages installed"
        else
            fail "pip install failed (try --venv ~/cgmd-venv or add --user)"
        fi
    fi
fi

# --- 3. GROMACS --------------------------------------------------------------
GMX_BIN=""
for candidate in gmx gmx_mpi; do
    if command -v "$candidate" >/dev/null 2>&1; then
        GMX_BIN="$candidate"
        break
    fi
done

if [ -z "$GMX_BIN" ]; then
    fail "GROMACS (gmx) not found"
    info "install one of:"
    info "  sudo apt install gromacs            # Ubuntu 22.04+ ships 2021/2024 with GPU support"
    info "  conda install -c conda-forge gromacs=2024"
    info "  https://manual.gromacs.org/current/install-guide (build with -DGMX_GPU=CUDA)"
else
    GMX_VERSION="$($GMX_BIN --version 2>/dev/null | sed -n 's/^GROMACS version:[[:space:]]*//p' | head -1)"
    ok "gromacs $GMX_VERSION ($(command -v "$GMX_BIN"))"
    if $GMX_BIN --version 2>/dev/null | grep -qi "GPU support:.*CUDA"; then
        ok "GROMACS built with CUDA GPU support"
    else
        warn "GROMACS does not report CUDA GPU support - mdrun will fall back to the CPU"
    fi
    if $GMX_BIN --version 2>/dev/null | grep -qi "SIMD.*AVX2_256"; then
        ok "AVX2 SIMD kernels available"
    fi
fi

# --- 4. GPU ------------------------------------------------------------------
if command -v nvidia-smi >/dev/null 2>&1; then
    GPU_LINE="$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null | head -1)"
    if [ -n "$GPU_LINE" ]; then
        ok "GPU visible in WSL2: $GPU_LINE"
    else
        fail "nvidia-smi present but reports no device (check the Windows NVIDIA driver)"
    fi
else
    fail "nvidia-smi not found inside WSL2"
    info "install the Windows NVIDIA driver (>= 535) - it exposes the GPU to WSL2,"
    info "do NOT install a Linux driver inside WSL."
fi

# --- 5. Martini 3 force field ------------------------------------------------
MARTINI_DIR="${CGMD_MARTINI3_DIR:-}"
if [ -z "$MARTINI_DIR" ] && [ -n "$PYTHON_BIN" ]; then
    MARTINI_DIR="$("$PYTHON_BIN" - <<'PY' 2>/dev/null
import glob, os
try:
    import martini_forcefields
except Exception:
    raise SystemExit(0)
root = os.path.dirname(martini_forcefields.__file__)
hits = sorted(glob.glob(os.path.join(root, "**", "gmx_files"), recursive=True))
print(hits[0] if hits else "")
PY
)"
fi
if [ -n "$MARTINI_DIR" ] && [ -d "$MARTINI_DIR" ]; then
    if ls "$MARTINI_DIR"/*.itp >/dev/null 2>&1 || find "$MARTINI_DIR" -name "*.itp" -print -quit | grep -q .; then
        ok "Martini 3 force field: $MARTINI_DIR"
    else
        fail "Martini 3 directory has no .itp files: $MARTINI_DIR"
    fi
else
    warn "Martini 3 force field not located yet (pip install martini-forcefields or set CGMD_MARTINI3_DIR)"
fi

# --- 6. repository sanity ----------------------------------------------------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [ -f "$REPO_ROOT/results/status/cgmd_task.json" ]; then
    ok "task contract present: results/status/cgmd_task.json"
else
    warn "no task document yet (the hub bootstrap creates an idle one)"
fi
if command -v git >/dev/null 2>&1; then
    ok "git $(git --version | awk '{print $3}')"
else
    fail "git not found inside WSL (sudo apt install git)"
fi

# --- 7. write a machine readable report -------------------------------------
REPORT_DIR="$REPO_ROOT/skills/cgmd-hub/state"
mkdir -p "$REPORT_DIR" 2>/dev/null || true
REPORT_FILE="$REPORT_DIR/wsl-env-check.txt"
{
    echo "# generated by code/cgmd/setup_env.sh at $(date -Is)"
    echo "# host: $(uname -srm)"
    for line in "${REPORT[@]}"; do echo "$line"; done
} > "$REPORT_FILE" 2>/dev/null && info "report: $REPORT_FILE"

echo "--------------------------------------------------------------"
if [ "$PROBLEMS" -eq 0 ]; then
    printf "${GREEN}environment OK - ready for GPU production runs${NC}\n"
    exit 0
fi
printf "${YELLOW}%d problem(s) found${NC}\n" "$PROBLEMS"
exit 1
