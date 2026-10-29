# 与 Windows 台式机打通：先做最小 GitHub 往返验证

此仓库是当前 Arena 会话的工作仓库：`hukeying85-ux/0fuye`、分支
`arena/7ed6241a-0fuye`。参考的 [leanrea 分支](https://github.com/mqgg5630-cyber/leanrea/tree/arena%2F4d729933-leanrea)
采用 **GitHub 分支作为异步中转**，但它的既有 `hub-watch.ps1` 默认只监视
`mqgg5630-cyber` 名下的仓库，运行在 **笔记本**，并不会自动监视这里的
`hukeying85-ux/0fuye`，更不等于台式机已在线。其 2026-10-27 的记录称
`desktop-ieudgs5` 当时 Tailscale 离线；这是旧记录，不是实时检测。

Arena 沙箱不能直接访问你的局域网或 Tailscale。先用下面的一次性握手确认
**台式机 → GitHub → 此分支 → Arena** 的双向数据路径；不安装后台服务、
不开 SSH、不执行来自 GitHub 的任意命令，也不需要管理员权限。完成后，
再按需要决定是否配置长期任务执行器或笔记本到台式机的 SSH。

## 在目标台式机上（Windows PowerShell，手动执行一次）

前提：已安装 Git for Windows；台式机能访问 GitHub。**推送回执需要此仓库的写入权限**。
先确认要操作的是你自己的机器；仓库是公开的，切勿提交任何隐私数据、
密钥或诊断日志。若已有同名目录，请换一个全新目录，勿覆盖原有克隆。

```powershell
$dest = Join-Path $HOME 'arena-0fuye-bridge'
git clone --single-branch --branch arena/7ed6241a-0fuye https://github.com/hukeying85-ux/0fuye.git $dest
Set-Location $dest
Get-Content .\bridge\desktop-handshake.ps1   # 先阅读脚本再决定是否执行
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\bridge\desktop-handshake.ps1 -DryRun
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\bridge\desktop-handshake.ps1
```

最后一行成功时打印 `OK: receipt pushed ...`。脚本先检查 origin、分支、工作区和
GitHub 上的 HEAD 是否一致；只读取仓库里的 `bridge/challenge.json`，提交
`bridge/receipts/<nonce>.json`（仅随机码、挑战提交 ID、结果、UTC 时间），并只推送
**这个分支**。不会上传电脑名、用户名、IP、硬件信息，也不会改全局 Git 配置。
`-DryRun` 只检查、不会提交。用本机 Git 身份管理器正常授权即可，**不要把令牌、
私钥或密码发到聊天或提交到仓库**。

如果 `git push` 提示 403/没有权限：**这不是握手成功**。当前仓库属于
`hukeying85-ux`，而提供的示例仓库属于 `mqgg5630-cyber`；不能假定台式机登录的
GitHub 账号可向此分支推送。需由仓库所有者通过 GitHub 正常授权具有写入权限的账号，
或者改用经双方同意的其他回执通道；不要在聊天里传凭据。你也可以先只运行
`-DryRun`，把非敏感的成功/报错文字告诉我，这只验证 **读取**，不算双向打通。
如果远端分支已经更新，脚本不会自动拉取并运行新代码：请先自行审查改动，
在全新克隆中重试，或在干净工作树里 `git pull --ff-only` 后重试。

## Arena 侧验收

收到台式机的 `OK` 后，在本会话中让我执行：

```bash
git fetch origin arena/7ed6241a-0fuye
git merge --ff-only origin/arena/7ed6241a-0fuye
python3 bridge/agent_verify.py
```

`VERIFIED` 代表挑战和回执在 GitHub 分支形成了往返；`WAITING` 代表还没有回执。
它**不**证明回执来自哪台物理机器，也不提供远程桌面/任意命令执行能力。
请保留最后的 `OK` 文字；不必把整个本机日志或敏感信息贴出来。

## 如果目标是「笔记本 ↔ 台式机实时 SSH」，而不是 GitHub 同步

这是另一条链路，与上述握手独立。leanrea 的旧诊断曾显示台式机 Tailscale 离线，
因此先在**台式机上**确认开机、Tailscale 已登录且与笔记本处于同一 tailnet：

```powershell
Get-Service Tailscale,sshd -ErrorAction SilentlyContinue | Format-Table Name,Status,StartType
# 若 tailscale 命令不在 PATH，请用本机实际的 tailscale.exe 完整路径：
tailscale status
tailscale ip -4
```

然后在**笔记本上**对刚得到的台式机 Tailscale IP 验证：

```powershell
$desktopIp = '这里填台式机 tailscale ip -4 的输出'  # 换成真实的 100.x 地址
tailscale ping $desktopIp
Test-NetConnection -ComputerName $desktopIp -Port 22
```

只有机器在线并且你确实需要 SSH，才在台式机上**自行审核后**以管理员身份启用
Windows OpenSSH Server（安装、服务启动、防火墙范围均应按你自己的网络策略配置），
再用你**自己的**公钥和 Windows 用户名测试 SSH。不要直接运行链接仓库的
`code/connect/desktop_setup.ps1`：它会改服务、系统电源设置和 SSH 信任关系，
其中公钥是为**另一台笔记本**预置的。不要把 SSH 22 端口对公网开放。
从 Arena 沙箱无法验证 Tailscale/局域网连通性；如需排障，请只提供已脱敏的
`tailscale status` / `Test-NetConnection` 结果。

## 后续长期任务

如确认要让 Arena 在台式机持续执行任务，需要**另行明确授权**：在目标台式机
安装受限的本机 runner，限定仓库、分支和可执行任务白名单，先审计代码和权限。
不能因为旧笔记本 hub 有回执就当作这台台式机的 runner 已经运行；更不应让公开
分支的任意内容直接以管理员权限执行。本阶段仅做一项可审计的单次握手。
