# 解放双手：自愈值守 · 万能信箱 · 局域网直连

> 目标：**你不用再敲任何命令**。台式机自己发现问题、自己修、自己跑、自己回报；
> 任何会话、任何分支、任何机器都能直接把活派给它；同一个局域网里笔记本还能秒级直连。

---

## 1. 它自己会做什么（不需要你介入）

| 场景 | 以前 | 现在 |
| --- | --- | --- |
| 上一轮轮询被 `wsl.exe` 卡死、锁文件残留 | 值守静默数小时，要人上去删 `poll.lock` | 每轮检查 `state/poll.pid`：进程已死 → 立刻破锁；活着但锁龄超 90 min → `taskkill` 后破锁并继续 |
| 100 ps 没跑过 / 上次失败 / 结果超过 24 h | 要人手动排请求 | `smoke_auto`：自动排一次 100 ps，失败退避 180 min 再试，成功则 24 h 后再验 |
| 代码有更新 | 要人提醒 `git pull` | 每轮 `fetch` + `reset --hard origin/<branch>`（脏工作区先发布结果） |
| 手机不知道结果 | 要人查 | ntfy 推送 + `results/status/gmx_smoke.json` 进 git |
| 别的会话想用这台 GPU | 要人转述、要改分支 | 信箱总线，见第 2 节 |

自愈状态都在 `state/`（不进 git），对外可见的只有 `results/status/*.json`
（`gmx_smoke.json`、`hub_heartbeat.json`、`hub_mailbox.json`、`desktop_selfcheck.json`）。

可调参数（`skills/cgmd-hub/config/cgmd_hub.local.json`）：

```json
"stale_lock_minutes": 90,
"smoke_auto": true,
"smoke_interval_hours": 24,
"smoke_retry_minutes": 180,
"mailbox_enabled": true,
"mailbox_jobs_per_poll": 1,
"mailbox_ref": "hub/mailbox"
```

---

## 2. 信箱总线：任何会话 → 台式机 → 结果（走 git，不用登录）

请求和回执放在**独立分支** `hub/mailbox` 上，所以：

* 调用方永远不会提交到自己的工作分支 → **再也不会出现 rebase 冲突**（上一轮反复卡的就是这个）；
* 任何会话 / 任何分支 / 任何机器都能用（沙箱、笔记本、手机都行）；
* 台式机每轮（60 s）取 1 个任务，跑完把结果写回同一个 ref。

```
hub/mailbox
├── inbox/<id>.json     请求  cgmd.mailbox.request.v1
└── outbox/<id>.json    结果  cgmd.mailbox.result.v1
```

### 用法

```bash
# 1) 问一声（10 秒内回，验证链路）
python3 -m core.hub_mailbox run --kind ping --timeout 300

# 2) 让台式机跑 100 ps（GPU），阻塞直到拿到结果
python3 -m core.hub_mailbox run --kind smoke --timeout 1800

# 3) 在台式机上执行任意 gmx 子命令（白名单内，非交互）
python3 -m core.hub_mailbox run --kind gmx --arg --version
python3 -m core.hub_mailbox run --kind gmx --arg solvate --arg -cs --arg spc216.gro --arg -box --arg 3 --arg 3 --arg 3

# 4) 自检 / 同步
python3 -m core.hub_mailbox run --kind selfcheck --timeout 600
python3 -m core.hub_mailbox run --kind sync --timeout 600

# 5) 只看队列、只取结果
python3 -m core.hub_mailbox ls
python3 -m core.hub_mailbox wait 20261029T131500-1a2b --timeout 900
python3 -m core.hub_mailbox show 20261029T131500-1a2b
```

返回结果示例（所有传输共用同一 schema）：

```json
{"schema":"cgmd.mailbox.result.v1","id":"...","kind":"smoke","status":"ok",
 "summary":"gmx 2025.1: 100 ps integrated on gpu","seconds":23.5,
 "detail":{"report":{...},"artifact":"results/status/gmx_smoke.json"},
 "logs_tail":["..."]}
```

`status` 取值：`ok` `fail` `error` `unsupported` `timeout` `lost`。
`lost` / `timeout` 说明台式机没取到或还在忙——不会让你无限等。

### 安全边界

| 类别 | 说明 |
| --- | --- |
| `gmx` | 只允许白名单子命令（`mdrun` `grompp` `solvate` `energy` `check` …），参数里的 `; & | < > \`` `$(` 一律拒绝 |
| `shell` | **默认关闭**，必须用 `-AllowShell` 启动或配置 `"allow_shell": true` |
| 其他 | 未知 `kind` 会立刻回 `unsupported`，不会执行 |

---

## 3. 局域网直连：笔记本 ↔ 台式机（毫秒级）

信箱走公网 git，最慢要等一个轮询周期（≤60 s）。同一个 WiFi 下就直接打：

```powershell
# 台式机上跑一次（普通权限即可，不用管理员）
powershell -NoProfile -ExecutionPolicy Bypass -File C:\cgmd\0fuye\skills\cgmd-hub\runner\Invoke-CgmdBridge.ps1
```

监听 `0.0.0.0:8765`，接口只有三个：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | 活着吗、gmx 版本、显卡 |
| GET | `/status` | 最近一次 100 ps 报告 + 心跳 |
| POST | `/job` | `{"kind":"ping|smoke|selfcheck|gmx","args":{...}}` |

笔记本侧（任意有 Python 的机器）：

```bash
python3 -m core.desk_bridge ping   --host 192.168.1.23
python3 -m core.desk_bridge status --host 192.168.1.23
python3 -m core.desk_bridge smoke  --host 192.168.1.23 --timeout 900
python3 -m core.desk_bridge gmx    --host 192.168.1.23 -- --version
```

怎么知道台式机的 IP？让信箱告诉你（返回里带 `lan` 和 `bridge_port`）：

```bash
python3 -m core.hub_mailbox run --kind ping --timeout 300 | python3 -c "import json,sys;print(json.load(sys.stdin)['detail']['lan'])"
```

**访问控制**：回环与 `10/8`、`172.16/12`、`192.168/16` 直接放行；其他来源必须带
`X-CGMD-Token`（配置里 `bridge_token`）。`shell` 依旧默认关闭。

**首次放行端口**（可选，需要一次管理员权限，之后永久有效）：

```powershell
netsh advfirewall firewall add rule name="CGMD bridge" dir=in action=allow protocol=TCP localport=8765
# 或者：Invoke-CgmdBridge.ps1 -OpenFirewall（同样要管理员）
```

不做这一步也不影响互通——退回信箱总线即可，只是慢一点。

---

## 3.5 已经实测通过的部分（2026-10-29 13:21，DESKTOP-IEUDGS5）

| 验证项 | 结果 |
| --- | --- |
| 自动开信箱分支 | 台式机自己 push 出 `hub/mailbox`（`mailbox: open the queue`） |
| 自测任务 | 台式机**自己**排 ping → 自己接单 → 0.79 s 完成 → 回执 `outbox/selftest-20261029T132102.json` |
| 回执内容 | `gmx 2025.1`、`NVIDIA RTX A4000 596.71 16376 MiB`、48 线程、`ready: true` |
| 局域网发现 | 回执里直接给出 `lan: [100.84.137.117, 172.20.32.1, 192.168.110.226, 172.17.240.1]`、`bridge_port: 8765` |
| 值守对外可见 | `results/status/hub_mailbox.json` 的 `state` 会在 `ran` / `no-branch` / `created` / `repaired` / `error` 之间如实变化 |
| 从会话派 100 ps | `20261029T063704-9a27`：14:37:56 接单 → **29.85 s 回执**，`status ok`、`ps 100`、`mdrun-md-gpu rc=0`、576 ns/day |
| 端到端阶段 | solvate → grompp(em, 自带 FF 崩→内联兜底) → mdrun-em → grompp(md) → **mdrun-md-gpu 15.6 s** → `Finished mdrun` |

路上踩掉的两个坑（代码已修，留档备查）：

1. `git mktree` 经 PowerShell 管道收到的行尾带 CR，生成了名为 `README.md\r` 的文件；Windows 无法检出
   （`invalid path 'README.md?'`），worktree 建不起来。现在 mktree 从文件喂 LF，且分支不可用但为空时
   会自动重建（绝不强推有真实任务的分支）。
2. 回执文件带 `generated_at`，最初每 60 s 就产生一个提交。现在只在「状态/队列长度/最近回执」真正变化时发布。
3. `ConvertFrom-Json` 读回来的台账是 `PSObject`，PS 5.1 索引它会抛「无法对 PSObject 类型的对象进行索引」；
   而这一抛发生在「回执已写盘、请求已删除、还没 push」的中间，于是下一轮又把请求恢复、看到本地已有回执、
   直接 `continue` 丢掉——调用方等了 15 分钟。现在：读回来的字典先转 hashtable；**发现本地已有回执就立刻发布**
   而不是丢请求；整轮崩了也要把已完成的回执推上去；同一单最多试 3 次，超了就回一条 `error` 解放调用方。

---

## 3.6 桌面（Arena Desk）为什么一直"没修好"——三个根因

这三条全部是**代码里从未提交的素材 + 一个 PowerShell 作用域坑**，与显卡、网络、权限无关。

| # | 现象 | 根因 | 修法 |
| --- | --- | --- | --- |
| 1 | 自检永远失败、`results/status/desktop_selfcheck.json` 一直是那个 `False` | `Test-CgmdHub.ps1` 的 `param([switch]$Json)` 与末尾 `$json = $report \| ConvertTo-Json` **是同一个变量**（PowerShell 变量名不区分大小写），给 `[switch]` 赋字符串必抛 `无法转换为 SwitchParameter`，于是**每次自检都在写报告前崩掉**；那个 `False` 又让所有读它的工具继续抛 `无效的 JSON 基元` | 局部变量改名 `$reportJson`；`if ($Json.IsPresent)`；所有 `Read-JsonFile` 加 try/catch；值守每轮自动删除非 JSON 的状态文件并提交删除 |
| 2 | 开机动画只有黑屏 14.5 s 然后跳过 | `index.html` 引用的 `dsh-boot.mp4` / `dsh-bg.mp4` **从来没有进过仓库**（`git log --all` 查无此文件），`<video>` 404，看门狗到点才退出 | 视频加 `poster`（现成的 `boot-mascot.jpg` / `wallpaper-anime.jpg`）+ 新增 `#boot-fallback` 图层（吉祥物浮动、光晕呼吸、进度条 2.2 s），2.4 s 后自然淡出；`readyState===0` 也能兜住不触发 `onerror` 的情况 |
| 3 | 手机扫码进去是 404、桌面里一堆"未安装 / E:\0writing" | `code/panel/jobbeacon_src/jobbeacon/pwa/` 也从未提交；`desktop_ops.py`、`deploy.ps1`、`launch_panel.ps1`、`catalog.json` **全都假设有 E: 盘**（参考笔电有，台式机没有） | 内建手机伴侣页（`/mobile` + manifest + sw.js + 图标复用现有 PNG）；新增 `resolve_win_path()` / `app_root()` / `app_drive()`，把 `E:\...` 自动映射到真实存在的盘；`Resolve-AnyDrive` 同样处理 PowerShell 侧；一键安装默认装到 Arena Desk 自己所在的盘 |

**另外两个使"改了却没生效"的坑**：

* 面板 `server.py` 改了但**进程没重启**，旧的还在内存里跑 → `sync` 任务现在会 `taskkill ArenaDesk.exe` + 重启计划任务 `arena-desk-panel`，并轮询 `127.0.0.1:18765` 确认回来（回执里直接写 `panel restarted`）。
* 自检只看 WSL 里的 `gmx`（2018.1、无 CUDA），把主力引擎说成 CPU 版 → 现在**永远优先探测原生 `gmx.exe`**，报告里同时给出 `gromacs_native` / `gromacs_wsl` / `gromacs_gpu`；Martini 依赖缺失对原生 GPU 路径只降级为 warn。

修完后的真实自检（2026-10-29 14:53，DESKTOP-IEUDGS5）：**18 项 15 pass / 3 warn / 0 fail**

```
pass gromacs    GROMACS 2025.1 native windows (GPU support: CUDA) | wsl 2018.1 (cpu only) unused
pass desk-http  127.0.0.1:18765 | version 2.8.0 | 8 tasks | /mobile 200 | /assets/boot-mascot.jpg 200 | /style.css 200
pass gmxrun     ok | gmx 2025.1 | 100 ps | 2026-10-29T14:37:58+08:00
warn python     missing: vermouth, insane, MDAnalysis, matplotlib | 只影响 Martini 肽链流水线
warn tools      同上
warn martini3   同上
```

`desk-http` 那一行现在会**直接证明**三个页面/资源都是 200——重启是否生效、开机动画素材在不在，看这一行就够。

---

## 4. 两条链路怎么选

```
同局域网、要秒回、要立刻看 gmx 输出   →  局域网桥  core.desk_bridge.py
任何网络、要可靠、要留档、要跨会话     →  信箱总线  core.hub_mailbox.py
两者都挂了                            →  ntfy 推送照旧（arena-beacon-95bc796a66）
```

设计上两者返回同一个 `cgmd.mailbox.result.v1`，脚本可以「先试桥、失败退信箱」：

```python
from core import desk_bridge, hub_mailbox
try:
    result = desk_bridge.smoke("192.168.1.23", timeout=900)
except desk_bridge.BridgeError:
    job_id = hub_mailbox.send(".", "smoke", {"ps": 100})
    result = hub_mailbox.wait(".", job_id, timeout=1800)
```
