"""3-Account x 3-Machine x Multi-Arena-Session Federation & Martini CG-MD Hub.

Implements the user's exact distributed research architecture:
- `mqgg5630-cyber`   -> Laptop (`LAPTOP-R77M5D6M`) -> Commander Arena Session
- `shaohuawen03-cyber` -> HPC (`mu01` `cu`/`fat1`) -> Graduation Thesis & All-Atom MD Session
- `hukeying85-ux`    -> Desktop Workstation (GPU)  -> Martini 3 Coarse-Grained MD Session

Also powers:
- Plan A (Cloudflare Quick Tunnel) + Plan D (ZeroTier Free 25-node LAN) dual networking
- Multi-Arena-Session Registry & 1-click Copy-Paste Dispatch Prompt Generator
- Martini 3 Coarse-Grained Antimicrobial Peptide (AMP) Membrane MD Pipeline Generator
- End-to-end "Haoleme / JobBeacon" push notification config & live test sender
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
JB_SRC_CANDIDATES = (
    Path(__file__).resolve().parent / "jobbeacon_src",
    REPO_ROOT / "projects" / "jobbeacon" / "src",
)
for _cand in JB_SRC_CANDIDATES:
    if _cand.is_dir() and str(_cand) not in sys.path:
        sys.path.insert(0, str(_cand))

from jobbeacon.notifiers import dispatch_alert  # noqa: E402

TRI_NODE_MATRIX: tuple[dict[str, Any], ...] = (
    {
        "node_id": "laptop_mqgg",
        "emoji": "💻",
        "machine": "主力笔记本 (LAPTOP-R77M5D6M)",
        "gh_account": "mqgg5630-cyber",
        "ssh_host": "github.com (443 穿透)",
        "arena_session_name": "[S1-总控] Commander · 笔记本与全局调度",
        "bound_repo_hint": "mqgg5630-cyber/0fuye (私有总控库)",
        "core_mission": "全局任务规划拆解、跨会话派单、硕士毕业论文一键排版 (Lark-Formatter)、Notion/云盘总账管理",
        "network_plan": "方案A (Cloudflare HTTPS 供手机直看面板) + 方案D (ZeroTier 虚拟内网主控 IP)",
        "sync_daemon": "git-sync-hub (Windows 计划任务静默轮询) + ArenaDesk.exe",
    },
    {
        "node_id": "hpc_shaohua",
        "emoji": "🧬",
        "machine": "HPC 超算集群 (mu01 · cu 64核 / fat1 96核1T)",
        "gh_account": "shaohuawen03-cyber",
        "ssh_host": "github-shaohua -> ssh.github.com:443",
        "arena_session_name": "[S2-毕业课题] BioHPC · 宏基因组/AMP模型/全原子MD",
        "bound_repo_hint": "shaohuawen03-cyber/BioHPC (mu01 已连通)",
        "core_mission": "硕士毕业课题核心：476 样本 AD 肠道宏基因组、XAMP/HMD-AMP 候选肽预测、胜出肽段全原子精细 MD (CHARMM36m) 与伞形采样 PMF",
        "network_plan": "SSH 跳板 + node_agent.py 出站 HTTPS 推 ntfy（严禁开放超算公网入站端口）",
        "sync_daemon": "python3 code/federation/node_agent.py --role hpc (Linux 后台守护，0 Token)",
    },
    {
        "node_id": "desktop_hukeying",
        "emoji": "🖥️",
        "machine": "高性能台式机 (GPU Workstation + 笔记本联邦代理)",
        "gh_account": "hukeying85-ux",
        "ssh_host": "github-hukeying -> ssh.github.com:443",
        "arena_session_name": "[S3-粗粒化算力] hukeying85-ux/0fuye · arena/32cd826e-0fuye",
        "bound_repo_hint": "hukeying85-ux/0fuye @ arena/32cd826e-0fuye (免合并直接运行)",
        "core_mission": "高通量跑 Martini 3 粗粒化分子动力学 (dt=20 fs, 1~3 us/day)：对课题筛出的 Top 10~20 抗菌肽做细菌拟膜 (POPE:POPG 3:1) 打孔/吸附微秒级初筛，把 Top 2~3 回传 HPC 精算",
        "network_plan": "方案D (ZeroTier 固定内网 IP 供笔记本/手机 SSH 直连与 .xtc 大轨迹高速互传) + 方案A 备用",
        "sync_daemon": "cgmd-hub (Invoke-CgmdPoll.ps1) + git-sync-hub 默认值守同步",
    },
)

AD_DUAL_NETWORK_PLAN: dict[str, Any] = {
    "selected_combo": "方案 A (Cloudflare Quick Tunnel) + 方案 D (ZeroTier Free 25 节点虚拟局域网)",
    "total_cost": "¥0 / 永久免费（彻底替代收费版手机 Tailscale）",
    "channels": [
        {
            "code": "Plan-A",
            "title": "通道 A：Cloudflare Quick Tunnel（手机免装 App 随时看进度）",
            "purpose": "给手机 Safari/Chrome 提供零配置 HTTPS 地址打开 /mobile 伴侣端，实时查看三台机器『好了吗』进度条、ns/day (us/day) 与审批闸门。",
            "command": "powershell -ExecutionPolicy Bypass -File code\\connect\\setup_ad_dual_mesh.ps1 -NodeRole laptop -Action planA",
        },
        {
            "code": "Plan-D",
            "title": "通道 D：ZeroTier Free 25 节点虚拟局域网（台式机↔笔记本↔手机 SSH 高速内网）",
            "purpose": "把笔记本 (.11)、台式机 (.12) 与手机 (.13) 组进同一个免费加密二层内网：手机可用免费 Termius/JuiceSSH 直连台式机，台式机跑完的 GB 级 .xtc 粗粒化轨迹可直接 scp/rsync 传给笔记本或跳板传 HPC，不走 Git 不爆仓！",
            "command": "powershell -ExecutionPolicy Bypass -File code\\connect\\setup_ad_dual_mesh.ps1 -NodeRole desktop -Action planD -ZeroTierNetworkId <你的16位免费NetworkID>",
        },
    ],
}

ARENA_SESSION_BOUNDARIES: dict[str, Any] = {
    "can_arena_sessions_be_grokbot": True,
    "headline": "完全可以用多个 Arena 会话组建 GrokBot！但必须采用『本地 24×7 零Token哨兵 + 按需唤醒 Arena 会话』双层架构",
    "limits": [
        {
            "metric": "单次 bash 命令最长等待",
            "limit": "30 分钟 (1800 秒)",
            "explanation": "适合编译、环境部署、中等时长脚本与建模预处理，不适合直接阻塞等待跑 12 小时的 MD。",
        },
        {
            "metric": "后台进程单次阻塞等待 (wait_for)",
            "limit": "3 分钟 (180 秒)",
            "explanation": "用于拉起服务或检查阶段性日志非常快。",
        },
        {
            "metric": "单轮对话连续工作与闲置休眠机制",
            "limit": "回合制 (Turn-based)：回复结束后云端会话静默挂起，不会自己在半夜主动开口说话",
            "explanation": "分支代码与会话上下文永久保存；只要您发一句话（粘贴唤醒词），几秒内满血恢复继续分析！",
        },
    ],
    "best_practice_loop": [
        "第 1 步（派单）：在 S1 总控会话（mqgg5630）规划课题批次，生成目标会话唤醒指令与任务包。",
        "第 2 步（投递）：粘贴到 S3 台式机会话（hukeying85）或 S2 超算会话（shaohuawen03），让 AI 自动完成建模并以后台守护方式（nohup / Start-Process + node_agent.py）启动长耗时动力学。",
        "第 3 步（无限时长盯梢）：本机/台式机/HPC 上的 node_agent.py 7×24 小时 0-Token 持续盯 md.log 与 squeue。",
        "第 4 步（好了吗秒推）：跑完或发散报错的 1 秒内，node_agent.py 直接往您手机推送『✅ 好了！』锁屏通知。",
        "第 5 步（回传闭环）：您打开对应 Arena 会话说一句『已跑完，拉取最新摘要并筛出 Top-3 回传课题主库』，完成科研闭环！",
    ],
}

ARCHITECTURE_OPTIMIZATIONS: tuple[dict[str, str], ...] = (
    {
        "id": "OPT-01",
        "title": "控制流与重数据流彻底分离（防 Git 100MB 爆仓）",
        "detail": "Git 仓库只同步 .mdp/.sbatch/FASTA/收敛指标 JSON/论文矢量图（<5MB，node_agent 已加硬护栏拦截）；几百 MB 的 .xtc/.trr/.tpr 动力学轨迹一律走方案 D ZeroTier 虚拟局域网点对点直传。",
    },
    {
        "id": "OPT-02",
        "title": "粗粒化初筛 (台式机 hukeying) → 全原子精修 (HPC shaohuawen) 漏斗加速",
        "detail": "先用台式机 GPU 跑 Martini 3 粗粒化 (dt=20 fs, 速度提升 100~300 倍) 在细菌膜 POPE:POPG (3:1) 与哺乳动物膜 POPC:CHOL 间筛出高选择性抗菌肽 Top 2~3，再反粗粒化 (cg2at2/backward) 送 mu01 跑全原子 PMF，省下 80% 超算机时！",
    },
    {
        "id": "OPT-03",
        "title": "跨平台 Python 哨兵补齐 Linux HPC 短板",
        "detail": "原 git-sync-hub 仅支持 Windows PowerShell；新增纯标准库 code/federation/node_agent.py，Windows 台式机与 Linux HPC (mu01) 一套脚本通跑。",
    },
    {
        "id": "OPT-04",
        "title": "三账号严格单机单主号隔离（杜绝 Token 串号）",
        "detail": "笔记本锁死 mqgg5630-cyber，台式机锁死 hukeying85-ux，HPC 仅放 shaohuawen03-cyber 的 SSH 443 密钥；跨库投递走联邦任务单 JSON + Arena 专属会话，互不污染凭据。",
    },
    {
        "id": "OPT-05",
        "title": "全链路『好了吗』主动锁屏通知打通",
        "detail": "不仅网页端响铃，更打通 ntfy 加密随机频道与自定义 Webhook：无论是 hub_task 执行完、台式机粗粒化跑完 2 us、还是 Martini 压强发散报警，均主动推手机锁屏。",
    },
)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_martini_cgmd_bundle(
    peptide_name: str = "AMP_Cand01",
    sequence: str = "GIGKFLHSAKKFGKAFVGEIMNS",
    membrane_type: str = "bacterial_inner",
    box_xy_nm: float = 10.0,
    box_z_nm: float = 12.0,
    sim_us: float = 2.0,
    ntfy_topic: str = "",
) -> dict[str, Any]:
    """Generate ready-to-run Martini 3 Coarse-Grained MD workflow for Desktop (`hukeying85-ux`)."""
    safe_name = "".join(c if (c.isalnum() or c in "_-") else "_" for c in peptide_name.strip()) or "AMP_Cand01"
    clean_seq = "".join(c for c in sequence.strip().upper() if c.isalpha()) or "GIGKFLHSAKKFGKAFVGEIMNS"
    us = max(0.1, min(float(sim_us), 50.0))
    # dt = 0.020 ps -> 1 ns = 50,000 steps -> 1 us = 50,000,000 steps
    nsteps = int(round(us * 50_000_000))

    if membrane_type == "mammalian_rbc":
        lipids = "-l POPC:4 -l CHOL:1"
        mem_desc = "哺乳动物红细胞对照膜 (POPC:CHOL = 4:1 · 溶血毒性评估)"
    else:
        lipids = "-l POPE:3 -l POPG:1"
        mem_desc = "革兰氏阴性菌拟内膜 (POPE:POPG = 3:1 · 抗菌打孔/吸附活性初筛)"

    topic_arg = f"--notify ntfy:{ntfy_topic.strip()}" if ntfy_topic.strip() else ""

    mdp_eq = (
        "; Martini 3 Safe Pre-Equilibration (dt = 10 fs, Berendsen) - prevents CG blow-up\n"
        "integrator               = md\n"
        "dt                       = 0.010\n"
        "nsteps                   = 2000000 ; 20 ns safe relaxation\n"
        "nstxout-compressed       = 10000\n"
        "nstlog                   = 5000\n"
        "nstenergy                = 5000\n"
        "cutoff-scheme            = Verlet\n"
        "nstlist                  = 20\n"
        "coulombtype              = reaction-field\n"
        "rcoulomb                 = 1.1\n"
        "epsilon_r                = 15\n"
        "vdw_type                 = cutoff\n"
        "vdw-modifier             = Potential-shift-verlet\n"
        "rvdw                     = 1.1\n"
        "tcoupl                   = v-rescale\n"
        "tc-grps                  = Protein Membrane W_ION\n"
        "tau_t                    = 1.0 1.0 1.0\n"
        "ref_t                    = 310 310 310\n"
        "pcoupl                   = Berendsen\n"
        "pcoupltype               = semiisotropic\n"
        "tau_p                    = 4.0\n"
        "compressibility          = 3e-4 3e-4\n"
        "ref_p                    = 1.0 1.0\n"
    )

    mdp_prod = (
        f"; Martini 3 Production Coarse-Grained MD ({us:g} us, dt = 20 fs, GPU accelerated)\n"
        "integrator               = md\n"
        "dt                       = 0.020\n"
        f"nsteps                   = {nsteps} ; {us:g} us total\n"
        "nstxout-compressed       = 25000 ; frame every 500 ps\n"
        "nstlog                   = 10000\n"
        "nstenergy                = 10000\n"
        "cutoff-scheme            = Verlet\n"
        "nstlist                  = 20\n"
        "coulombtype              = reaction-field\n"
        "rcoulomb                 = 1.1\n"
        "epsilon_r                = 15\n"
        "vdw_type                 = cutoff\n"
        "vdw-modifier             = Potential-shift-verlet\n"
        "rvdw                     = 1.1\n"
        "tcoupl                   = v-rescale\n"
        "tc-grps                  = Protein Membrane W_ION\n"
        "tau_t                    = 1.0 1.0 1.0\n"
        "ref_t                    = 310 310 310\n"
        "pcoupl                   = Parrinello-Rahman\n"
        "pcoupltype               = semiisotropic\n"
        "tau_p                    = 12.0\n"
        "compressibility          = 3e-4 3e-4\n"
        "ref_p                    = 1.0 1.0\n"
    )

    runner_sh = (
        "#!/usr/bin/env bash\n"
        f"# Martini 3 Coarse-Grained AMP-Membrane Screening ({safe_name} | {mem_desc})\n"
        "# Target Machine: Desktop GPU Workstation (hukeying85-ux)\n"
        "set -euo pipefail\n\n"
        f"PEPTIDE='{safe_name}'\n"
        f"SEQ='{clean_seq}'\n"
        "mkdir -p cg_${PEPTIDE} && cd cg_${PEPTIDE}\n\n"
        "# 1. Convert AA peptide structure to Martini 3 CG topology via martinize2\n"
        "martinize2 -f ../${PEPTIDE}_aa.pdb -o ${PEPTIDE}_cg.top -x ${PEPTIDE}_cg.pdb \\\n"
        "  -ff martini3001 -dssp mkdssp -elastic -ef 500 -eu 0.9 -p backbone\n\n"
        f"# 2. Build solvated asymmetric/symmetric membrane box ({box_xy_nm:g}x{box_xy_nm:g}x{box_z_nm:g} nm) via insane.py\n"
        f"python3 insane.py -f ${{PEPTIDE}}_cg.pdb -o system_cg.gro -p topol.top \\\n"
        f"  -x {box_xy_nm:g} -y {box_xy_nm:g} -z {box_z_nm:g} {lipids} -sol W -salt 0.15 -charge auto -center -dm 3.5\n\n"
        "# 3. Energy Minimization + 20 ns Safe Equilibration (dt=10fs) + GPU Production (dt=20fs)\n"
        "gmx grompp -f cg_em.mdp -c system_cg.gro -p topol.top -o em.tpr -maxwarn 1\n"
        "gmx mdrun -deffnm em -ntmpi 1 -ntomp 8\n"
        "gmx grompp -f cg_eq_dt10fs.mdp -c em.gro -p topol.top -o eq.tpr -maxwarn 1\n"
        "gmx mdrun -deffnm eq -nb gpu -pme cpu -ntmpi 1 -ntomp 8\n"
        "gmx grompp -f cg_prod_dt20fs.mdp -c eq.gro -p topol.top -o prod.tpr -maxwarn 1\n\n"
        "# 4. Launch GPU production + 0-Token JobBeacon sentinel (auto push 'Haoleme' alert on completion!)\n"
        "gmx mdrun -deffnm prod -nb gpu -ntmpi 1 -ntomp 8 &\n"
        "MD_PID=$!\n"
        f"python3 ../../code/federation/node_agent.py --role desktop --task-title \"CG-MD {safe_name} ({us:g} us)\" \\\n"
        f"  --md-log prod.log --interval 30 {topic_arg}\n"
        "wait $MD_PID\n"
    )

    return {
        "peptide_name": safe_name,
        "sequence": clean_seq,
        "length_aa": len(clean_seq),
        "membrane_type": membrane_type,
        "membrane_desc": mem_desc,
        "sim_us": us,
        "nsteps": nsteps,
        "mdp_eq": mdp_eq,
        "mdp_prod": mdp_prod,
        "runner_script": runner_sh,
    }


class FederationHub:
    """Manages 3-account session registry, cross-session task dispatches, and 'Haoleme' alerts."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_path = self.data_dir / "arena_sessions.json"
        self.dispatches_path = self.data_dir / "federation_dispatches.json"
        self.notify_path = self.data_dir / "beacon_notify.json"
        self._ensure_seed()

    def _ensure_seed(self) -> None:
        if not self.notify_path.exists():
            rand_suffix = secrets.token_hex(5)
            self._write_json(
                self.notify_path,
                {
                    "enabled": True,
                    "ntfy_server": "https://ntfy.sh",
                    "ntfy_topic": f"arena-beacon-{rand_suffix}",
                    "webhook_url": "",
                    "notify_on_hub_task": True,
                    "notify_on_md_finish": True,
                    "notify_on_md_error": True,
                    "last_test_result": None,
                    "updated_at": _utc_now(),
                },
            )
        if not self.sessions_path.exists():
            self._write_json(
                self.sessions_path,
                [
                    {
                        "session_slot": "S1",
                        "title": "总控与笔记本管家 (当前会话)",
                        "node_id": "laptop_mqgg",
                        "gh_account": "mqgg5630-cyber",
                        "branch_or_repo": "mqgg5630-cyber/0fuye @ arena/89735ee7-0fuye",
                        "status": "active",
                        "focus": "全局规划派单 · 硕士论文排版 · Notion/云盘总控",
                        "updated_at": _utc_now(),
                    },
                    {
                        "session_slot": "S2",
                        "title": "硕士毕业课题与超算主线会话",
                        "node_id": "hpc_shaohua",
                        "gh_account": "shaohuawen03-cyber",
                        "branch_or_repo": "shaohuawen03-cyber/BioHPC @ mu01",
                        "status": "active",
                        "focus": "AD 476样本宏基因组 · XAMP/HMD-AMP · mu01 全原子精细 MD",
                        "updated_at": _utc_now(),
                    },
                    {
                        "session_slot": "S3",
                        "title": "台式机粗粒化分子动力学会话",
                        "node_id": "desktop_hukeying",
                        "gh_account": "hukeying85-ux",
                        "branch_or_repo": "hukeying85-ux/0fuye @ arena/32cd826e-0fuye",
                        "status": "active",
                        "focus": "Martini 3 粗粒化细菌膜打孔 · cgmd_task.json (免合并直接运行) + ntfy 秒推",
                        "updated_at": _utc_now(),
                    },
                ],
            )
        if not self.dispatches_path.exists():
            sample = self._build_dispatch_record(
                target_node="desktop_hukeying",
                title="候选抗菌肽 Top-5 批次 Martini 3 粗粒化细菌内膜 (POPE:POPG 3:1) 2 us 初筛",
                objective=(
                    "接收 shaohuawen03 课题组深度学习模型筛出的候选肽序列，在台式机 GPU 上用 Martini 3 (dt=20 fs) "
                    "构建 POPE:POPG (3:1) 拟膜体系跑 2.0 us，统计膜结合时间、质心插入深度与双层膜序参数，跑完触发『好了吗』手机推送并导出 Top-2 序列回传 HPC。"
                ),
                peptide_seq="GIGKFLHSAKKFGKAFVGEIMNS",
            )
            self._write_json(self.dispatches_path, [sample])

    def _read_json(self, path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _write_json(self, path: Path, data: Any) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def get_notify_config(self) -> dict[str, Any]:
        cfg = self._read_json(self.notify_path, {})
        topic = str(cfg.get("ntfy_topic", ""))
        if topic.startswith("ldu-beacon-"):
            topic = "arena-beacon-" + topic[len("ldu-beacon-") :]
            cfg["ntfy_topic"] = topic
            self._write_json(self.notify_path, cfg)
        server = cfg.get("ntfy_server", "https://ntfy.sh").rstrip("/")
        cfg["subscribe_url"] = f"{server}/{topic}" if topic else ""
        return cfg

    def update_notify_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        cfg = self.get_notify_config()
        if payload.get("regenerate_topic"):
            cfg["ntfy_topic"] = f"arena-beacon-{secrets.token_hex(5)}"
        elif "ntfy_topic" in payload and str(payload["ntfy_topic"]).strip():
            raw_t = str(payload["ntfy_topic"]).strip()
            cfg["ntfy_topic"] = "".join(c for c in raw_t if c.isalnum() or c in "-_")[:64]
        if "ntfy_server" in payload and str(payload["ntfy_server"]).strip():
            cfg["ntfy_server"] = str(payload["ntfy_server"]).strip().rstrip("/")
        if "webhook_url" in payload:
            cfg["webhook_url"] = str(payload["webhook_url"]).strip()[:300]
        if "enabled" in payload:
            cfg["enabled"] = bool(payload["enabled"])
        cfg["updated_at"] = _utc_now()
        cfg.pop("subscribe_url", None)
        self._write_json(self.notify_path, cfg)
        return self.get_notify_config()

    def send_test_notification(self, custom_message: str = "") -> dict[str, Any]:
        cfg = self.get_notify_config()
        topic = str(cfg.get("ntfy_topic", "")).strip()
        server = str(cfg.get("ntfy_server", "https://ntfy.sh")).strip() or "https://ntfy.sh"
        webhook = str(cfg.get("webhook_url", "")).strip()

        title = "✅ 好了吗 (JobBeacon) 通知链路已打通！"
        msg = custom_message.strip() or (
            "您的三机三账号算力信标（笔记本 mqgg5630 · 超算 shaohuawen03 · 台式机粗粒化MD hukeying85）"
            "已完成『好了吗』推送自检！任务跑完或报错将第一时间推送到您的手机。"
        )
        endpoints: list[str] = []
        if topic:
            endpoints.append(f"ntfy:{topic}" if server.rstrip("/") == "https://ntfy.sh" else f"{server.rstrip('/')}/{topic}")
        if webhook:
            endpoints.append(webhook)

        res = dispatch_alert(
            endpoints,
            title,
            "completed",
            msg,
            store_dir=self.data_dir / "jobbeacon",
        )
        ok = bool(res.get("ok"))
        raw_cfg = self._read_json(self.notify_path, {})
        raw_cfg["last_test_result"] = {
            "ok": ok,
            "tested_at": _utc_now(),
            "results": res.get("deliveries", []),
        }
        self._write_json(self.notify_path, raw_cfg)
        return {
            "ok": ok,
            "subscribe_url": f"{server.rstrip('/')}/{topic}" if topic else "",
            "results": res.get("deliveries", []),
        }

    def _build_dispatch_record(
        self,
        target_node: str,
        title: str,
        objective: str,
        peptide_seq: str = "",
    ) -> dict[str, Any]:
        node_map = {n["node_id"]: n for n in TRI_NODE_MATRIX}
        node = node_map.get(target_node, node_map["desktop_hukeying"])
        notify_cfg = self.get_notify_config()
        topic = notify_cfg.get("ntfy_topic", "arena-beacon-demo")
        task_id = f"DISP-{int(dt.datetime.now(dt.timezone.utc).timestamp())}-{secrets.token_hex(2)}"
        clean_seq = "".join(c for c in peptide_seq.strip().upper() if c.isalpha())

        arena_prompt = (
            f"【跨会话协同任务单 {task_id}】\n"
            f"- 当前专职角色：{node['arena_session_name']}\n"
            f"- 绑定受控机器：{node['machine']}（严格锁定 GitHub 账号 `{node['gh_account']}`，严禁改动其他账号全局默认配置）\n"
            f"- 本次任务目标：{title}\n"
            f"- 详细执行要求：{objective}\n"
            + (f"- 候选抗菌肽序列：{clean_seq}\n" if clean_seq else "")
            + "- 长任务运行与『好了吗』通知铁律：\n"
            "  1) 耗时 >10 分钟的动力学/生信任务必须以后台守护方式启动，不要在前台阻塞超时；\n"
            f"  2) 同时挂载本地 0-Token 算力信标：`python3 code/federation/node_agent.py --role {'desktop' if target_node == 'desktop_hukeying' else ('hpc' if target_node == 'hpc_shaohua' else 'laptop')} --md-log prod.log --notify ntfy:{topic}`，确保跑完或发散 1 秒推送手机；\n"
            "  3) 严禁将 .xtc/.trr/.tpr 等 >5MB 轨迹文件提交进 Git（大轨迹走方案 D ZeroTier 虚拟内网互传），仅将精简指标摘要 JSON 与矢量图提交回仓库。"
        )
        return {
            "task_id": task_id,
            "created_at": _utc_now(),
            "target_node": node["node_id"],
            "target_machine": node["machine"],
            "target_gh_account": node["gh_account"],
            "target_session": node["arena_session_name"],
            "title": title.strip()[:160],
            "objective": objective.strip()[:1200],
            "peptide_seq": clean_seq,
            "status": "dispatched",
            "arena_prompt": arena_prompt,
        }

    def create_dispatch(
        self,
        target_node: str,
        title: str,
        objective: str,
        peptide_seq: str = "",
    ) -> dict[str, Any]:
        if not title or not title.strip():
            return {"ok": False, "error": "任务标题不能为空"}
        items = self._read_json(self.dispatches_path, [])
        rec = self._build_dispatch_record(target_node, title, objective or title, peptide_seq)
        items.insert(0, rec)
        self._write_json(self.dispatches_path, items[:40])
        return {"ok": True, "dispatch": rec}

    def update_session_binding(self, session_slot: str, branch_or_repo: str, status: str = "active") -> dict[str, Any]:
        sessions = self._read_json(self.sessions_path, [])
        updated = None
        for s in sessions:
            if s.get("session_slot") == session_slot:
                if branch_or_repo.strip():
                    s["branch_or_repo"] = branch_or_repo.strip()[:160]
                if status.strip():
                    s["status"] = status.strip()[:40]
                s["updated_at"] = _utc_now()
                updated = s
                break
        if not updated:
            return {"ok": False, "error": f"未知会话槽位: {session_slot}"}
        self._write_json(self.sessions_path, sessions)
        return {"ok": True, "session": updated}

    def snapshot(self) -> dict[str, Any]:
        notify_cfg = self.get_notify_config()
        sample_cg = generate_martini_cgmd_bundle(ntfy_topic=notify_cfg.get("ntfy_topic", ""))
        sessions = self._read_json(self.sessions_path, [])
        migrated = False
        for s in sessions:
            if s.get("session_slot") == "S3" and ("<" in str(s.get("branch_or_repo", "")) or s.get("status") == "ready_to_bind"):
                s["branch_or_repo"] = "hukeying85-ux/0fuye @ arena/32cd826e-0fuye"
                s["status"] = "active"
                s["focus"] = "Martini 3 粗粒化细菌膜打孔 · cgmd_task.json (免合并直接运行) + ntfy 秒推"
                migrated = True
            elif s.get("session_slot") == "S2" and ("<" in str(s.get("branch_or_repo", "")) or s.get("status") == "ready_to_bind"):
                s["branch_or_repo"] = "shaohuawen03-cyber/BioHPC @ mu01"
                s["status"] = "active"
                migrated = True
        if migrated:
            self._write_json(self.sessions_path, sessions)
        return {
            "tri_node_matrix": list(TRI_NODE_MATRIX),
            "ad_network_plan": AD_DUAL_NETWORK_PLAN,
            "session_boundaries": ARENA_SESSION_BOUNDARIES,
            "optimizations": list(ARCHITECTURE_OPTIMIZATIONS),
            "sessions": sessions,
            "dispatches": self._read_json(self.dispatches_path, [])[:20],
            "notify_config": notify_cfg,
            "default_cgmd_bundle": sample_cg,
            "updated_at": _utc_now(),
        }
