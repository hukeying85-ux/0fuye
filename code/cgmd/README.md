# code/cgmd · Martini 3 粗粒化抗菌肽膜打孔流水线

输入任意候选抗菌肽序列（或已预测的 PDB），输出**可复现的细菌内膜 POPE:POPG(3:1) 打孔模拟**，
以及一份 `< 1 MB` 的 `summary_metrics.json` + 矢量图；重轨迹（`.xtc/.trr/.tpr/.cpt/.gro`）永不入库。

---

## 目录

```
code/cgmd/
├── cgmd/
│   ├── config.py      Config 解析（任务文档 / 环境变量 / 本机配置三级覆盖）
│   ├── peptide.py     肽物化描述（pH 7.4 净电荷、pI、GRAVY、疏水力矩、两亲性、摩尔质量）
│   ├── seq2pdb.py     序列 → 全原子 PDB（NeRF 内置建模 / 外部预测器 / 指定 PDB）
│   ├── engine.py      GROMACS 命令构造、mdp 渲染、GPU/环境探测
│   ├── topology.py    insane + martinize2 + Martini 3 力场 → 可跑 topol.top（含原子数交叉校验）
│   ├── index.py       index.ndx 生成（Peptide/Membrane/POPE/POPG/Water/Ions/Headgroups/Tails）
│   ├── pipeline.py    EM → 20 ns NPT 预平衡 → 微秒级生产；stages.json 断点续跑
│   ├── analyze.py     嵌膜深度 z、脂序参数 S、水孔指标、膜厚（MDAnalysis）
│   ├── figure.py      SVG 矢量图（深度曲线/序参数/水孔/螺旋轮/膜厚）
│   └── cli.py         run / plan / env-check / describe
├── mdp/               em.mdp.in / eq.mdp.in / prod.mdp.in（Martini 3 标准参数）
├── examples/          任务 JSON 示例
└── setup_env.sh       WSL2 环境自检 / 安装
```

---

## 快速开始

```bash
export PYTHONPATH=$PWD:$PWD/code/cgmd

# 环境自检（GROMACS/CUDA/Martini3/MDAnalysis）
python3 -m cgmd.cli env-check

# 肽描述：无需任何依赖，先把候选序列筛一遍
python3 -m cgmd.cli describe GIGKFLHSAKKFGKAFVGEIMNS

# 干跑：打印完整命令计划，不碰 GPU
python3 -m cgmd.cli plan --sequence GIGKFLHSAKKFGKAFVGEIMNS \
    --workdir ~/cgmd-runs/demo --output results/cgmd/demo

# 真跑（由台式机守护自动调用，形态如下）
python3 -m cgmd.cli run --task results/status/cgmd_task.json \
    --workdir ~/cgmd-runs/<task_id> --output results/cgmd/<task_id> \
    --gpu-id 0
```

常用开关：`--production-ns`、`--equilibration-ns`、`--ntomp`、`--martini3-dir`、`--max-frames`、
`--no-resume`（重算）、`--no-notify`、`--dry-run`。

---

## 力场与依赖

`martini-forcefields`（PyPI）或从 cgmartini.nl 下载 `martini_v3.0.0`，力场**不入库**（第三方许可）。
解析顺序：`--martini3-dir` → `CGMD_MARTINI3_DIR` → `skills/cgmd-hub/config/cgmd_hub.local.json` →
`<repo>/forcefields/martini3` → pip 包 `martini_forcefields/**/gmx_files`。

| 组件 | 用途 | 安装 |
| --- | --- | --- |
| GROMACS ≥ 2021（CUDA） | grompp / mdrun | `sudo apt install gromacs` 或 `-DGMX_GPU=CUDA` 自编译 |
| vermouth（含 `martinize2`） | 全原子 → Martini 3 | `pip install vermouth` |
| insane | 建膜 + 加水加盐 | `pip install insane` |
| martini-forcefields | Martini 3 参数 | `pip install martini-forcefields` |
| MDAnalysis | 轨迹分析 | `pip install MDAnalysis` |
| numpy / matplotlib | 数值与出图 | `pip install numpy matplotlib` |

---

## 关键实现说明

### 1. 序列 → 结构
内置建模器用标准键长键角 + NeRF 内部坐标法逐残基放置重原子（20 种标准残基的侧链都有专门的构建分支，
芳香环用规则多边形后再吸附到 CB 上），默认生成理想伸展链，`--ss H` 可生成理想 α 螺旋；
写盘前会做 1.0 Å 非键碰撞检查（`structure.json` 里可见 `clashes`）。
有实验/预测结构时优先 `--structure-pdb`，或 `--predictor "colabfold_batch {fasta} {outdir}"`。

### 2. GROMACS 参数（Martini 3 标准）
`reaction-field / rcoulomb 1.1 / epsilon_r 15 / Verlet buffer 0.005 / Potential-shift / rvdw 1.1`；
EM 用 `steep`，预平衡 `v-rescale tau-t 1.0 + c-rescale semiisotropic tau-p 4.0` 且 `-DPOSRES`
（`martinize2 -p backbone` 写入的 posre 段），生产 `Parrinello-Rahman tau-p 12.0`、`dt 20 fs`。
`mdrun` 固定 `-nb gpu -bonded gpu -pme cpu -gpu_id N -pin on -dlb yes`。

### 3. 拓扑重建（最容易翻车的地方）
`insane` 只会写 `#include "martini.itp"`（一个不存在的文件名）并沿用旧离子名（`NA+`）。
`topology.py` 会：递归索引力场目录下所有 `[ moleculetype ]`（含原子数）→ 把 `NA+→NA`、`SOL→W` 之类
别名归一 → 只 `#include` 实际用到的文件（base `[ defaults ]/[ atomtypes ]` 排最前）→ 用 `martinize2`
输出的真实分子名（`Protein_0`）替换 `Protein` → 与 `.gro` 的原子数交叉校验。
最终 `topol.top` 是自洽的，`gmx grompp` 无需任何手工编辑。

### 4. 断点续跑
`<workdir>/stages.json` 记录每个阶段的完成状态与耗时；崩溃/断电后重跑同一条命令即可从断点继续
（生产阶段还会自动 `-cpi prod.cpt`）。`--no-resume` 强制全量重算。

### 5. 结果收敛
`summary_metrics.json` 里所有时间序列按 ≤400 点抽稀（`timeseries` 段 ≤121 点），
`desktop_runner.enforce_size()` 还有一道 >1 MB 自动再抽稀的兜底；图形只出 SVG（无位图依赖）。

---

## 指标口径

| 字段 | 含义 |
| --- | --- |
| `membrane_insertion.z_distance_nm` | 肽珠质心 z − 磷酸基团圆均值中平面 z（最小镜像），负值 = 偏向下层小叶 |
| `membrane_insertion.inserted_fraction` | 平衡段中 \|z\| < 1.5 nm 的帧占比 |
| `membrane_insertion.per_residue_z_nm` | 每个肽珠相对中平面的平均深度 |
| `lipid_order.sn1/sn2` | Martini 尾链相邻珠键方向与膜法向的 `S = <P2(cosθ)>`（0.9+ 有序、<0.5 明显扰动） |
| `pore.water_in_core` | 肽横向半径 1.2 nm 圆柱内、膜芯 ±0.9 nm 的水珠数 |
| `pore.pore_score` | 该区域水密度 / 本体水密度（> 0.25 且占平衡段 > 10% → `pore_formed`) |
| `membrane.thickness_nm` | 上下层磷酸基团平均 z 之差 |

---

## 测试

```bash
PYTHONPATH=.:code/cgmd MPLBACKEND=Agg python -m pytest tests -q
```

`tests/test_pipeline_dryrun.py` 用干跑跑通「认领 → 执行 → 回写 → 结果镜像」全链路；
`tests/test_analyze_trajectory.py` 用合成的 Martini 体系（MDAnalysis 写 XTC）验证三项核心指标与体积上限。
