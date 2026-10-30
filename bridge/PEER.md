# 将现有桌面 hub 一次性连接到本会话分支（不用 G:）

此会话固定使用分支 `arena/7ed6241a-0fuye`。已有的桌面 hub 在自己的分支
`arena/32cd826e-0fuye` 上有真实心跳/GROMACS 纯水盒回执；它的
`Invoke-CgmdMailbox.ps1` 支持 `peer_repos`：读取**本分支** `inbox/*.json` 的
白名单请求，回执写到它自己的 `hub/mailbox/outbox`。这条机制不要求本会话
推送其他分支、在 Windows 上挂 G: 或修改全局 Git 凭据。

**本机 peer 已启用且真实验收通过**：2026-10-30 09:41:59–09:42:00 +08:00，
桌面 `DESKTOP-IEUDGS5` 从本分支处理 `20261030T012629-1b00ad`，
`gmx --version` 退出码 0，并把同 ID 回执写入 `hub/mailbox/outbox`。
该收发通道是受限 GROMACS 通道，**不代表肽动力学已开始**；hub 不会读取
本会话的私人 Google Drive 输入，也不会自动运行 `cg_pilot` Python 代码。

## 一次性配置（已执行；仅供更换/重装桌面时参考）

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

**下一阶段尚需安全落地输入并验证**：当前 hub 的 `pipeline` 类型未接线，
`shell` 默认禁用。peer 接通只证明白名单 `gmx` 命令可派送，**不自动赋予
任意脚本执行权或私有 Drive 文件读取权**。`grompp`/`mdrun` 本身在白名单内，
但只有先把已建模的 `.gro/.top/.itp/.mdp` 文件放到台式机的私有工作目录、
核查参数与 GROMACS 预处理成功，才能按阶段派发它们。不可为省略这一步
随意开启公网仓库的任意远程 `shell`，或把纯水盒烟测称作肽 MD。
