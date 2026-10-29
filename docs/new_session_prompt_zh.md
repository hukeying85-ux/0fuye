# 新会话提示词 + 连接手册（安装已完成）

> 用法：新开一个对话，把 **第 1 节**整段复制粘贴进去。
> 你只需要在最后一行写「我想做的事」，其余它自己会跑。
>
> **台式机基座已经装好了**——`CGMD-Hub-Poll`（60 s 轮询）+ Arena Desk 面板（`:18765`）+ 局域网桥（`:8765`）。
> 所以新会话要做的是**连接**，不是安装：不存在「再装一遍」，
> 也不存在「让你粘贴命令」这一步，两者都写进了下面的硬规则。
> 真的换了新机器才需要第 2 节的冷启动引导，那也是我做，不是你敲。

---

## 1. 直接粘进新对话的提示词（整段复制，v2）

> v2 相对 v1 的改动：环境事实前置、加「零粘贴」硬规则、加跨仓禁令（不要再造第二套基座）、
> 加速度验收的 JSON 路径、加实测基线数字。三项都是为了不再出现「跑完还要你贴一行 PowerShell」。

```text
你是 CGMD 项目的执行代理。这台「台式机」= DESKTOP-IEUDGS5（Windows 10 + RTX A4000 16 GB +
原生 GROMACS 2025.1 CUDA，装在 F:\gromacs-2025.1-SM86）。

【任务是"连接"，不是"安装"】
  基座已经装好并在跑：CGMD-Hub-Poll（60 s 轮询）+ Arena Desk 面板（127.0.0.1:18765）+ :8765 局域网桥。
  不要再装第二套、不要重新 bootstrap、不要建计划任务；你的工作是连上它、派活、验收、汇报。

【最重要的一条：你不需要我粘贴任何东西】
  · 台式机上的所有动作（同步代码、部署面板、注册/修复计划任务、重启、跑 gmx、拉开机动画）
    都通过下面的信箱总线由你自己发起。我不是你的手，别给我命令行。
  · 唯一例外：这是一台**从没装过基座**的全新机器。此时也只能由我一次性装；
    若真遇到这种冷启动，先跑一次 ping，再用 detail 证明「这台机器确实没有值守」，
    然后**只给一条**命令并说明为什么这次必须我动手。不要为了省事就退回到"你贴一下"。

【你的运行环境（别浪费时间探测）】
  · 沙箱 = Linux(Debian)，没有 Windows / PowerShell / GPU，不要试图本地跑 gmx 或 .ps1。
  · 沙箱出网只放行 github.com / codeload / api.github.com / pypi / npm ——
    **连不到台式机的 192.168.x.x / 100.84.x.x**。所以这里只走信箱总线，
    不要拿 core.desk_bridge 试 :8765（那是笔记本在同一个 Wi-Fi 下才用的）。试了必超时，浪费 10 分钟。
  · 台式机没有 E: 盘；面板叫 Arena Desk，服务在 127.0.0.1:18765。

【仓库 / 拿代码】
  git clone -b arena/32cd826e-0fuye https://github.com/hukeying85-ux/0fuye && cd 0fuye
  只读这个仓库。你派的活走独立的 hub/mailbox 引用，**不需要也不许**往任何分支提交/推送。

【第 0 步：先读能力卡（1 秒，别跳过）】
  python3 -m core.hub_mailbox caps
  它会直接告诉你：台式机是否存活、心跳多久前、GROMACS/GPU、最近一次 18 项自检和 100 ps 的速度、
  9 种任务各自干什么、坏了按什么顺序修。**先看它，再决定跑什么。**

【第 1 步：30 秒确认链路（必做）】
  python3 -m core.hub_mailbox run --kind ping --timeout 300
  期望：status=ok，summary 形如 "DESKTOP-IEUDGS5 alive, gmx 2025.1, 1 gpu(s)"，
        detail 里有 gpus / lan / bridge_port。
  返回 timeout / lost：先 deskdiag 再 deskfix 再 sync（见下面「坏了怎么修」），
  仍不行才如实告诉我「值守停了」，并附 results/status/hub_mailbox.json 的 state/log_tail 原文。
  不要自己猜、不要写新脚本去替代值守。

【第 2 步：GPU 烟测 100 ps（要动算力就跑这个）】
  python3 -m core.hub_mailbox run --kind smoke --json-args '{"ps": 100}' --timeout 1800
  验收逐条核对（字段层级已经踩过坑，照抄路径）：
    result.status == "ok"
    result.detail.report.ps_completed == 100
    result.detail.report.mdrun.finished == true
    result.detail.report.mdrun.performance_ns_per_day > 0        (实测 576 ns/day 量级)
    result.detail.report.accelerator == "gpu"                     (不在 report.progress 里)
    stages 里 mdrun-md-gpu 的 returncode == 0
  结果同时落在 results/status/gmx_smoke.json（git 可查）。

【全部可用任务（同一入口，caps 里也有说明）】
  caps（子命令，不是 --kind）  上面那张能力卡；本地读文件、不发单
  --kind ping              活着吗
  --kind selfcheck         18 项自检（原生 gmx / CUDA / 面板 / 素材）
  --kind smoke --json-args '{"ps": 500}'    真实 GROMACS，默认 100 ps
  --kind sync --json-args '{"desk": true}'  台式机拉最新代码 + 重部署面板 + 重启（回执含 panel restarted）
  --kind gmx --arg --version                白名单 gmx 子命令
  --kind deskdiag          文件哈希 repo↔desk、计划任务、页面 200、开机回执、锁屏状态
  --kind deskfix           重挂登录触发器 + 保面板 + 立刻拉一次开机动画
  python3 -m core.hub_mailbox ls / show <id>     看队列 / 取某单结果

【坏了怎么修（顺序固定，不用问我要命令）】
  deskdiag  → 看 drift / tasks / boot_ack / session，先定性
  deskfix   → 触发器、面板、动画
  sync desk → 代码版本不对时（drift 不为 0）
  selfcheck → 最后确认 18 项是 15 pass / 3 warn / 0 fail（warn 是 Martini python 依赖，不影响接单）

【跨仓 / 别的项目怎么办（这条是硬禁令）】
  · 台式机上**只有这一套基座**（CGMD-Hub-Poll + Arena Desk + :8765）。不要再装第二套、
    不要克隆别的仓库去建 desktop-base、不要写第二份轮询脚本——上一轮有会话这么干，
    结果自删了自己的 watcher、还为了拿凭据让用户在机器上粘命令。
  · 别的项目要用台式机：把本仓库当客户端，`python3 -m core.hub_mailbox` 派活即可；
    需要"新任务类型"就在 0fuye 里加一个 kind 再 sync，而不是另起炉灶。
  · 别的仓库自己的 GitHub 凭据问题，不要在这台机器上重新登录/重置 token。

【如果你的会话不在这个仓库里（token 只覆盖你自己那个仓库）】
  Arena 给每个会话的 GH_TOKEN 只对"会话所在的那个仓库"有写权限，往 0fuye 推 `hub/mailbox`
  会直接 403 `Resource not accessible by integration`——这不是台式机掉线，别误报。
  正确姿势（两条命令，仍然不用我动手）：
    git clone https://github.com/hukeying85-ux/0fuye.git /tmp/desk        # 公开仓库，只读客户端
    python3 -m core.hub_mailbox --repo <你自己的 checkout> run --kind ping --read-repo /tmp/desk
  也就是：**往你自己的仓库的 `hub/mailbox` 派单，从 0fuye 读回执**。
  台式机会匿名拉取对端仓库的信箱（`peer_repos`，我已配好），执行完把同一单号的回执写进 0fuye，
  所以 `--read-repo /tmp/desk` 用同一个 id 就能取到。前提是你的仓库在 `peer_repos` 里；
  不在的话让我用 `--kind deskfix --json-args '{"peer_repos":["hukeying85-ux/你的仓库"]}'` 加一行，同样不用你敲。

【硬规则（违反等于白做）】
  1. 不许让我粘贴/执行任何命令，也不许说"请你在台式机上运行…"。上面的任务种类足够覆盖部署、修复、自检。
  2. 不改 0fuye 的任何分支、不 git add -A。派活只写 `hub/mailbox`（独立引用）或你自己仓库的信箱；
     要改 0fuye 的代码，就在你自己的分支上改，走 PR，别直接推 arena/32cd826e-0fuye。
  3. PowerShell 脚本必须纯 ASCII，且不能周期性弹出控制台窗口；计划任务注册必须带 -Trigger
     （LastTaskResult 267011 + LastRunTime 1999-11-30 = "从未运行"，不是"部署旧了"）。
  4. 轨迹类大文件（.xtc/.trr/.tpr/.gro/.edv）一律不进 git；只回传 < 1 MB 的 summary_metrics.json 和矢量图。
  5. 这台机器用的是 Windows 原生 gmx.exe，不是 WSL；任何方案都不要依赖 WSL / Python / Martini 文件跑烟测。
  6. 实测基线（2026-10-29，拿它对比）：ping 0.9 s；100 ps 端到端 21–31 s、mdrun 14–16 s、
     576 ns/day；自检 18 项 15 pass / 3 warn / 0 fail；面板 v2.8.0。
     数字差太多先 deskdiag，不要直接说"机器变慢了"。

【汇报格式】
  先一张表：主机 / 值守心跳 / GPU / GROMACS / 烟测 ps、ns·day⁻¹ / 自检 pass-warn-fail / 工单号，
  再写「我要做的事」的进展。凡是没实测的数字，标"未验证"，不要编。

【我想做的事】
  <在这里写你的需求，例如：把 Martini 3 POPE:POPG=3:1 的膜孔体系跑到 1 µs；
   或者：帮我看看现在 576 ns/day 还能不能再快；或者：台式机开机动画再看一眼>
```

---

## 1.1 更短的一句话版（可以，但只当封面语）

你原本那句可以留作开场，但它自己不构成提示词——两个实测会话里，正因为只给了这一句，
一个去猜「安装指什么」，另一个干脆自己造了一套基座并最终把命令交回给你。建议这样发：

> 安装 github.com/hukeying85-ux/0fuye 分支 arena/32cd826e-0fuye 的台式机基座，
> 通过它打通 DESKTOP-IEUDGS5，全程你来操作，我一个字都不粘。
> 然后照 docs/new_session_prompt_zh.md 第 1 节执行；
> 我不接受"请你在台式机上运行…"这类要求。

---

## 1.2 从别的仓库连接（跨仓派活，403 的正解）

**为什么会 403。** Arena 给每个云端会话签发的临时 token 只对"会话所在的那个仓库"有写权限。
实测（2026-10-29）：

| 请求 | 结果 |
| --- | --- |
| `POST /repos/hukeying85-ux/JevHarness/git/blobs` | `201 Created` |
| `POST /repos/hukeying85-ux/0fuye/git/blobs` | `403 Resource not accessible by integration` |
| `git push` 到 `JevHarness`（本会话在 0fuye） | `403`（对称，反过来也一样） |
| `git ls-remote` / `git clone` 对方的公开仓库 | **正常**（读是开放的） |

所以"任何会话 → 台式机"不能靠让对方往 0fuye 推。协议改成：**各写各的、台式机居中**。

```
你自己的仓库 hub/mailbox ──inbox/<id>.json──▶ 台式机（匿名拉取 peer_repos）
                                               │ 执行（GPU / GROMACS）
                                               ▼
                       0fuye hub/mailbox ──outbox/<id>.json──▶ 你用同一个 id 读回执
```

调用方（以 JevHarness 为例，全程不需要你敲命令）：

```bash
git clone https://github.com/hukeying85-ux/0fuye.git /tmp/desk     # 公开仓库，只读客户端
cd <你自己的 checkout>
python3 -m core.hub_mailbox --repo . run --kind ping --read-repo /tmp/desk
python3 -m core.hub_mailbox --repo . run --kind smoke --json-args '{"ps": 100}' --read-repo /tmp/desk
```

- `--repo .` = 请求写进**你自己仓库**的 `hub/mailbox`（你有写权限，201）。
- `--read-repo /tmp/desk` = 回执从 **0fuye** 读（公开，匿名可读），同一单号。
- 台式机侧对应配置只有一行 `peer_repos`，由 `deskfix` 写入，不用你碰机器：

```bash
python3 -m core.hub_mailbox run --kind deskfix \
  --json-args '{"peer_repos": ["hukeying85-ux/JevHarness"]}'
```

- 也支持 `owner/repo#ref` 指定别的分支名（自测时用过 `hukeying85-ux/0fuye#peer-test`）。
- 台式机**匿名**拉取（`-c credential.helper=`）——所有对端仓库都是公开的，不需要在对端再配凭据，
  也就不会出现"为了拿 token 让用户在机器上粘命令"那种事。私有仓库会自动退回本机凭据助手再试一次。
- 回执落盘在 0fuye 的 `outbox/<id>.json`，带 `peer` 字段写明来自哪个仓库、哪个分支。
- 幂等：同一单号只执行一次（台式机 ledger + 0fuye 里已有的回执双重去重），
  所以对端那封请求**留在原地也没关系**，不需要对端删除、也不需要给它写权限。

---

## 2. 台式机侧的一次性安装（本分支）

> **这一段不是给你的操作说明**，是"我（代理）在台式机上做过什么"的留档。
> 正常情况你不会用到它：机器上已经有值守在跑，`caps` 一看就知道。
> 只有换新机器 / 重装系统这种「冷启动」才需要一次性的引导，
> 而那次也可以由代理通过远程/已有通道完成；你要做的只是别自己动手。

### 2.0 先判断是哪种情况

| 现象 | 结论 | 谁来做 |
| --- | --- | --- |
| `caps` 里 `desk.alive = true`、`heartbeat_age_min < 5` | 基座活着，直接派活 | 全自动，无人介入 |
| `ping` 超时，但 `results/status/hub_heartbeat.json` 有历史 | 值守可能停了 | 代理跑 `deskfix` / `sync`，仍不行才报「机器需要看一眼」 |
| 从没有过 `hub_heartbeat.json`、`C:\cgmd\0fuye` 不存在 | 真·冷启动 | 一次性引导，见 2.2–2.5 |


### 2.2 拿到代码（冷启动时由代理执行一次）

```powershell
git clone -b arena/32cd826e-0fuye https://github.com/hukeying85-ux/0fuye C:\cgmd\0fuye
cd C:\cgmd\0fuye
```

### 2.3 引导（写配置 + 建计划任务 + 自检）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\skills\cgmd-hub\bootstrap_desktop.ps1 `
  -RepoPath C:\cgmd\0fuye -Branch arena/32cd826e-0fuye
```

它会做四件事：写 `skills/cgmd-hub/config/cgmd_hub.local.json`（已被 gitignore）、
编译静默启动器 `CGMDHub.exe`（`/target:winexe`）+ VBS 包装、注册每 60 s 的计划任务
`CGMD-Hub-Poll`、最后跑一遍 18 项自检。**最后一行必须是「成功」**，否则先别往下走。

### 2.4 本分支新增的三块能力（配置项）

`skills/cgmd-hub/config/cgmd_hub.local.json` 里加上（缺省值就够用，写出来只是让你好改）：

```json
"mailbox_enabled": true,
"mailbox_ref": "hub/mailbox",
"mailbox_jobs_per_poll": 1,
"mailbox_max_attempts": 3,
"smoke_auto": true,
"smoke_interval_hours": 24,
"smoke_retry_minutes": 180,
"stale_lock_minutes": 90,
"allow_shell": false,
"bridge_port": 8765,
"bridge_token": ""
```

| 项 | 作用 |
| --- | --- |
| `mailbox_*` | 任何会话通过 `hub/mailbox` 分支派活；每轮最多接 1 单；3 次做不完就回一条 error，绝不让调用方干等 |
| `smoke_auto` / `smoke_interval_hours` | 没跑过 / 上次失败 / 超过 24 h 就自动跑 100 ps；失败退避 3 h |
| `stale_lock_minutes` | 上轮崩了留下的锁，90 min 后或进程已死时自动破锁 |
| `allow_shell` | **默认 false**，需要远程执行任意命令时才开 |
| `bridge_port` | 局域网直连端口 |

配置改完重启一次计划任务即生效：

```powershell
Start-ScheduledTask -TaskName CGMD-Hub-Poll
```

### 2.5 局域网直连（可选，让笔记本秒级调用）

```powershell
# 台式机：普通权限启动桥
powershell -NoProfile -ExecutionPolicy Bypass -File C:\cgmd\0fuye\skills\cgmd-hub\runner\Invoke-CgmdBridge.ps1

# 想开机自启，就在计划任务里加一条（同样走静默启动器，不弹窗）
```

让**别的机器**能连进来，需要一次管理员权限放行端口（一次性，之后永久）：

```powershell
netsh advfirewall firewall add rule name="CGMD bridge" dir=in action=allow protocol=TCP localport=8765
```

或者直接 `Invoke-CgmdBridge.ps1 -OpenFirewall`（同样要管理员）。放行范围建议只在
家里的网段：`remoteip=192.168.110.0/24`。

---

## 3. 三条链路的分工与降级顺序

```
同局域网、要秒回        →  core.desk_bridge   (HTTP, <1 s)
任何网络、要留档        →  core.hub_mailbox    (git, ≤60 s)
两条都不通              →  ntfy 推送 + results/status/*.json（台式机自己写）
```

降级写法（新会话里可以直接用）：

```python
from core import desk_bridge, hub_mailbox
try:
    result = desk_bridge.smoke("192.168.110.226", timeout=900)
except desk_bridge.BridgeError:
    job = hub_mailbox.send(".", "smoke", {"ps": 100})
    result = hub_mailbox.wait(".", job, timeout=1800)
```

---

## 4. 已实测的数字（2026-10-29，DESKTOP-IEUDGS5）

| 项目 | 值 |
| --- | --- |
| GROMACS | 2025.1，mixed，AVX2_256，CUDA 12.8 / 驱动 13.2，FFTW3 |
| GPU | NVIDIA RTX A4000 16 GB（驱动 596.71），48 线程 |
| 100 ps（50000 步 × 0.002 ps） | **21–31 s 端到端**，`mdrun` 14–16 s，**576–617 ns/day**（跨会话实测区间，波动来自 GPU 占用） |
| 加速 | `-nb gpu -gpu_id 0`，失败自动回退 CPU |
| 从派活到拿到回执 | 30.9 s（信箱总线，含 60 s 轮询内的等待） |
| 跨仓派活（对端信箱 → 台式机 → 0fuye 回执） | `ping` 一个轮询周期内回；**100 ps GPU 540 ns/day**（2026-10-29 16:31 实测） |
| 自愈 | 值守自己开信箱分支、自己排 ping 自测、自己按期复验 100 ps |

已知的 Windows 坑（脚本已内置兜底）：这台机器的 `gmx grompp` 读自带 `oplsaa.ff`
会 `0xC0000005`，脚本自动改用参数全内联的 SPC 拓扑重跑，并把原因写进报告
`notes` 和 `system.topology.reason`。

---

## 5. 出问题先看这几处

| 现象 | 先看 |
| --- | --- |
| 派活没反应 | `results/status/hub_mailbox.json` → `state` `queued` `inbox` `attempts` `log_tail` |
| 100 ps 失败 | `results/status/gmx_smoke.json` → `stage_error` + `stages[].returncode` / `output_tail` |
| 值守像停了 | `results/status/hub_heartbeat.json` 的 `at`（超过 90 min 没变就是真停了） |
| 局域网连不上 | 台式机 `state/bridge-*.log`；先试 `core.hub_mailbox ping` 确认值守活着 |
| 面板/手机页/开机动画 | 看 `results/status/desktop_selfcheck.json` 的 `desk-http` 那行：它会把 `/mobile`、`/assets/boot-mascot.jpg`、`/style.css` 的 HTTP 码直接列出来 |
| 改了 `code/panel/*` 没生效 | 面板进程要重启：`python3 -m core.hub_mailbox run --kind sync --json-args '{"desk": true}'`（回执里应有 `panel restarted`） |
| 新会话张口就说"请你在台式机上运行…" | 提示词 v2 的硬规则 1 没生效；把 §1.1 那句「我不接受你让我粘命令」补进对话，让它改走 `deskdiag`/`deskfix`/`sync` |
| 会话另建了一套基座（`desktop-base` / 第二份 watcher） | 违反 §1「跨仓禁令」。台式机只允许一条 `CGMD-Hub-Poll` + Arena Desk；多余的按 `schtasks /delete` 清掉，统一回 0fuye 基座 |
| 派活报 `403 Resource not accessible by integration` | 你的会话 token 只覆盖自己那个仓库 → 走 §1.2：往自己仓库的信箱派单，`--read-repo` 读 0fuye |
| 会话想连 `192.168.x.x:8765` 一直超时 | 云端沙箱只放行 github/pypi/npm，局域网桥给笔记本用；云端会话一律走信箱 |
| 跑 pytest 一堆 import 报错 | 沙箱默认没有 matplotlib/numpy：`python3 -m venv /tmp/v && /tmp/v/bin/pip install pytest matplotlib numpy`；基线 **189 passed / 4 skipped** |
| 心跳有、但 `head` 落后 | `caps` 里 `desk.head` 与 `git rev-parse --short HEAD` 不同就是没同步：`--kind sync --json-args '{"desk": true}'` |

**已修复、不要再回退的坑**：① PowerShell 里 `[switch]$Json` 和局部 `$json` 是同一个变量，赋值必崩；
② 这台机器没有 E: 盘，任何 `E:\...` 都必须走 `resolve_win_path()` / `Resolve-AnyDrive`；
③ `dsh-boot.mp4` / `dsh-bg.mp4` 与 `jobbeacon/pwa/` 素材不在仓库里，靠 poster + `#boot-fallback` + 内建手机页兜底；
④ 自检必须优先报原生 `gmx.exe`，不要拿 WSL 里那个 CPU 版 2018.1 当主力。
⑤ 计划任务注册时**必须带 `-Trigger`**：`LastTaskResult 267011` + `LastRunTime 1999-11-30` 表示"从未运行"，
   不是"部署旧了"——先用 `deskdiag` 看哈希（`drift 0` 就说明文件没错），再用 `deskfix` 补触发器；
⑥ 缺 `dsh-boot.mp4` 时 `play()` 是**同步被拒**的，要在碰 `<video>` 之前读 `boot_video_available`，
   绝不能靠 `onerror`/300 ms 兜底（那就是黑闪的来源）；
⑦ 远程/服务上下文拉起的窗口是隐藏的，开机安全阀必须是 **90 s + 等窗口可见**，9.2 s 会报
   `dsh_video_bg_autoforward`；回执 `mode` 只有 `boot_asset_absent*` 才算动画这一环真的过了。
