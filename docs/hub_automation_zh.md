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

### 3.6.1 开机动画为什么"还是没成功"——又是三个根因（已全部修好并实测）

上面第 2 条只解决了"素材缺失时黑屏 14.5 s"，但**动画本身仍然一次都没播过**。三个新根因：

| # | 现象 | 根因 | 修法（都已提交，用户不用敲任何命令） |
| --- | --- | --- | --- |
| 4 | 登录后什么都不发生，`deskdiag` 看到 `arena-desk-boot-demo` 的 `LastTaskResult 267011`、`LastRunTime 1999-11-30` | 计划任务注册时**没带 `-Trigger`**——`267011` 不是"失败"，而是"从未运行过"。部署脚本只在版本升级时 `Start-ScheduledTask` 一次，所以等于永远不自动跑 | `deploy.ps1` 给开机任务挂 `AtLogOn`；`arena-desk-open` 在登录时**禁用**（避免两个窗口抢）；另注册无触发器的 `arena-desk-open-manual` 供手动开窗。现场用新任务 `deskfix` 一次性兜底 |
| 5 | 动画"闪一下就黑"，回执 `mode: dsh_video_autoplay_fallback` | `dsh-boot.mp4` / `dsh-bg.mp4` **仓库和台式机都没有**，`<video>.play()` 同步被拒；旧代码在拒绝时直接 `enterWorkspace(300, ...)`——300 ms 就撤图层，看起来就是黑闪 | 服务端 `/api/state` 新增 `boot_video_available` / `wallpaper_available` / `boot_fallback_art` / `wallpaper_fallback_art`；`app.js` **先看标志位再碰 `<video>`**，缺素材直接走 `showBootFallback()`（吉祥物 + 光晕 + 进度条 → 淡出），壁纸退到 `wallpaper-anime.jpg` |
| 6 | 回执变成 `mode: dsh_video_bg_autoforward`（9.2 s 后放弃） | 从服务上下文远程拉起时窗口是**隐藏**的，浏览器不给隐藏窗口上屏；旧安全阀 9.2 s 一到就撤 | 安全阀放到 **90 s**，并新增"先等到窗口可见再播"；隐藏期间也把首帧画出来。`deskdiag` 同时报 `session`（`user` / `session_id` / `locked` / `logonui`），锁屏导致的不会骗人 |

**实测（2026-10-29 15:07，DESKTOP-IEUDGS5，全部由我远程执行）：**

| 检查 | 结果 |
| --- | --- |
| `deskdiag` 文件漂移 | `drift 0`，`index.html` / `app.js` / `style.css` / `server.py` / `desktop_ops.py` 五个文件仓库↔`C:\0apps\ArenaDesk` **哈希逐个相同** |
| 计划任务 | `arena-desk-boot-demo` **Running**、触发器 `MSFT_TaskLogonTrigger`、`last_run 15:07:07`；`arena-desk-open` Disabled；`arena-desk-open-manual` Ready 无触发器 |
| 素材 | `dsh-boot.mp4` / `dsh-bg.mp4` 仓库与台式机均**不存在**（`repo:false, desk:false`）；`boot-mascot.jpg` / `wallpaper-anime.jpg` 都在 |
| 会话 | `user BNI`、`session_id 1`、`locked False`、`logonui False` ——不是锁屏造成的 |
| **开机回执** | `boot_ack: ok True`、`overlay_hidden True`、**`mode: boot_asset_absent`**、`dismissed_at 15:07:48` ——既不是 300 ms 跳过，也不是 9.2 s 隐藏窗口放弃 |

也就是说：现在缺视频时走的是**优雅降级动画**（吉祥物图层，2.4 s 自然淡出），而不是黑闪；一旦把 `dsh-boot.mp4` 放进 `code/panel/assets/`，同一个 `sync` 就会自动切回真视频，代码不用改。

两个新信箱任务（同样是我远程调用，用户不接触命令行）：

```
python3 -m core.hub_mailbox run --kind deskfix  --json-args '{}'          # 重挂开机触发器 + 保面板存活 + 立刻拉一次动画
python3 -m core.hub_mailbox run --kind deskdiag --json-args '{}'          # 文件哈希 / 任务状态 / 服务响应 / 素材 / boot_ack / 锁屏
```

---

## 3.7 新会话怎么自己"上手"：`caps` 能力卡 + 零粘贴契约

新会话的第一条命令不该是猜，而是一张卡：

```
python3 -m core.hub_mailbox caps
```

它只读仓库里已提交的状态文件（不联网、不发单、1 秒返回），直接给出：

| 字段 | 内容 |
| --- | --- |
| `desk.alive` / `heartbeat_age_min` | 台式机是否活着、心跳多久前（> 120 min 判死） |
| `desk.gromacs` / `desk.gpu` / `desk.gpus` | 真正干活的引擎与显卡 |
| `selfcheck.overall` / `selfcheck.counts` | 18 项自检的 pass/warn/fail |
| `smoke.ns_per_day` / `smoke.accelerator` | 最近一次 100 ps 的速度与加速器 |
| `jobs` | 9 种任务各自干什么 |
| `first_steps` / `if_broken` | 先跑什么、坏了按什么顺序修 |
| `rules` | 五条硬规则（其中第一条就是"永远不要让用户粘贴命令"） |
| `user_action_required` | 固定 `false` |

**零粘贴契约**（写进 `docs/new_session_prompt_zh.md` v2 的硬规则，也会被测试守着）：
台式机上的一切动作——同步、部署、修计划任务、重启面板、跑 gmx、拉开机动画——
都必须通过 `hub/mailbox` 由会话自己发起；调用方**不提交、不推送、不碰分支**。
唯一允许例外：从没装过基座的全新机器（`caps` 里连心跳历史都没有），
此时给一条命令并说明原因，而不是把"你贴一下"当成默认手段。

**跨仓禁令**：台式机上只允许**一套**基座（`CGMD-Hub-Poll` + Arena Desk + `:8765`）。
另一个项目的会话曾自己克隆仓库、另建 `desktop-base`、写第二份 watcher，
结果第一轮就把自己的 watcher 删了、还要用户在机器上粘命令装凭据。
别的项目要用台式机，正确做法是**把 0fuye 当客户端**（`python3 -m core.hub_mailbox`）；
需要新任务类型就在本仓库加一个 kind 再 `sync`。

---

## 3.8 跨仓派活：token 只覆盖一个仓库，所以改成"各写各的、台式机居中"

任何会话都想驱动台式机（验收标准第 2 条），但 Arena 给每个云端会话的 `GH_TOKEN`
**只对会话所在的那个仓库有写权限**。2026-10-29 在 `JevHarness` 会话里实测：

| 请求 | 结果 |
| --- | --- |
| `POST /repos/hukeying85-ux/JevHarness/git/blobs` | `201 Created` |
| `POST /repos/hukeying85-ux/0fuye/git/blobs` | **`403 Resource not accessible by integration`** |
| `git push` 到 `JevHarness`（从 0fuye 会话发） | **`403`**（对称，反过来一样） |
| `git ls-remote` / `git clone` 对方公开仓库 | 正常（读是开放的） |

所以"让对方往 0fuye 的 `hub/mailbox` 推"这条路走不通，也不该走。现在改成：

```
对端仓库 hub/mailbox ──inbox/<id>.json──▶ 台式机（peer_repos，匿名 fetch）
                                           │ 执行（GPU / GROMACS）
                                           ▼
                       0fuye hub/mailbox ──outbox/<id>.json──▶ 调用方按同一 id 取回
```

| 组件 | 位置 | 作用 |
| --- | --- | --- |
| `peer_repos` | 台式机 `config\cgmd_hub.local.json` | 要侍候的对端仓库，`owner/repo` 或 `owner/repo#ref`；由 `deskfix` 远程写入 |
| `Invoke-PeerCycle` | `skills/cgmd-hub/runner/Invoke-CgmdMailbox.ps1` | 每轮匿名 `ls-remote` + `fetch` 对端信箱，跑单，回执写进**本仓** outbox |
| `peer_once` / `parse_peer` | `core/hub_mailbox.py` | 同一协议的 Python 孪生实现，测试用它驱动；没 PowerShell 的机器也能当中继 |
| `--read-repo` | `core.hub_mailbox` CLI | 从本仓派单、去 0fuye 读回执（一次命令两件事） |

细节：匿名优先（`-c credential.helper=`），私有仓库自动退回本机凭据助手再试一次；
对端还没建信箱分支时报 `waiting`（不算错误，不刷日志）；回执带 `peer` 字段；
对端那封请求**不用删**——台式机靠 ledger + 已有回执双重去重，同一单号只跑一次。

**实测（2026-10-29 16:2x–16:3x，真机）：**

| 步骤 | 结果 |
| --- | --- |
| 在另一个信箱里排队 `ping`（`hukeying85-ux/0fuye#peer-test`，模拟对端仓库） | 台式机一个轮询周期内取走 |
| 回执 | `ok \| DESKTOP-IEUDGS5 alive, gmx 2025.1, 1 gpu(s) \| peer=hukeying85-ux/0fuye#peer-test` |
| 同样路径排队 `smoke {"ps":100}` | `ok \| gmx 2025.1: 100 ps integrated on gpu`，`ps=100`、**540 ns/day**、`accelerator=gpu` |
| 生产配置 | `peer_repos = ["hukeying85-ux/JevHarness"]`，`deskdiag` 里 `peers: [{status: waiting, note: no mailbox branch yet}]` |

对端会话要做的只有两句（不需要碰台式机、不需要我贴命令）：

```bash
git clone https://github.com/hukeying85-ux/0fuye.git /tmp/desk
python3 -m core.hub_mailbox --repo . run --kind ping --read-repo /tmp/desk
```

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
