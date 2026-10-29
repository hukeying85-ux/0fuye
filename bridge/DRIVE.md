# 台式机任务通道：Google Drive（不依赖 Git 推送）

之前的 GitHub 握手在台式机上 `git push` 时遇到 Windows 凭据存储错误；
那份回执**只在台式机克隆中提交成功，并未进入本分支**。本方案使用已授权的
Google Drive 文件夹做双向异步队列，绕开 Git 凭据；代码仍由公开仓库提供，
但**原始研究 DOCX、肽结构和轨迹不得提交到公开 Git 仓库**。

本会话已创建仅 Drive 账号所有者有权限的文件夹 `Arena-0fuye-DesktopBridge`
（含 `inbox` 和 `outbox`）。前提：台式机上的 `G:\我的云端硬盘` 登录的就是
存放研究 DOCX 的同一 Google Drive 账号，并且同步正常。若没有看到此文件夹，
请先核对账号和同步状态，**不要在 G: 手工创建同名空目录**。

## 一次性只读盘点（推荐先做）

在**台式机交互式 PowerShell** 中运行；已有那个带本地未推送提交的克隆不要删、
不要 `reset --hard`，这里用一个**新目录**克隆即可。此处克隆只需 GitHub 公开
读取权限，**不需要**配置 Git 推送凭据：

```powershell
$dest = Join-Path $HOME 'arena-0fuye-drive-runner'
git clone --single-branch --branch arena/7ed6241a-0fuye https://github.com/hukeying85-ux/0fuye.git $dest
Set-Location $dest
Get-Content .\bridge\drive-runner.ps1        # 先审阅两份脚本
Get-Content .\bridge\peptide-inventory.ps1
$drive = 'G:\我的云端硬盘\Arena-0fuye-DesktopBridge'
Test-Path (Join-Path $drive 'inbox')          # 必须为 True
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\bridge\drive-runner.ps1 `
    -DriveRoot $drive -SearchRoot 'F:\0wsh\asd' -Mode Once
```

`-Mode Once` 仅处理队列中的一个或多个 `inventory_peptides` 请求后退出；
如果 Google Drive 同步稍慢，等候文件出现再运行一次。无需管理员权限。
脚本只读扫描 F 盘的 `.pdb/.gro/.fa/.fasta`，结合邻近 `.xtc/.trr/.log`
**文件名与时间戳**挑选近期 2–30 个标准残基的肽；不会读取轨迹内容，
不安装软件、不启动 MD、不执行任务 JSON 里的命令或路径。
报告以小 JSON 写到私有 Drive `outbox`，包含候选结构路径、推断序列、
长度、运行证据文件名、时间戳和环境工具是否可见。序列可能漏掉非标准
残基/修饰或多链，需要在开跑前人工核对 PDB、端基与真实运行日志。

### 可选：持续轮询（由你明确选择）

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\bridge\drive-runner.ps1 `
    -DriveRoot $drive -SearchRoot 'F:\0wsh\asd' -Mode Watch -IntervalSeconds 60
```

该命令**仅在当前窗口打开期间**每分钟检查 Drive 队列，Ctrl+C 立即停止，
不创建计划任务或后台服务。当前版本的白名单**只有只读盘点**，不运行
GROMACS、Python、PowerShell 命令或接收任意脚本。正式 CGMD 运行步骤须
根据实际肽和力场单独实现、审核、明确计算预算后再启动。

## 如果还想修复 GitHub 回执

桌面端的错误是 `wincredman` 无法保存凭据且执行环境没有 TTY；它不是
「台式机已经打通」的证据。若你要继续走 GitHub 通道，在**可打开浏览器的
台式机交互式 PowerShell** 中自行查看 `gh auth status`，必要时通过
`gh auth login --hostname github.com --git-protocol https --web` 登录，
再 `gh auth setup-git`。之后需确认登录账号确实具有
`hukeying85-ux/0fuye` 的写入权限，才重试原克隆里的 `git push`。
不要把任何密码、令牌、浏览器授权码贴到聊天或上传到仓库。
Drive 方案不依赖这一步，也不要求你修改已有本机 Git 凭据。
