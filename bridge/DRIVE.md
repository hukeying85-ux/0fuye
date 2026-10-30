# Google Drive 搜索与旧版台式机任务通道

**2026-10-29 状态更正：目标台式机没有 G: 盘。下面依赖
`G:\我的云端硬盘` 的本地镜像队列不适用于这台机器，请勿照着运行、
更不要手工创建空的 G:。**用户要求改用 Arena 已连接的 Google Drive
直接搜索云端资料；这一步不需要本机挂载盘，也不需要 Git 推送。

已在 Drive 找到 Aβ 候选短肽 MD 方案 DOCX 与 12 条 AChE–PAS 对接肽的
补充文档（云端文档中有序列）；其所在文件夹没有 PDB/GRO/FASTA 或轨迹。
**Drive 文档中的序列不能证明它就是台式机 `F:\0wsh\asd` 最近运行的肽**，
也不能证明已完成肽的粗粒化 MD。先前仅用于只读盘点的队列任务未运行、
没有 outbox 回执，现已从 inbox 移至回收站，避免以后误执行。
原始研究 DOCX、肽结构和轨迹不得提交到公开 Git 仓库。

以下内容保留作为**仅供确实有 Google Drive 本地同步盘的其他机器**使用的
旧方案说明。它不是直接访问云端的 API；Arena 的 Drive 连接器只能读取
已同步到云端的文件，不能直接扫描本机 F: 盘。

若坚持核验 F: 上近期实际运行的 **YLSLLQR**，参见
[无需 G: 的本机只读证据采集与网页私有上传](EVIDENCE.md)；
在拿到结构和真实运行记录前不选定体系，也不称已完成 CG MD。

## 旧方案：可见本地同步盘时的一次性只读盘点

本会话曾创建仅账号所有者可访问的 `Arena-0fuye-DesktopBridge` 文件夹
（`inbox`/`outbox`），但目前 **inbox 无活动任务**；以下是旧方案的操作示例，
**不是让这台没有 G: 的台式机运行它**。
仅在别的机器确实已经有该账号的本地同步盘、且另行派发有效任务后，
才在其交互式 PowerShell 中参考以下命令。已有带本地未推送提交的克隆不要删、
不要 `reset --hard`；新目录克隆只需 GitHub 公开读取权限：

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
