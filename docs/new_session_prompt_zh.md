# 新会话提示词 + 本分支安装手册

> 用法：新开一个对话，把 **第 1 节**整段复制粘贴进去，它就会自己去装、去连、去跑。
> 需要改的只有两处：台式机 IP（可留空，让它自己从信箱里读）和你想做的事。

---

## 1. 直接粘进新对话的提示词（整段复制）

```text
你是 CGMD 项目的执行代理。台式机（Windows 11 + RTX A4000 + 原生 GROMACS 2025.1 CUDA）
已经装好值守程序，你不用碰它的键盘，也不要让我手动敲命令。

【仓库】
  github.com/hukeying85-ux/0fuye   分支 arena/32cd826e-0fuye
  沙箱内先：git clone -b arena/32cd826e-0fuye https://github.com/hukeying85-ux/0fuye && cd 0fuye

【第一步：30 秒确认链路（必做，不要跳过）】
  cd 0fuye
  python3 -m core.hub_mailbox run --kind ping --timeout 300
  期望：status=ok，summary 里出现 "DESKTOP-IEUDGS5 alive, gmx 2025.1"，
        detail 里有 gpus / lan / bridge_port。
  如果返回 timeout 或 lost：说明台式机值守没跑，直接告诉我，
  并把 results/status/hub_mailbox.json 的 state / log_tail 原文贴给我，不要自己猜。

【第二步：要用 GPU 就跑这个，不要自己写脚本】
  python3 -m core.hub_mailbox run --kind smoke --json-args '{"ps": 100}' --timeout 1800
  验收标准（全部满足才算成功，逐条核对 detail.report）：
    status            = ok
    ps_completed      = 100
    mdrun.finished    = true
    stages 里 mdrun-md-gpu 的 returncode = 0
    software.gromacs.version = 2025.1 且 accelerator = gpu
  结果同时落在 results/status/gmx_smoke.json（git 里可查）。

【其余可用任务（都用同一入口）】
  --kind selfcheck    18 项自检
  --kind sync         让台式机同步代码/重部署 Arena Desk
  --kind gmx --arg --version        白名单内的 gmx 子命令
  --kind smoke --json-args '{"ps": 500}'   跑 500 ps
  python3 -m core.hub_mailbox ls            看队列
  python3 -m core.hub_mailbox show <id>     取某单结果

【同一局域网时（快，秒级，可选）】
  python3 -m core.desk_bridge ping --host <台式机IP>
  python3 -m core.desk_bridge smoke --host <台式机IP>
  IP 从 ping 结果的 detail.lan 里取（形如 192.168.x.x）。
  连不上就退回信箱总线，不要卡在这里。

【硬规则（违反等于白做）】
  1. 绝不 switch 到别的分支；只推 arena/32cd826e-0fuye。
  2. 不要 git add -A（会把台式机侧的 results/status 卷进冲突）；
     只 add 你自己改过的文件，推之前先 git pull --rebase。
  3. PowerShell 脚本必须纯 ASCII，且不能周期性弹控制台窗口。
  4. 轨迹类大文件（.xtc/.trr/.tpr/.gro/.edv 等）一律不进 git；
     只回传 < 1 MB 的 summary_metrics.json 和矢量图。
  5. 这个工作站用的是 **Windows 原生 gmx.exe**，不是 WSL；
     任何方案都不要依赖 WSL / Python / Martini 文件去跑烟测。
  6. 不要让我手动执行命令。卡住了就自己查 results/status/*.json 和日志再来一次。
  7. 测试基线：PYTHONPATH=$PWD:$PWD/code/cgmd:$PWD/code/federation \
     MPLBACKEND=Agg python3 -m pytest tests -q  → 必须 159 passed 以上。

【我想做的事】
  <在这里写你的需求，例如：把 Martini 3 POPE:POPG=3:1 的膜孔体系跑到 1 µs；
   或者：帮我看看现在 576 ns/day 还能不能再快>

先按上面跑完第一步和第二步，把关键数字用表格汇报给我，再开始我要的正事。
```

---

## 2. 台式机侧的一次性安装（本分支）

> 已经装过可以跳过；换机器/重装系统时照这个来。全程**普通权限** PowerShell，不弹窗。

### 2.1 拿到代码

```powershell
git clone -b arena/32cd826e-0fuye https://github.com/hukeying85-ux/0fuye C:\cgmd\0fuye
cd C:\cgmd\0fuye
```

### 2.2 引导（写配置 + 建计划任务 + 自检）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\skills\cgmd-hub\bootstrap_desktop.ps1 `
  -RepoPath C:\cgmd\0fuye -Branch arena/32cd826e-0fuye
```

它会做四件事：写 `skills/cgmd-hub/config/cgmd_hub.local.json`（已被 gitignore）、
编译静默启动器 `CGMDHub.exe`（`/target:winexe`）+ VBS 包装、注册每 60 s 的计划任务
`CGMD-Hub-Poll`、最后跑一遍 18 项自检。**最后一行必须是「成功」**，否则先别往下走。

### 2.3 本分支新增的三块能力（配置项）

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

### 2.4 局域网直连（可选，让笔记本秒级调用）

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
| 100 ps（50000 步 × 0.002 ps） | **21–22 s 端到端**，`mdrun` 15–16 s，**576 ns/day** |
| 加速 | `-nb gpu -gpu_id 0`，失败自动回退 CPU |
| 从派活到拿到回执 | 30.9 s（信箱总线，含 60 s 轮询内的等待） |
| 自愈 | 值守自己开信箱分支、自己排 ping 自测、自己按期复验 100 ps |

已知的 Windows 坑（脚本已内置兜底）：这台机器的 `gmx grompp` 读自带 `oplsaa.ff`
会 `0xC0000005`，脚本自动改用参数全内联的 SPC 拓扑重跑，并把原因写进报告
`notes` 和 `system.topology.reason`。

---

## 5. 出问题先看这三处

| 现象 | 先看 |
| --- | --- |
| 派活没反应 | `results/status/hub_mailbox.json` → `state` `queued` `inbox` `attempts` `log_tail` |
| 100 ps 失败 | `results/status/gmx_smoke.json` → `stage_error` + `stages[].returncode` / `output_tail` |
| 值守像停了 | `results/status/hub_heartbeat.json` 的 `at`（超过 90 min 没变就是真停了） |
| 局域网连不上 | 台式机 `state/bridge-*.log`；先试 `core.hub_mailbox ping` 确认值守活着 |
| 面板/手机页/开机动画 | 看 `results/status/desktop_selfcheck.json` 的 `desk-http` 那行：它会把 `/mobile`、`/assets/boot-mascot.jpg`、`/style.css` 的 HTTP 码直接列出来 |
| 改了 `code/panel/*` 没生效 | 面板进程要重启：`python3 -m core.hub_mailbox run --kind sync --json-args '{"desk": true}'`（回执里应有 `panel restarted`） |

**已修复、不要再回退的坑**：① PowerShell 里 `[switch]$Json` 和局部 `$json` 是同一个变量，赋值必崩；
② 这台机器没有 E: 盘，任何 `E:\...` 都必须走 `resolve_win_path()` / `Resolve-AnyDrive`；
③ `dsh-boot.mp4` / `dsh-bg.mp4` 与 `jobbeacon/pwa/` 素材不在仓库里，靠 poster + `#boot-fallback` + 内建手机页兜底；
④ 自检必须优先报原生 `gmx.exe`，不要拿 WSL 里那个 CPU 版 2018.1 当主力。
