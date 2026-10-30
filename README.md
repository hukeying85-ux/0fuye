# 0fuye

## 通道状态（截至 2026-10-30）

**本会话已验证受限 Windows GROMACS 指令通道，但尚未启动肽 CG MD，也未读取台式机 F: 盘。**
用户允许跳过 F: 旧运行记录的前置核验；[单肽 Martini 3 工程试跑代码](cg_pilot/README.md)
以云端候选 YLSLLQR 建模，不是原 Aβ 种子成核实验。
2026-10-30 09:42 +08:00，现有桌面 hub 从本分支读取任务
`20261030T012629-1b00ad`，台式机 `DESKTOP-IEUDGS5` 执行 `gmx --version`
并在其 GitHub `hub/mailbox/outbox` 返回 `exit_code: 0`；这是本分支的**真实握手**，
但不是 `grompp`、`mdrun`、肽结构落地或轨迹。该 hub 仅接受白名单的 GROMACS
子命令：`pipeline` 未接线、任意 `shell` 默认禁用，不能因“每分钟自动轮询”
就假设它会自动运行 Python、下载私有 Drive 输入或修复错误。
Google Drive 连接器只能读取已在云端的文件；台式机没有 G: 本地镜像盘，
私有“prepared-not-run”输入包仍未验证落地到 Windows。**在安全地将输入
部署到台式机、确认 grompp 通过并取得实际 mdrun 回执前，不得称动力学已开始。**

- [现有桌面 hub 一次性接入本分支的受限 peer 任务通道](bridge/PEER.md)
- [Google Drive 云端搜索与旧版镜像队列的适用条件](bridge/DRIVE.md)
- [GitHub 分支握手与安全边界](bridge/README.md)
- [F: 肽结构与日志的人工只读采集备用方案](bridge/EVIDENCE.md)（用户目前不采用）

如已有 F: 项目在同账号 Google Drive 的自动备份，需先确定其云端目录；
否则必须一次性让已有桌面值守器接入可审计的任务与回执通道。云端
Aβ 候选文档不能替代 F: 最近运行输入的核验。
