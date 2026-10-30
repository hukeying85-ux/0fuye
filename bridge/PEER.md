# 将现有桌面 hub 一次性连接到本会话分支（不用 G:）

此会话固定使用分支 `arena/7ed6241a-0fuye`。已有的桌面 hub 在自己的分支
`arena/32cd826e-0fuye` 上有真实心跳/GROMACS 纯水盒回执；它的
`Invoke-CgmdMailbox.ps1` 支持 `peer_repos`：读取**本分支** `inbox/*.json` 的
白名单请求，回执写到它自己的 `hub/mailbox/outbox`。这条机制不要求本会话
推送其他分支、在 Windows 上挂 G: 或修改全局 Git 凭据。

但该桌面 hub 的本机 `cgmd_hub.local.json` 目前仅列出别的 peer，**尚未列出本分支**。
云端代码/Google Drive 连接器不能改 Windows 上这个被 Git 忽略的私有配置。
因此必须由掌管台式机的用户**只执行一次**配置动作。没有这一步，任何云端
任务都只是排队，绝不能说已在台式机运行。

## 一次性配置（先辨认终端，再复制相应命令）

如果提示符为 `C:\Users\BNI>`，那是 **cmd.exe**，不是 PowerShell。
在该窗口请复制**下列完整的一行**（不能拆行；`&&` 保证更新失败时不会运行旧脚本）：

```cmd
git -C "%USERPROFILE%\arena-0fuye-drive-runner" pull --ff-only origin arena/7ed6241a-0fuye && powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\arena-0fuye-drive-runner\bridge\enable-existing-hub-peer.ps1"
```

如已打开 **PowerShell**（提示符常以 `PS C:\...>` 开头），并确认之前克隆的
`arena-0fuye-drive-runner` 工作区无未保存改动，则可用下面的 PowerShell 版本：

```powershell
$repo = Join-Path $HOME 'arena-0fuye-drive-runner'
git -C $repo status --short    # 若这里有重要未保存修改，先停下，不要 reset
git -C $repo pull --ff-only origin arena/7ed6241a-0fuye
if ($LASTEXITCODE -ne 0) { throw '更新失败；不要运行旧脚本' }
$script = Join-Path $repo 'bridge\enable-existing-hub-peer.ps1'
Get-Content -LiteralPath $script
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script -WhatIf
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script
```

脚本仅在 `C:\cgmd\0fuye\skills\cgmd-hub\config\cgmd_hub.local.json`
的 `peer_repos` 中**追加** `hukeying85-ux/0fuye#arena/7ed6241a-0fuye`，
保留原有 peers 与设置，并把原配置备份到该 hub 已忽略的 `state/` 下。
它不安装服务、不启用 `shell`、不改受监控分支、不提交原始研究数据、
不运行 CGMD；条件不符会停止。旧本机配置可能**没有** `mailbox_enabled` 键：
现有 hub 的代码把缺省值视为 `true`，接入脚本也遵循此规则；如果该键
**明确写为 `false`**，脚本仍拒绝修改、不会擅自开启邮箱。
若实际 hub 路径不同可显式指定 `-HubRepoPath <真实路径>`，
不要猜目录、不要将令牌发给 Arena。

## 如何判断真正接通

本分支 `inbox/` 已有一个**仅运行 `gmx --version`** 的只读握手任务。
桌面 hub 每次轮询重新读取本机配置；启用 peer 后，应在它自己的
`hub/mailbox/outbox/<同一ID>.json` 写出包含该任务 ID 的回执。
Arena 只读核对**同一任务 ID + worker + 时间 + 实际退出码**后才称“连接成功”。
若无回执或 `gmx` 失败，不能根据旧心跳冒充已接通。

**下一阶段尚需独立实现安全运行权限**：当前 hub 的 `pipeline` 类型未接线，
`shell` 默认禁用。peer 接通只证明受限 `gmx` 命令可派送，**不自动赋予任意脚本
执行权**。必须另做审核的 `cg_pilot` 受限执行器，才能运行单肽的
`grompp`/`mdrun` 并把原始轨迹留在台式机、只回传小型非敏感结果。
