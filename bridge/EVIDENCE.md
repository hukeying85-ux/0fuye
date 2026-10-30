# YLSLLQR：从本机 F: 获取结构与运行证据（无 G:、不上传 Git）

用户要求：**只有确认 `F:\0wsh\asd` 最近实际跑过 YLSLLQR，才把它作为后续 CG MD 的输入**。Google Drive 中的 AChE–PAS 候选文档虽然含 YLSLLQR 序列，不能证明台式机上有相应结构和运行日志；100 ps 纯水盒烟测也不是肽 MD。Arena 云端只能读取已上传 Drive 的文件，不能直接访问本机 F:。

`collect-peptide-evidence.ps1` 是台式机交互式 PowerShell 5.1 的**一次性只读采集**：

- 对 F: 项目目录中 `.pdb/.pdbqt/.gro/.fa/.fasta` 的链或分子做**精确序列**匹配；扫描默认最近 90 天的运行证据，结构本身可更旧；
- 仅当包含确切 YLSLLQR 分子的 `.gro` 与**同名** `.tpr`、日志存在，日志确认 MD 积分器和运行结束、`.gro`/日志时间近期且相近，才标为 `verified_recent_md`；如只在多分子段内找到序列，则降低证据等级；
- 附上选中结构原件（可能包括水、其他链、CG 珠），以及同名运行日志（≤5 MB 时附原件，否则仅摘要/哈希）和小型 JSON 记录；**不复制轨迹或 TPR，不执行模拟，不联网，不修改 F:**。上传前须人工检查结构与日志中的本机路径/隐私信息；
- 写到本机 `%LOCALAPPDATA%\ArenaPrivatePeptideEvidence`（避免 Documents 被自动同步）并打包 ZIP，**绝不写到公开 Git 仓库**。无匹配或扫描受限时也生成带状态的报告，不能把“未找到”写成“F: 不存在”。

## 在目标 Windows 台式机执行（需本人先审阅脚本）

此前建立的新克隆若仍干净，可在交互式 PowerShell 中更新；如果 `status --short` 显示自己尚未保存的改动，**先停下，不要 reset/覆盖**：

```powershell
$repo = Join-Path $HOME 'arena-0fuye-drive-runner'
git -C $repo status --short
git -C $repo pull --ff-only origin arena/7ed6241a-0fuye
$script = Join-Path $repo 'bridge\collect-peptide-evidence.ps1'
Get-Content -LiteralPath $script      # 审阅：无网络/安装/G: 命令
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script `
  -Sequence YLSLLQR -SearchRoot 'F:\0wsh\asd' -DaysBack 90
```

如果本机没有该新克隆，不要覆盖旧的带本地提交的克隆；可新克隆当前分支到一个**全新目录**，再阅读并运行脚本。命令不依赖 Git 推送权限，只需能读取公开代码。

输出为 `%LOCALAPPDATA%\ArenaPrivatePeptideEvidence\Arena-YLSLLQR-evidence-*.zip`（实际绝对路径会打印在控制台）；**先在本机查看 ZIP 的 `manifest.json` 和结构/日志摘要**，再通过 Google Drive 网页上传到本会话已创建的仅所有者可见文件夹（链接在聊天中），或把 ZIP 作为私人附件交给 Arena。**不要 `git add`、`git push`、公开分享或上传含轨迹的整个 F: 项目。**上传后告知“已上传”，Arena 再从私有 Drive 核验实际结构、日志和运行参数。

`verified_recent_md` 只说明文件级关联符合要求，并非从二进制 TPR 校验过全部原子拓扑；后续建模前仍需复核是否全原子结构、端基/修饰、力场、真实体系组分与运行时间。`sequence_found_run_not_verified`、`incomplete_scan_target_not_found` 等状态都**不能**当作该肽近期运行的已证实结果。
