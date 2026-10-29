# 粗粒化分子动力学（Martini 3）抗菌肽膜打孔 · 具体步骤详解

> 适用体系：细菌内膜模型 **POPE:POPG = 3:1**（± 0.15 M NaCl），候选抗菌肽（AMP）单拷贝
> 工具链：`insane.py`（建膜）+ `martinize2` / vermouth 0.15（粗粒化）+ GROMACS 2021↑ CUDA（EM→NPT→生产）+ MDAnalysis（分析）
> 对应仓库实现：`hukeying85-ux/0fuye` → `code/cgmd/`（流水线）、`code/federation/`（无人值守 + 手机推送）
> 时间基准：全部北京时间（Asia/Shanghai，UTC+8）

---

## 0. 全流程总览（12 个阶段）

| # | 阶段 | 关键输入 | 关键输出 | 单次耗时（参考） | 必须通过的校验 |
|---|------|----------|----------|------------------|----------------|
| 0 | 环境准备 | WSL2 + NVIDIA 驱动 | `gmx` / `martinize2` / `insane` / Martini 3 itp | 首次 30–60 min | `gmx --version` 出现 `GPU support: CUDA` |
| 1 | 体系设计 | 肽序列、膜组成、盒子、盐、温度 | `cgmd_task.json` 或 CLI 参数 | 5 min | 肽长 ≤120 aa、序列只含 20 种标准氨基酸 |
| 2 | 序列 → 全原子结构 | 序列 / 预测 PDB | `peptide_atomistic.pdb` | 1 s（内置）～30 min（ColabFold） | 非键原子间 ≥1.0 Å，无碰撞 |
| 3 | martinize2 粗粒化 | `peptide_atomistic.pdb` | `peptide_cg.pdb` + `peptide.top` + `Protein_0.itp` | 3–10 s | 珠子数 ≈ 1–2 × 残基数 |
| 4 | insane 建膜 + 溶胀 | `peptide_cg.pdb` | `system.gro` + `insane.top` | 1–20 s | 膜上下层脂质数接近、总电荷提示 |
| 5 | 拓扑重建 | `insane.top` + `peptide.top` | `topol.top` | <1 s | `topol.top` 原子数 == `.gro` 原子数 |
| 6 | 索引文件 | `system.gro` | `index.ndx` | <1 s | 含 `Peptide/Membrane/Water/Ions` 组 |
| 7 | 能量最小化 EM | `em.mdp` | `em.gro` / `em.log` | 10 s–5 min（CPU） | `converged to Fmax < 10`，最大力 < 100 |
| 8 | 预平衡 NPT | `eq.mdp` + `-DPOSRES` | `eq.gro` / `eq.cpt` | 20 ns ≈ 10–40 min | 温度/压力平稳、膜厚 3.5–4.2 nm、肽不跑位 |
| 9 | 生产模拟 | `prod.mdp` | `prod.xtc` / `prod.log` / `prod.cpt` | 1 µs ≈ 10–25 h | `ns/day` 正常、无 LINCS 爆炸 |
| 10 | 轨迹分析 | `system.gro` + `prod.xtc` | `summary_metrics.json` + SVG | 2–20 min | JSON < 1 MB、帧数/残基数完整 |
| 11 | 回传与推送 | 精简结果 | Git `results/cgmd/<task_id>/` + 手机弹窗 | 秒级 | 无 `.xtc/.trr/.tpr/.cpt/.gro` 入库 |

**一句话串起来**：`序列 → 全原子 PDB → Martini 3 珠子 → 塞进 POPE:POPG 膜 → 拓扑自洽 → EM 消张力 → 20 ns 让脂质包裹肽 → 微秒级看打孔 → 只把 10 kB 数字和几张 SVG 交回去`。

---

## 阶段 0 · 环境准备（WSL2 + CUDA）

### 0.1 基础检查

```bash
uname -srm                 # Linux ... x86_64
nvidia-smi                 # WSL2 里必须能看到 Windows 侧透传的 GPU
gmx --version              # 需要 "GPU support: CUDA"
```

要点：

* **NVIDIA 驱动只装在 Windows 侧**（≥ 535），WSL2 里**不要**再装 Linux 驱动，否则 `nvidia-smi` 冲突；
* GROMACS 必须是 CUDA 版本；Ubuntu 24.04 的 `apt install gromacs` 通常已带 GPU 支持，否则按 `-DGMX_GPU=CUDA -DGMX_USE_FFT_MKL=off` 自行编译；
* Martini 3 力场**不入库**（第三方许可），用 pip 包或手动下载。

### 0.2 一次性安装

```bash
# Python 侧（建膜、粗粒化、分析、出图）
pip install vermouth insane martini-forcefields MDAnalysis numpy matplotlib

# 全量自检（本仓库脚本，会写一份机器可读报告）
bash code/cgmd/setup_env.sh --check
bash code/cgmd/setup_env.sh --install --yes      # 缺什么补什么
```

### 0.3 目录约定（重轨迹绝不进 Git）

```
~/cgmd-runs/<task_id>/        # 工作区：.xtc/.trr/.tpr/.cpt/.gro 全在这里，永不入库
<repo>/results/cgmd/<task_id>/summary_metrics.json   # 回传 Git 的精简结果（~10 kB）
<repo>/results/cgmd/<task_id>/figures/*.svg           # 回传 Git 的矢量图（每张 10–50 kB）
```

`.gitignore` 已硬性排除 `*.xtc *.trr *.tpr *.cpt *.gro *.edr *.h5 *.dcd`，并有单元测试断言「已跟踪文件里不得出现任何一个」。

---

## 阶段 1 · 体系设计（先想清楚再烧 GPU）

### 1.1 选肽

* 长度建议 10–40 aa（Martini 3 对短肽最可靠，>60 aa 无结构建模误差变大）；
* 阳离子性：`net_charge(pH 7.4) ≥ +2`（Lys/Arg 数与 Glu/Asp 数之差），这是 AMP 吸附带负电 POPG 膜的驱动力；
* 两亲性：`<µH>`（11 残基窗口、100°/残基）> 0.4、`amphipathic_face_ratio` > 0.4 更可能成孔；
* 快速筛选（零成本，先跑这个再上 GPU）：

```bash
python3 -m cgmd.cli describe GIGKFLHSAKKFGKAFVGEIMNS
```

输出：净电荷、等电点 pI、GRAVY、疏水力矩（螺旋/β）、两亲性比、摩尔质量、组成。

### 1.2 膜模型

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| 脂质组成 | `POPE:POPG = 3:1` | 革兰阴性菌内膜近似：POPE 高曲率倾向（PE 头基小），POPG 提供负电 |
| 面积/脂质 | `-a 0.60 nm²` | Martini 3 平衡值（POPC 0.64、POPE 0.60 量级） |
| 盒子 xy | 12 nm × 12 nm（最小 10 nm） | 太小 → 肽与自身周期像作用；12 nm ≈ 上下层共 ~600 脂质 |
| 盒子 z | 8 nm | 保证水层 ≥ 3 nm（否则膜两侧真空化） |
| 盐 | 0.15 M NaCl | 生理强度，屏蔽过强静电 |
| 温度 | 310 K | 与实验条件一致；Martini 3 温度标定偏差比 M2 小 |
| 时间步 | 20 fs | Martini 3 标准（M2 常用 20–30 fs；>25 fs 需检查能量漂移） |

### 1.3 生产时长预算

| 目的 | 时长 | 说明 |
|------|------|------|
| 观察吸附/插入取向 | 100–300 ns | 足够看到肽从水相贴膜 |
| 判断能否形成稳定水孔 | **1–3 µs** | 打孔是稀有事件，单个 1 µs 未成孔 ≠ 不能成孔，需 3–5 条重复 |
| 统计序参数/厚度收敛 | ≥ 500 ns 平衡段 | 只用后 50% 做统计 |

> 单拷贝 + 单条轨迹的结论只能算**筛选**。定量结论需要 n ≥ 3 独立种子（`simulation.seed`）或副本（`peptide.n_copies`）。

### 1.4 下单（两种方式等价）

**A. 命令行直接跑**

```bash
python3 -m cgmd.cli run --sequence GIGKFLHSAKKFGKAFVGEIMNS --name magainin2 \
        --production-ns 1000 --gpu-id 0 \
        --workdir ~/cgmd-runs/magainin2 --output results/cgmd/magainin2
```

**B. 写成任务文件交给台式机守护（无人值守推荐）**

```json
{
  "schema": "cgmd.task.v1",
  "task_id": "cgmd-20261029-120000-ab12",
  "status": "pending",
  "peptide": { "name": "magainin2", "sequence": "GIGKFLHSAKKFGKAFVGEIMNS", "secondary_structure": "C" },
  "membrane": { "lipids": { "POPE": 3, "POPG": 1 }, "box_xy_nm": 12.0, "salt_M": 0.15, "temperature_K": 310 },
  "simulation": { "production_ns": 1000, "equilibration_ns": 20, "dt_fs": 20, "gpu_id": 0, "seed": -1 }
}
```

```bash
python3 -m core.task_contract validate --path results/status/cgmd_task.json
git add results/status/cgmd_task.json && git commit -m "queue magainin2" && git push
# → 台式机 60 s 内自动认领，手机收到「台式机开始计算」弹窗
```

---

## 阶段 2 · 序列 → 全原子结构（步骤 1/9）

`martinize2` 需要**结构**而不是序列。三条路线，按质量降序：

### 路线 A：已有实验/预测结构（最推荐）

```bash
python3 -m cgmd.cli run ... --task task.json   # task 里写 peptide.structure_pdb = "/path/model.pdb"
```

适用：NMR/X-ray 结构，或 AlphaFold2 / ColabFold 预测（无序肽也建议跑一次，取 rank_001）。

### 路线 B：外部预测器模板

```json
"peptide": { "sequence": "GIGK...", "predictor": "colabfold_batch {fasta} {outdir} --num-recycle 3" }
```

支持占位符 `{fasta}` `{outdir}` `{name}` `{sequence}`；程序会优先挑 `*rank_001*` / `*ranked_0*` 的 PDB，拷贝为 `peptide_atomistic.pdb`。

### 路线 C：内置 NeRF 建模（默认，无需网络）

实现要点（`code/cgmd/cgmd/seq2pdb.py`）：

1. 主链用标准键长键角：`N–CA 1.458 Å`、`CA–C 1.525 Å`、`C–N 1.329 Å`、`C=O 1.231 Å`；`∠N-CA-C 111°`、`∠CA-C-N 116.2°`、`∠C-N-CA 121.7°`；
2. 二面角：默认 φ=-139° / ψ=135°（**理想伸展链**，适合无序肽与膜插入初态）；`"secondary_structure": "H"` 则 φ=-57° / ψ=-47°（理想 α 螺旋）；ω 固定 180°；
3. 每个原子用 **NeRF 内部坐标法**放置：给定 `(A,B,C)` 与目标键长、键角、二面角，解析求出 `D` 的三维坐标；逐残基递推；
4. 侧链：20 种标准残基各有专门构建分支（直链 CG-CD-CE-NZ、分支 CG1/CG2、芳香环先用规则多边形生成再吸附到 CB、Pro 的吡咯环用 torsions 扫描找闭合解、Trp 的吲哚稠环）；
5. **碰撞检查**：任意两原子（残基序号相差 >1）间距 < 1.0 Å 即报 `clashes`，写进 `structure.json`；出现则改用路线 A/B 或加 `-ss H`；
6. 只写重原子（H 由 `martinize2 -ignh` 丢弃），PDB 格式 → 直接喂给 `martinize2`。

> 为什么「理想伸展链」够用：Martini 3 把整个侧链压成 1–2 个珠子，主链 1 个珠子，二级结构细节在 20 ns 预平衡里就被膜环境和弹性网络抹平了。若研究的是「折叠态打孔」而非「吸附-插入-成孔动力学」，才必须用实验结构。

---

## 阶段 3 · martinize2 粗粒化（步骤 2/9）

### 3.1 实际执行的命令（流水线自动生成）

```bash
martinize2 \
  -f peptide_atomistic.pdb \
  -x peptide_cg.pdb \
  -o peptide.top \
  -name Protein \
  -ff martini3001 \
  -ss C \
  -ignh \
  -elastic -ef 500 -el 0.5 -eu 0.9 \
  -p backbone \
  -maxwarn 1
```

### 3.2 参数逐条解释

| 参数 | 作用 | 备注 |
|------|------|------|
| `-ff martini3001` | Martini **3** 力场（vermouth 里的正式名） | 流水线会先 `martinize2 -list-ff` 探测，兼容 `martini3` / `martini30` 命名 |
| `-ss C` | 全部按 coil 处理 | 无序肽/未做 DSSP 时的安全值；有结构可用 `-ss EEEE...` 或 `-dssp` |
| `-ignh` | 丢掉输入里的氢 | 必加，否则重原子映射会报缺原子 |
| `-elastic -ef 500` | 弹性网络（Elastic Network），Fc=500 kJ/mol/nm² | 维持二级结构，防止 CG 蛋白「塌陷」；纯无序肽可减小到 200–300 或 `-ea 0` 关闭衰减 |
| `-el 0.5 -eu 0.9` | 只在 0.5–0.9 nm 之间建弹性键 | 下限避免 i,i+2 过近，上限避免跨链串键 |
| `-p backbone` | 输出**主链**位置约束文件（`POSRES` 段） | 预平衡阶段靠它把肽按在原位，避免一上来就被膜挤变形 |
| `-maxwarn 1` | 容忍 1 条警告 | 常见为「missing atom OXT」 |
| `-name Protein` | 分子名占位 | 真正 moleculetype 名会是 `Protein_0`（按链编号），拓扑重建时会用到 |

### 3.3 输出与检查

```
peptide_cg.pdb      # 珠子坐标（BB / SC1 / SC2 / SC3 …）
peptide.top         # #include "Protein_0.itp" + [ molecules ] Protein_0 1
Protein_0.itp       # [ atoms ][ bonds ][ constraints ][ angles ][ dihedrals ][ position_restraints ]
```

* 珠子数经验：`beads ≈ 1.2–2 × 残基数`（Magainin-2 23 aa → 54 珠）；
* `Protein_0.itp` 里 `[ position_restraints ]` 段在 `#ifdef POSRES` 内，预平衡 mdp 必须 `define = -DPOSRES` 才生效。

### 3.4 常见坑

| 报错/现象 | 原因 | 处理 |
|-----------|------|------|
| `Could not find force field 'martini3001'` | 未装 vermouth 的 Martini 3 力场文件 | `pip install vermouth`（0.15+ 自带）；或 `-ff-dir <...>/force_fields -map-dir <...>/mappings` |
| `Missing atom XXX:OXT` | C 端少了 OXT | 无害；`-maxwarn 1` 放行，或建模时补 OXT |
| `Residue ... has no mapping` | 非标准残基（修饰/非天然） | 用 `-mutate` 映射到标准残基，或改用全原子 |
| 珠子数明显偏少 | `-ss` 与实际结构冲突导致断链 | 用 `-dssp` 或显式 `-ss` 序列 |
| 该力场下 `-elastic` 报错 | 某些版本需要 `-eunit molecule` | 加 `-eunit molecule` |

---

## 阶段 4 · insane 建膜（步骤 3/9）

### 4.1 实际执行的命令

```bash
insane \
  -f peptide_cg.pdb \
  -o system.gro \
  -p insane.top \
  -pbc rectangular \
  -x 12.000 -y 12.000 -z 8.000 \
  -a 0.600 \
  -sol W \
  -salt 0.150 \
  -l POPE:3 -l POPG:1
```

### 4.2 参数解释与两个版本差异

| 参数 | 作用 | 注意 |
|------|------|------|
| `-f` | 待嵌入的 CG 结构（肽） | 坐标单位 Å，insane 内部转 nm |
| `-l POPE:3 -l POPG:1` | 单一 `-l` = 上下层同组成 | 想上下不对称用 `-l`（下层）+ `-u`（上层） |
| `-x/-y/-z` | 直接给盒子尺寸（nm） | **比 `-d/-dz` 更可控**：`-d` 是「周期像最小距离」的语义，容易被肽尺寸放大 |
| `-a 0.600` | 面积/脂质（nm²） | 决定脂质数量；盒面积 ÷ a ÷ 2 ≈ 单层脂质数 |
| `-sol W` | Martini 水 | 旧名 `SOL` 也能被别名映射 |
| `-salt 0.15` | 中和 + 0.15 M NaCl | 程序自动按体系净电荷先中和再加盐（`NA+`/`CL-`） |
| `-ff M3` | **新版权 insane 才有**（≥1.2 / Git 主线） | 流水线会 `insane --help` 探测；旧版（PyPI 1.1-dev）传了会 `Unrecognized option '-ff'`，程序自动省略 |

> 关键工程细节：**盒子自动扩张**。流水线会读 `peptide_cg.pdb` 的三向尺寸，取 `max(请求值, 肽尺寸 + 2 nm)`，避免「肽比盒子还长」导致周期像自相互作用（这是新手最常见的假象之一）。

### 4.3 输出与自检

```
system.gro   # 完整体系坐标（肽 + 脂质 + 水 + 离子）
insane.top   # 只有 #include "martini.itp" 与 [ molecules ] 段 —— 名字是脏的，必须重建！
```

命令行会打印：

```
; 351 lipids in upper leaflet, 341 lipids in lower leaflet   ← 上下层数量应接近
; NDX Solute 1 52
; Charge of protein: +3.0
; Charge of membrane: -172.0
; Total charge: 0.0                                           ← 必须接近 0（已加反离子）
```

若 `Total charge` 不为 0：insane 的自动中和可能被组成判断干扰，需手工补离子（`gmx genion -neutral` 或改 `-salt`）。

---

## 阶段 5 · 拓扑重建（步骤 4/9，最容易翻车）

### 5.1 为什么必须重建

`insane.top` 只写了两样东西：

```
#include "martini.itp"     ← 这个文件根本不存在
[ molecules ]
Protein 1                  ← Protein 是占位名，真实名是 Protein_0
POPE 263
POPG 87
W 10630
NA+ 203                    ← Martini 3 里叫 NA（NA+ 是 Martini 2 遗留）
CL- 31
```

直接 `grompp` 会得到 `Invalid moleculetype name` / `Atomtype X not found` / `No such file martini.itp`。

### 5.2 重建算法（`code/cgmd/cgmd/topology.py`）

1. **递归索引**力场目录下所有 `*.itp` 的 `[ moleculetype ]`（名字 + nrexcl + 原子数），Martini 3 全套约 300 个 moleculetype；
2. 找出含 `[ defaults ]` 或 `[ atomtypes ]` 的**基文件**（`martini_v3.0.0.itp`），它必须排在第一；
3. **别名归一**：`NA+→NA`、`CL-→CL`、`K+→K`、`CA2+→CA`、`SOL/HOH/TIP3→W`；
4. `Protein → <martinize2 真实名>`（如 `Protein_0`），并 `#include` 其 itp；
5. **按需 include**：只 include 实际出现过的分子定义文件（脂质/溶剂/离子各一个），避免把 16 MB 的 `martini_v3.0.0.itp` 全量读入；
6. 写出 `topol.top`，并**交叉校验原子数**：`Σ(moleculetype 原子数 × 分子数)` 必须等于 `system.gro` 头部的原子数。

### 5.3 产物示例

```
; CGMD-Engine topology -- generated automatically
#include "../../forcefields/martini3/martini_v3.0.0.itp"
#include "../../forcefields/martini3/martini_v3.0.0_phospholipids_v1.itp"
#include "../../forcefields/martini3/martini_v3.0.0_solvents_v1.itp"
#include "../../forcefields/martini3/martini_v3.0.0_ions_v1.itp"
#include "Protein_0.itp"

[ system ]
CGMD magainin2 in POPE:POPG bilayer

[ molecules ]
Protein_0              1
POPE                 164
POPG                  54
POPE                 151
POPG                  50
W                   4059
NA                   101
```

校验报告（写进 `topology.json`）：

```json
{ "gro_atoms": 9242, "topology_atoms": 9242, "consistent": true, "difference": 0 }
```

**原子数对不上时不要硬跑**：99% 是 `[ molecules ]` 里少了某一行或多写了一行，或 itp 被同名文件覆盖。

### 5.4 常见报错

| grompp 报错 | 原因 | 处理 |
|-------------|------|------|
| `No such file or directory: martini.itp` | 没重建拓扑 | 走本阶段 |
| `Invalid moleculetype name 'NA+'` | 别名没归一 | 同上（或手工 sed） |
| `Atomtype Q5n not found` | 基文件没 include / 顺序错 | 基文件必须第一个 include |
| `No such moleculetype POPE` | 脂质 itp 未 include | 检查 `-l` 里的名字与 itp 中是否一致（大小写敏感） |
| `number of coordinates in gro file does not match topology` | 原子数不一致 | 看 `topology.json` 的 `difference` |

---

## 阶段 6 · 索引文件（步骤 5/9）

`gmx make_ndx` 是交互式的，且默认组对 Martini 毫无意义（每个珠子都算 "atom"）。因此直接按 `.gro` 的残基名/原子名生成 `index.ndx`：

| 组名 | 内容 | 用途 |
|------|------|------|
| `System` | 全部 | 温压耦合、能量输出 |
| `Peptide` | 前 N 个原子（N = 肽珠子数 × 拷贝数） | 位置约束、MSD、构象分析 |
| `Membrane` | 所有脂质 | 膜相关分析 |
| `POPE` / `POPG` | 按残基名 | 分种类序参数、横向扩散 |
| `Water` | `W` | 水孔统计、水密度 |
| `Ions` | `NA/CL/K/CA/MG` | 离子-肽静电、离子桥 |
| `Headgroups` | `PO4/NH3/GL0/GL1/GL2/NC3` | 膜厚、头基取向 |
| `Tails` | `C1A/D2A/C3A/C4A/C1B/C2B/C3B/C4B` | 序参数、尾链有序度 |

---

## 阶段 7 · 能量最小化 EM（步骤 6/9）

### 7.1 mdp（Martini 3 标准非键设置）

```ini
integrator              = steep
emtol                   = 10.0
emstep                  = 0.001
nsteps                  = 5000

nstlist                 = 20
cutoff-scheme           = Verlet
verlet-buffer-tolerance = 0.005
pbc                     = xyz

coulombtype             = reaction-field      ; Martini 标配，不是 PME
rcoulomb                = 1.1                 ; nm
epsilon_r               = 15                  ; 粗粒化介电（含极化平均）
epsilon_rf              = 0
vdwtype                 = cutoff
vdw-modifier            = Potential-shift
rvdw                    = 1.1
```

**为什么是 reaction-field 而不是 PME**：Martini 的电荷是珠子上的「平均电荷」，ε_r=15；PME 会引入不必要的高频误差与开销，reaction-field + 1.1 nm 截断是社区标准。

### 7.2 执行

```bash
gmx grompp -f em.mdp -c system.gro -p topol.top -n index.ndx -o em.tpr -maxwarn 2
gmx mdrun -deffnm em -nb cpu -ntomp 4          # EM 用 CPU 反而更快，避免 GPU 传输开销
```

### 7.3 判据与排查

* 成功：日志 `Steepest Descents converged to Fmax < 10 in 812 steps`，`Maximum force < 100 kJ/mol/nm`；
* 未收敛但最大力 100–1000：可接受，继续 NPT（预平衡会进一步松弛）；
* 最大力 > 1000 或 `Potential Energy` 为正的大数：**体系有原子重叠**（通常是 insane 的 `-rand` 太小或盒子被压缩），处理顺序：
  1. 换 `integrator = cg`（共轭梯度）再跑 5000 步；
  2. 回到阶段 4 加大 `-d`/盒子或提高 `-a`；
  3. 检查肽是否与膜重叠（`-fudge 0.1` 增大到 0.2）。

---

## 阶段 8 · 20 ns NPT 预平衡（步骤 7/9）

### 8.1 mdp 要点

```ini
integrator      = md
dt              = 0.02          ; 20 fs
nsteps          = 1000000       ; ×0.02 ps = 20 ns
constraints     = none          ; Martini 不用 SHAKE，靠势函数
gen-vel         = yes
gen-temp        = 310
gen-seed        = -1            ; -1 = 随机；做重复实验时固定成整数
define          = -DPOSRES      ; 让 martinize2 的主链位置约束生效

tcoupl          = v-rescale
tc-grps         = System
tau-t           = 1.0
ref-t           = 310
pcoupl          = c-rescale     ; 预平衡用弱耦合，比 P-R 稳
pcoupltype      = semiisotropic ; 膜体系必须 xy 与 z 分开
tau-p           = 4.0
compressibility = 3e-4 3e-4
ref-p           = 1.0 1.0
refcoord-scaling= com
```

### 8.2 预平衡期间该盯什么

用 `gmx energy` / 本仓库的 `node_agent.py` 实时看：

| 量 | 期望 | 异常信号 |
|----|------|----------|
| 温度 | 310 ± 5 K（前 1 ns 可到 ±10） | 持续漂移 → `tau-t` 太大或 `dt` 太大 |
| 压力 | 1 bar ± 200 bar（瞬时波动正常） | 均值长期偏离 → 膜未平衡/盒子太小 |
| 势能 | 快速下降后平台 | 持续下降或噪声巨大 → 有空洞/重叠 |
| 膜厚 | 3.5–4.2 nm（POPE:POPG） | < 3 nm → 脂质被抽走 |
| 肽位置 | 在膜内小幅涨落，不横向漂走 | 跑出水相 → 初始取向/插入深度不对，考虑 `-dm`（insane 的 memshift） |
| 密度 | ~1000 kg/m³ 量级（Martini 水 1 bead/0.03 nm³） | 真空层 → z 方向水不够 |

### 8.3 位置约束的取舍

* 默认 `-p backbone`（主链约束，Fc=1000）：保住二级结构，让脂质先围绕肽松弛；
* 若研究对象是**肽自身的构象变化**（如螺旋→孔道态），预平衡后应**逐级释放**约束：20 ns (Fc=1000) → 5 ns (Fc=100) → 0；
* 纯无序肽（coil）：可用 `-p none` 减少人为限制。

---

## 阶段 9 · 微秒级 GPU 生产模拟（步骤 8/9）

### 9.1 mdp 相对预平衡的改动

```ini
continuation            = yes      ; 从 eq.cpt 继续，不重新给速度
gen-vel                 = no
pcoupl                  = Parrinello-Rahman   ; 生产段用 P-R 得到正确的体积涨落
tau-p                   = 12.0
nstenergy               = 5000
nstlog                  = 2500
nstxout-compressed      = 50000    ; 1 ns 一帧（20 fs × 50000）；1 µs → 1000 帧
compressed-x-grps       = System
```

`nstxout-compressed` 策略：分析只需要 ~1 ns 帧间隔（打孔/序参数的时间尺度是 ns），**不要**每 10 ps 存一帧——那会把 1 µs 轨迹撑到几十 GB 且分析慢一个数量级。

### 9.2 mdrun 命令（GPU 关键参数）

```bash
gmx mdrun -deffnm prod \
  -nb gpu -pme cpu -bonded gpu \
  -gpu_id 0 -ntomp 8 \
  -dlb yes -pin on \
  -cpi prod.cpt        # 断点续跑（崩溃/重启后自动接上）
```

* `-nb gpu`：非键（短程 LJ + reaction-field）放 GPU —— Martini 的绝大部分算力在这里；
* `-pme cpu`：reaction-field 其实不用 PME，但显式声明可避免 GROMACS 把 PME 也塞到 GPU 上与 -nb 抢资源；
* `-bonded gpu`：约束/键角放 GPU；
* `-ntomp`：一般设成 `物理核数 / GPU 数`，过多反而掉速；
* `-dlb yes`：动态负载均衡（多 GPU/多节点时必须）；
* **续跑**：`-cpi` 存在时自动接着跑；同时 `stages.json` 记录阶段状态，重跑同一条命令不会重算已完成的阶段。

### 9.3 性能参考（20k 珠子量级体系，量级参考）

| 硬件 | `ns/day`（Martini 3，20 fs） | 1 µs 需要 |
|------|------------------------------|-----------|
| RTX 4090 | 1200–2500 | 10–20 h |
| RTX 3090 | 800–1500 | 16–30 h |
| RTX 4070 Ti | 600–1200 | 20–40 h |
| 纯 CPU 32 核 | 60–150 | 7–17 天 |

> 实测值请以 `prod.log` 里的 `Performance: X ns/day` 为准；本仓库的 `node_agent.py` 会自动解析它并推手机。

### 9.4 发散（爆炸）的识别与处置

日志里出现下列任一，即判定发散，**立即停止等待**（`node_agent.py` 会推 `rotating_light` 告警）：

* `LINCS WARNING` 连续出现 / `Too many LINCS warnings`；
* `Step N, time T (ps)  NaN` 或 `blowing up`；
* `Water molecule starting at atom N can not be settled`；
* `Segmentation fault` / `CUDA_ERROR_OUT_OF_MEMORY`。

处置顺序：

1. 回看最后一帧未被污染的 `.gro`（`gmx trjconv -dump`），检查是否有珠子跑到盒外/重叠；
2. 缩小 `dt`（20 → 10 fs）重跑最后 1 ns；
3. 检查 `tau-p` 是否过小、`compressibility` 是否写错（常见：把 3e-4 写成 3e-5）；
4. 频繁在特定构象发散 → 该肽可能真的导致膜破裂，这正是「打孔」信号，需结合水孔指标判断而不是一味降 dt。

---

## 阶段 10 · 轨迹分析（步骤 9/9）

### 10.1 三个核心指标的定义（与实现一一对应）

#### (1) 嵌膜深度 `z_distance`

```
z(t) = peptide_centroid_z(t) − membrane_midplane_z(t)      （最小镜像，nm）
```

* 中平面用**磷酸基团（PO4）**的圆均值求（把 z 映射到圆周角 2πz/Lz 再取平均，避免跨周期断裂）；
* 负值 = 偏向下层小叶；`|z| < 0.8 nm` 记为核心区，`|z| < 1.5 nm` 记为界面/已插入；
* 同时输出**逐残基平均深度**（每个肽珠相对于中平面的平均 z），可看出哪一段插得最深（通常是 N 端或疏水面）。

#### (2) 脂质序参数 `S`

```
S = <P2(cosθ)> = <(3cos²θ − 1)/2>
θ = 相邻尾链珠子连线 与 膜法向(z) 的夹角
```

* 尾链相邻对：sn-1 = `C1A-D2A-C3A-C4A`，sn-2 = `C1B-D2B-C2B-C3B`（与 Martini 拓扑顺序一致）；
* 参考值：完整 POPE 双层 `S ≈ 0.85–0.95`；肽周围/成孔区显著下降（0.4–0.7）；
* 输出总体（sn1/sn2）与**分脂质种类**（POPE/POPG）的平均值。

#### (3) 水孔指标 `pore`

```
圆柱半径 R = 1.2 nm（围绕肽横向质心）
膜芯半高 h = 0.9 nm（|z| < h）
N_core(t) = 该圆柱 ∩ 膜芯内的水珠数

pore_score(t) = (N_core / V_cyl) / ρ_bulk
V_cyl = πR²·2h ，ρ_bulk 由 |z| ∈ [2.5, 3.5] nm 的 1 nm 平层估算

pore_formed = (pore_score > 0.25 的帧占比) > 10%（平衡段内）
```

* 判据可调：`analysis.pore_radius_nm`、`analysis.water_core_halfheight_nm`、阈值写在 `summary_metrics.json` 的 `pore.threshold` 里，保证可复现；
* 为什么用水密度而不是「孔半径」：Martini 水珠尺寸 0.47 nm，直接算几何半径噪声大，密度比更稳。

#### (4) 膜厚 `thickness`

上下层磷酸基团平均 z 之差；POPE:POPG 3:1 正常值 3.5–4.2 nm，显著变薄说明成孔/膜被抽出。

### 10.2 命令

```bash
# 流水线里自动执行；也可单独跑
python3 - <<'PY'
import sys; sys.path[:0] = [".", "code/cgmd"]
from cgmd import analyze
m = analyze.analyse_trajectory("eq.gro", "prod.xtc", peptide_atoms=54,
                               lipid_resnames=["POPE", "POPG"], max_frames=400)
print(m["membrane_insertion"]["z_distance_mean_nm"], m["lipid_order"]["mean"], m["pore"]["pore_formed"])
PY
```

### 10.3 常见坑

| 坑 | 表现 | 处理 |
|----|------|------|
| 忘记 `-pbc` / 用错参考结构 | z 值出现 ±Lz 跳变 | 用 `eq.gro`（与 xtc 同一坐标系）作拓扑参考，代码内部已做最小镜像 |
| 用了未平衡轨迹 | 序参数/厚度前 10 ns 单调漂移 | 统计只用后 50%（`equilibrated_fraction=0.5`） |
| 帧间隔太密 | 分析 1 h+，JSON 爆表 | `nstxout-compressed` 设 1 ns；分析再按 `max_frames` 抽稀 |
| 单条轨迹下结论 | 是否成孔判定反复 | n ≥ 3 独立种子，报「成孔概率」而非「成孔与否」 |
| 肽穿膜到下层 | z 从 -2 跳到 +2 | 属真实事件（translocation），需单独分子事件统计，不能只取平均 |

### 10.4 回传结果的结构

```json
{
  "schema": "cgmd.summary.v1",
  "task_id": "cgmd-20261029-120000-ab12",
  "peptide": { "sequence": "GIGKFLHSAKKFGKAFVGEIMNS", "net_charge_ph7_4": 3.03,
               "isoelectric_point": 10.58, "gravy": 0.083,
               "hydrophobic_moment_helix": 0.686, "amphipathic_face_ratio": 0.714 },
  "system":   { "lipid_ratio": "3:1", "box_nm": [12.0, 12.0, 8.0], "atoms": 9242 },
  "simulation": { "production_ns": 1000, "completed_ns": 1000, "ns_per_day": 1250.5,
                  "lincs_warnings": 0, "diverged": false },
  "membrane_insertion": { "z_distance_mean_nm": -0.41, "inserted_fraction": 1.0,
                          "per_residue_z_nm": [0.86, 0.58, ...] },
  "lipid_order": { "sn1": 0.949, "sn2": 0.949, "mean": 0.949, "per_species": {...} },
  "pore": { "pore_formed": true, "pore_score_mean": 0.31, "water_in_core_mean": 19.1,
            "cylinder_radius_nm": 1.2, "core_halfheight_nm": 0.9 },
  "membrane": { "thickness_nm": 3.9 },
  "figures": ["figures/z_distance_vs_time.svg", "figures/lipid_order_vs_time.svg",
              "figures/water_in_core_vs_time.svg", "figures/peptide_summary.svg",
              "figures/bilayer_thickness.svg"]
}
```

体积控制：时间序列最多 400 点（`timeseries` 段 ≤121 点），整体 < 1 MB（实测 ~10 kB）；图形只出 SVG。

---

## 阶段 11 · 回传 Git 与手机推送（无人值守）

### 11.1 状态机

```
idle → pending → claimed → running → completed_on_desktop
                              ↘ failed_on_desktop / cancelled
```

* 任一客户端把 `results/status/cgmd_task.json` 的 `status` 改成 `pending` 并 push；
* 台式机每 60 s 轮询：`flock` 防重入 → 校验 origin（必须是 `hukeying85-ux/0fuye`）→ `fetch`/`reset` → 认领 → WSL2 跑流水线；
* 完成后**只**提交 `results/status/` 与 `results/cgmd/<task_id>/`，push 回同一分支；
* 认领超过 6 h 的 `claimed/running` 视为孤儿，允许重领（机器重启场景）。

### 11.2 手机推送（零 Token）

```bash
python3 code/federation/node_agent.py test     # 验证链路
python3 code/federation/node_agent.py watch --log ~/cgmd-runs/<id>/prod.log --progress-every 900
```

推送时机：开始 / 每 10% 或每 15 min / 完成 / 发散；通道 `ntfy.sh` topic `arena-beacon-95bc796a66`，`priority: 5`（弹窗 + 震动），正文含北京时间戳与 `ns/day`、ETA、膜插入深度。

### 11.3 Git 卫生红线

```gitignore
*.xtc  *.trr  *.tpr  *.cpt  *.gro  *.edr  *.h5  *.dcd
```

流水线还有 `prune()` 兜底：即使有人手动把轨迹拷进仓库目录，提交前也会被删除并记录到 `runtime.pruned`。

---

## 12. 参数速查表（直接抄）

| 阶段 | 关键参数 | 值 |
|------|----------|-----|
| 全部 | `cutoff-scheme` | `Verlet`, `verlet-buffer-tolerance = 0.005` |
| 全部 | `coulombtype` / `epsilon_r` | `reaction-field` / `15` |
| 全部 | `rcoulomb` / `rvdw` | `1.1` / `1.1` nm |
| 全部 | `vdw-modifier` | `Potential-shift` |
| 全部 | `nstlist` | 20 |
| EM | `integrator`/`emtol`/`emstep` | `steep` / 10 / 0.001 |
| EQ | `dt` / `nsteps` | 0.02 ps / 1,000,000（20 ns） |
| EQ | `tcoupl`/`tau-t` | `v-rescale` / 1.0 |
| EQ | `pcoupl`/`tau-p` | `c-rescale` / 4.0，semiisotropic |
| PROD | `pcoupl`/`tau-p` | `Parrinello-Rahman` / 12.0 |
| PROD | `nstxout-compressed` | 50,000（1 ns） |
| mdrun | GPU | `-nb gpu -pme cpu -bonded gpu -gpu_id 0` |
| 分析 | 孔圆柱/芯高 | 1.2 nm / 0.9 nm |

---

## 13. 质量控制清单（跑完 1 µs 后逐条打勾）

- [ ] `topology.json.validation.consistent == true`（原子数一致）
- [ ] EM 收敛或最大力 < 1000
- [ ] 预平衡最后 5 ns 温度 310 ± 5 K、无持续漂移
- [ ] 膜厚 3.5–4.2 nm（不成孔区域）
- [ ] `simulation.diverged == false`，`lincs_warnings == 0`
- [ ] `summary_metrics.json` < 1 MB，帧数 > 100
- [ ] 至少 3 条独立种子（`seed` 不同）重复，结论报概率
- [ ] `results/` 下无任何 `.xtc/.trr/.tpr/.cpt/.gro`
- [ ] 手机收到了开始/完成/（若发散）告警三类推送

---

## 14. 一页纸命令流程（复制粘贴版）

```bash
# 0) 环境
bash code/cgmd/setup_env.sh --check

# 1) 肽筛选
python3 -m cgmd.cli describe GIGKFLHSAKKFGKAFVGEIMNS

# 2) 干跑（打印全部命令，不碰 GPU）
python3 -m cgmd.cli plan --sequence GIGKFLHSAKKFGKAFVGEIMNS \
        --workdir ~/cgmd-runs/demo --output results/cgmd/demo

# 3) 真跑（EM → 20 ns NPT → 1 µs）
python3 -m cgmd.cli run --task results/status/cgmd_task.json \
        --workdir ~/cgmd-runs/<task_id> --output results/cgmd/<task_id> --gpu-id 0

# 4) 手机跟踪
python3 code/federation/node_agent.py watch --log ~/cgmd-runs/<task_id>/prod.log

# 5) 结果
cat results/cgmd/<task_id>/summary_metrics.json | head -40
ls results/cgmd/<task_id>/figures/
```

---

## 15. 参考文献

1. Souza P.C.T. *et al.* **Martini 3: a general purpose force field for coarse-grained molecular dynamics.** *Nat. Methods* 18, 382–388 (2021). doi:10.1038/s41592-021-01098-3
2. Kroon P.C. *et al.* **Martinize2 and Vermouth: unified framework for topology generation.** *eLife* 12:RP90627 (2024). doi:10.7554/eLife.90627.2
3. Wassenaar T.A. *et al.* **Computational Lipidomics with insane: A Versatile Tool for Generating Custom Membranes for Molecular Simulations.** *J. Chem. Theory Comput.* 11, 2144–2155 (2015).
4. Marrink S.J. *et al.* **The MARTINI Force Field: Coarse Grained Model for Biomolecular Simulations.** *J. Phys. Chem. B* 111, 7812–7824 (2007).
5. GROMACS 2024 reference manual — `mdp` 选项与 `mdrun` GPU 调优章节。
6. Melo M.N. *et al.* **Parameters for Martini sterols and phosphatidylcholines.** *J. Chem. Theory Comput.* 11, 3453–3462 (2015)（膜参数标定背景）。

---

*文档与代码同源：所有参数/路径/指标定义均可在 `code/cgmd/cgmd/*.py`、`code/cgmd/mdp/*.mdp.in` 中逐行核对。*
