# skills/cgmd-hub · Windows 台式机零闪窗守护

本目录是 Windows 11 侧的全部代码。设计目标只有三条：

1. **永远不会出现黑色控制台窗口**（包括登录自启、每 60 s 轮询、模拟结束回写提交的瞬间）；
2. **只改本仓库的 git 配置**，绝不触碰全局 `git config` 或其他 GitHub 账号；
3. 出错必须能自证：所有动作写日志 + 心跳 JSON + 手机推送。

---

## 文件一览

| 文件 | 说明 |
| --- | --- |
| `bootstrap_desktop.ps1` | **一次性初始化**：预检 → 克隆并校验 origin → 本地凭据 → WSL 环境自检 → 写配置 → 编译静默包装器 → 注册计划任务 → 验证推送 |
| `runner/Invoke-CgmdPoll.ps1` | 单次轮询的全部逻辑（flock 防重入、origin 校验、fetch/reset、调 WSL runner、只提交 `results/`、push 重试、心跳） |
| `runner/CgmdPoll.vbs` | 零窗口入口：`wscript.exe` 直接 `Run(..., 0, False)` |
| `runner/SilentLauncher.cs` | `/target:winexe` 包装器源码：`UseShellExecute=false` + `CreateNoWindow=true`，把子进程输出重定向到日志 |
| `runner/Build-SilentLauncher.ps1` | 用系统自带 `csc.exe` 编译（无需 VS/SDK/联网） |
| `runner/Register-CgmdHubTask.ps1` | 注册/替换计划任务（默认 60 s，`ExecutionTimeLimit=0` 支持跨天微秒级模拟） |
| `runner/Unregister-CgmdHubTask.ps1` | 停止并移除计划任务 |
| `runner/Send-CgmdBeacon.ps1` | Windows 侧 ntfy 推送（与 Python 端同协议、同频道、北京时间戳） |
| `runner/Test-CgmdHub.ps1` | **18 项自检**：仓库/origin/分支/凭据/WSL/GPU/GROMACS-CUDA/Martini3/python 依赖/martinize2+insane/磁盘/静默包装器/计划任务/推送；产出 `results/status/desktop_selfcheck.json`（`cgmd.selfcheck.v1`），可选 `-Push` `-Notify` |
| `runner/Run-Gmx-Native.ps1` | **Windows 原生 100 ps 实测**：只用 GROMACS 自带 `oplsaa.ff` + SPC 水，`solvate` → EM → `50000×0.002 ps`，GPU 失败自动回退 CPU；若 `grompp` 在自带力场上崩溃（2025.1 Windows 版实测 `0xC0000005`）则自动换「参数全内联的 SPC 拓扑」重跑并记录原因；产出 `results/status/gmx_smoke.json`（`cgmd.gmxsmoke.v1`）并推送；不依赖 WSL / Python / Martini 文件 |
| `runner/Run-Smoke.ps1` | 手动 100 ps（WSL 版）；`-Native` 转调上一条；`-ClearLock` 先清卡死的 `poll.lock` 与残留轮询进程 |
| `runner/Sync-Desktop.ps1` | **一键同步**：origin 校验 → `fetch` → `reset --hard origin/<branch>`（脏工作区默认拒绝）→ 可选 `-Desk` 重新部署 `code/panel` → 跑 18 项自检 → 提交并推送 `desktop_sync.json` + `desktop_selfcheck.json` |
| `config/cgmd_hub.json` | 配置模板（真实配置 `cgmd_hub.local.json` 已 gitignore） |
| `state/`、`logs/` | 运行期状态与日志（已 gitignore） |
| `results/status/hub_heartbeat.json` | **值守心跳**（`cgmd.heartbeat.v1`）：轮询器最多每小时推送一次，任何客户端用 `python3 -m core.selfcheck heartbeat` 就能判断「台式机值守是否活着」 |

---

## 首次运行

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap_desktop.ps1
```

常用参数：

```powershell
.\bootstrap_desktop.ps1 -RepoPath D:\cgmd\0fuye -GpuId 1 -IntervalSeconds 60
.\bootstrap_desktop.ps1 -InstallWslDeps        # 顺带 pip 安装 python 侧依赖
.\bootstrap_desktop.ps1 -GitHubToken 'ghp_xxx' # 免交互（会写入已 gitignore 的凭据文件）
```

---

## 零闪窗的实现路径（为什么物理上不可能有黑框）

```
任务计划程序
  └─ wscript.exe  "<...>\CgmdPoll.vbs"        ← GUI 子系统，无 console 可言
        └─ CGMDHub.exe  --script Invoke-CgmdPoll.ps1   ← /target:winexe（GUI 子系统）
              └─ powershell.exe -WindowStyle Hidden   (CreateNoWindow = true)
                    └─ wsl.exe -d Ubuntu -- bash -lc ...
                          └─ python3 desktop_runner.py  →  gmx mdrun
```

* 计划任务的动作**不是** `powershell.exe`，因此不存在「先起控制台再隐藏」的瞬时闪烁窗口；
* `CGMDHub.exe` 由 `/target:winexe` 编译，PE 头里子系统就是 GUI，Windows 不会为它分配控制台；
* `CgmdPoll.vbs` 用 `shell.Run cmd, 0, False`（窗口样式 0 = 隐藏、不等待）；
* 所有 `Start-Process` 都带 `-NoNewWindow`，捕获输出走临时 `.cmd` 文件重定向，不新建窗口；
* 即使 `csc.exe` 不可用（极端精简系统），`wscript → powershell -WindowStyle Hidden` 这条链同样是零窗口，脚本会自动降级。

校验方法：注册后连续观察 3 分钟任务管理器，`conhost.exe` 不应有与轮询周期同步的新实例。

---

## 轮询器做的事（每 60 s）

1. `state/poll.lock` 独占锁 → 上一轮还在跑就直接退出（微秒级任务跑几天也不怕）；
2. `git remote get-url origin` 必须命中 `hukeying85-ux/0fuye`，否则 `exit 5` 并拒绝一切操作；
3. 若上一轮有未提交的 `results/` 变动，先提交推送（自愈）；
4. `git fetch` + 工作区干净时 `reset --hard origin/<branch>`；脏则只 `checkout`，绝不丢本地改动；
5. 读 `results/status/cgmd_task.json`，非 `pending` 直接空闲退出；
6. `wsl.exe -d <distro> -- bash -lc "cd <repo> && PYTHONPATH=... python3 code/federation/desktop_runner.py run ..."`；
7. 从 capture 文件里解析 runner 打印的最后一行 JSON 与 `CGMD_EXIT_CODE=`；
8. 只 `git add results/status results/cgmd` → `commit` → `push origin HEAD:<branch>`（失败自动 `pull --rebase --autostash` 重试 3 次）；
9. 写 `state/hub-state.json` 心跳，并推送一条手机通知。

`results/` 之外的文件永不提交；即使仓库里混进 `.xtc/.trr/.tpr/.cpt/.gro`，runner 的 `prune()` 会先删掉再提交。

---

## 一键同步（把 desk 拉到台式机并自检）

```powershell
# 最省事：同步到分支最新 + 重新部署 Arena Desk + 18 项自检 + 报告自动 push
powershell -NoProfile -ExecutionPolicy Bypass -File C:\cgmd\0fuye\skills\cgmd-hub\runner\Sync-Desktop.ps1 -Desk -Notify

# 只看会拉进来什么，不动工作区
powershell -NoProfile -ExecutionPolicy Bypass -File C:\cgmd\0fuye\skills\cgmd-hub\runner\Sync-Desktop.ps1 -DryRun
```

退出码：`0` 全绿 / `6` 有告警 / `7` 自检失败 / `9` desk 部署失败 / `8` git 冲突（先提交或加 `-Force`）/ `5` origin 不符 / `4` 配置缺失。
记录落在 `results/status/desktop_sync.json`（schema `cgmd.desksync.v1`：`from_sha`→`to_sha`、desk 版本、自检结论）。

## 值守是否活着？（心跳）

轮询器每次跑到末段都会更新本地 `state/hub-state.json`；**最多每 60 分钟**还会推一个 300 字节的
`results/status/hub_heartbeat.json` 到分支，于是“台式机值守有没有在跑”可以从任何地方验证，不需要 SSH：

```bash
python3 -m core.selfcheck heartbeat
# ALIVE: 2026-10-29T10:31:00+08:00 | host DESKTOP-CGMD | branch arena/32cd826e-0fuye | head 8b49c36 | state idle | 3 min ago (limit 120)
```

* 判据：`age <= max(2 × poll_seconds, 5 分钟)` 算 ALIVE，否则 STALE（退出码 1）；文件不存在 = 台式机从未跑过轮询；
* 频率调节：`Invoke-CgmdPoll.ps1 -HeartbeatMinutes 0` 每轮都写，`-1` 关闭 git 心跳（本地心跳保留）。

## 自检（这个台式机现在到底能不能接单？）

两种触发方式，结果都落在同一个文件里：

```powershell
# A. 坐在台式机前直接跑（推荐：表格一眼看清）
powershell -NoProfile -ExecutionPolicy Bypass -File C:\cgmd\0fuye\skills\cgmd-hub\runner\Test-CgmdHub.ps1 -Push -Notify
```

```bash
# B. 远程点名：任何客户端往分支里塞一个请求文件，台式机下一次轮询（<=60 s）自动执行
python3 -m core.selfcheck request --note "换网卡后复测" --write        # 只自检
python3 -m core.selfcheck request --desk --note "顺带部署 desk" --write  # 同步+部署 desk+自检
python3 -m core.selfcheck request --smoke --note "验证 gmx" --write     # 额外跑 100 ps 实测
git add results/status/selfcheck_request.json && git commit -m "queue selfcheck" && git push
python3 -m core.selfcheck status      # 读回桌面刚推上来的结论
```

判定与退出码：

| 退出码 | 含义 | 说明 |
| --- | --- | --- |
| `0` | 全绿 | 18 项全 pass，可接微秒级任务 |
| `6` | 有告警 | 例如 WSL 家目录剩余空间不足 20 GB、GROMACS 无 CUDA、分支落后；仍可跑 |
| `7` | 有失败 | 缺 GPU / 缺 python 依赖 / 缺 Martini 3 / 计划任务未注册等，必须先修 |
| `5` | origin 不符 | 克隆指向的不是被锁定的仓库，**拒绝运行** |
| `4` | 配置缺失 | 还没跑过 bootstrap |

18 项检查一览：`repo` `origin` `branch` `creds` `wsl` `gpu` `gromacs` `martini3` `python` `tools` `disk` `launcher` `task` `beacon` + `desk-src` `desk-app` `desk-http`（Arena Desk）+ `gmxrun`（最近一次 100 ps 实跑）。

* 自检本身**不碰 GPU、不启动模拟**，WSL 侧只做一次 base64 传输的探测脚本（一次往返，约 2 s）；
* `-Push` 会把报告提交并推到当前分支，因此"打通"这件事有 git 证据，而不是口头结论；
* bootstrap 最后一步会自动跑一次 `Test-CgmdHub.ps1 -Push`，首次安装即以自检报告收尾；
* 报告体积约 4 kB，`python3 -m core.selfcheck show` 可将它渲染成表格。

## 凭据策略（只动本仓库）

* `git config --local user.name/user.email`（`<user>@users.noreply.github.com`）；
* `git config --local credential.helper 'store --file=<repo>\\skills\\cgmd-hub\\state\\git-credentials'`；
* 该文件 `gitignore` + `Set-Acl` 仅当前用户可读；
* **不执行** `git config --global`，**不修改** Windows 凭据管理器，**不碰**任何其他账号配置。

---

## 排错

```powershell
Get-ScheduledTask -TaskName CGMD-Hub-Poll | Get-ScheduledTaskInfo
Get-Content .\logs\hub-*.log -Tail 40 -Wait
Get-Content .\state\hub-state.json
.\runner\Invoke-CgmdPoll.ps1 -Force -LogVerbose     # 前台手动跑一次
```

| 症状 | 处理 |
| --- | --- |
| 任务结果 `0x1` 且日志空 | 手动前台跑一次看报错；通常是 `wscript.exe` 路径或 distro 名不对 |
| `exit 5` | origin 不是本仓库，按提示修正后重跑 bootstrap |
| `exit 6` | 超过 `-MaxRunMinutes` 被强杀，检查 GPU 是否被占用 |
| 推送失败 | `-NoPublish` 只跑不推；或检查 token 过期（重跑 bootstrap 会重新写入） |
