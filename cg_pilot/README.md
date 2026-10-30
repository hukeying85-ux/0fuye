# 单肽 Martini 3 工程试跑（不是 Aβ 成核复现）

目标：按用户此前明确指出的 **YLSLLQR**，跳过“必须先取得 F: 最近运行结构”这一步，构建一个**单条短肽的水溶液 CG MD 工程试跑**。这条序列来自用户与私有 Drive 候选文档，**不能写作已证实 F: 最近运行的肽**；初始结构是生成的理想伸展构象，并非实验构象。原 Aβ 方案方法 8 需要稳定 seed + 50 Aβ40、对照与多重复；本试跑不能证明促 Aβ 聚集或 PC12 效应。

## 当前真实状态

- 已在 Arena 沙箱成功用 `PeptideBuilder 1.1.0`、`vermouth/martinize2 0.15.0`、`insane 1.2.0` 建模和溶剂化，生成单肽 18 珠、7 nm 盒中总 3338 珠；`Peptide_0=1, W=3249, NA=35, CL=36`，中性体系。拓扑/坐标粒子数与珠名一致，官方 Martini 3.0.0 文件哈希通过。
- **没有运行本肽的 GROMACS `grompp` 或 `mdrun`**：Arena 沙箱没有 `gmx`。台式机现有 hub 已通过 peer 从本分支接收 `20261030T012629-1b00ad`，于 2026-10-30 09:42 +08:00 在 `DESKTOP-IEUDGS5` 执行 `gmx --version` 退出 0；仅证明受限 `gmx` 通道。它没有自动同步私有 Drive 输入，也没有接线的 `pipeline`/任意 Python 执行权限。**预处理输入尚未验证已在 Windows 本地落地**，所以不能直接下发 `grompp`/`mdrun`。此前 GPU 100 ps **纯水**烟测不是这条肽的模拟。
- 测试涵盖拓扑/电荷计数、离子名称、命令干跑、完整 Martini3 构建；并非台式机运行回执。

## 建模约定（需后续研究审核）

- 末端：自由 N 端 NH3+ / C 端 COO−，Arg 为 +1；总肽净电荷 +1。假设末端**未封端**；若实验物质不同必须重建，不得直接照用。
- 初始构象：理想伸展链；`martinize2 -ff martini3001 -ss C`，不加 elastic network。短肽易变构，单次短轨迹不可推断平衡分布。
- Martini 3.0.0 官方参数固定到 [marrink-lab/martini-forcefields `784591e`](https://github.com/marrink-lab/martini-forcefields/tree/784591ebdc91d762ed4df986c4650546c938f776)（Apache 2.0）；运行时从 GitHub 下载并验证三个 `.itp` 的 SHA-256。第三方大文件不提交到本仓库；生成的 `forcefield/LICENSE` 保存来源许可。纯水 `W` + `NA/CL`，INSANE 0.15 M、7 nm 立方盒，300 K；水/蛋白相互作用的成核用途**未经全原子校准**。
- 阶段：EM 5000 步 → 1 ns NVT → 1 ns NPT → 默认 10 ns 生产，20 fs 步长、reaction-field/epsilon-r 15、Martini3 相容的 1.1 nm 截断；EM CPU、动力学请求 GPU。GPU 命令失败即停止，不暗中改称 GPU 结果。

## 在**有 GROMACS、且已接入此分支任务的环境**中的用法

代码以 Python 3.10+ 和 GROMACS 2025.1 CLI 为目标；第三方 Python 依赖仅安装到独立 venv，**不要修改系统 Python/驱动**：

```bash
python3 -m venv .venv
.venv/bin/pip install -r cg_pilot/requirements.txt
.venv/bin/python -m cg_pilot prepare --output "$HOME/private-cg-runs/ylsllqr" --fetch-forcefield
.venv/bin/python -m cg_pilot run --workdir "$HOME/private-cg-runs/ylsllqr" --dry-run
# 审阅 manifest.json、结构/拓扑、环境和 GPU 预算后才能真正启动：
.venv/bin/python -m cg_pilot run --workdir "$HOME/private-cg-runs/ylsllqr" --gmx /path/to/gmx --gpu-id 0
```

Windows 应换成本机 Python 和 `gmx.exe` 的路径。**上面是未来在有接收者的主机上执行的说明，不代表本会话已经对台式机发起模拟。**输出应留在本地私有目录；不要提交 `.gro/.xtc/.tpr/.cpt/.edr`、实验 PDB、完整研究 DOCX 到公开仓库。只有看到台式机同一任务的 `grompp`/`mdrun` 实际日志、轨迹和小型结果回执，才能说“已在台式机开始/完成”。

## 验收顺序

1. 台式机接入一个**真实的、针对本分支的受限任务接收通道**：已于 2026-10-30 09:42 +08:00 以 `gmx --version` 回执验证，只证明连接和 GROMACS 可执行。
2. 先以隐私合规方式将已准备的输入落地到 Windows 本地；当前尚未完成。之后在台式机上执行 `gmx grompp`/EM；零警告、坐标/拓扑匹配且无严重重叠才进 NVT/NPT，核对能量/温度/压力后再进入生产；失败停止并回传摘要，不掩盖错误。脚本只按退出码运行阶段，尚未实现自动能量 QC；`integrated_qc_pending` **不是科学质量闸门已通过**。
3. 把任务 ID、GROMACS/Forcefield 版本、实际积分时长、完成标志、能量/轨迹检查与失败原因写入**私有**回执，分析仅限“自身构象/溶剂化工程试跑”。
