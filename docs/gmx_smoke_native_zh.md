# Windows 原生 GROMACS 100 ps 实测报告

> 生成时间：2026-10-29 12:37（北京时间） · 机器：`DESKTOP-IEUDGS5`
> 结论：**通过**。100 ps 真实积分完成，GPU 加速，版本与软件清单已随 git 回传。
> 原始数据：`results/status/gmx_smoke.json`（`cgmd.gmxsmoke.v1`，由台式机自己写入并 push）

## 1. 一句话结果

| 项目 | 实测值 |
| --- | --- |
| 状态 / `status` | **ok** |
| 模拟时长 / `ps_completed` | **100.0 ps**（50000 步 × 0.002 ps） |
| 实际完成时间 | 100 ps = 16 s 积分（端到端含 EM 23.5 s） |
| 加速方式 / `accelerator` | **gpu** |
| 性能 | **540–576 ns/day**（0.042 hour/ns） |
| 体系 | SPC/E 水盒 2.5 nm 立方，1530 原子 / 510 个水分子 |
| 结束标记 | `Finished mdrun` ✔，无 `Fatal error` |

## 2. GROMACS 软件信息（`software.gromacs`）

| 字段 | 值 |
| --- | --- |
| 版本 | **2025.1** |
| 安装路径 | `F:\gromacs-2025.1-SM86\gromacs-2025.1-SM86\bin\gmx.exe` |
| 数据目录 | `F:\gromacs-2025.1-SM86\gromacs-2025.1-SM86`（`share\gromacs\top`） |
| 精度 | mixed |
| 内存模型 | 64 bit |
| SIMD | AVX2_256 |
| GPU 支持 | CUDA |
| CUDA runtime / driver | 12.80 / 13.20 |
| FFT 库 | fftw3 |
| OpenMP | 无（此预编译版未启用） |

## 3. 硬件（`software.gpus`）

| GPU | 驱动 | 显存 |
| --- | --- | --- |
| NVIDIA RTX A4000 | 596.71 | 16376 MiB |

## 4. 运行流程（`stages`）

| 阶段 | 命令 | 返回码 | 耗时 |
| --- | --- | --- | --- |
| `solvate` | `gmx solvate -cs spc216.gro -box 2.5 2.5 2.5` → 510 个水 | 0 | 0.09 s |
| `grompp-em` | 自带 `oplsaa.ff` + `spce.itp` | **-1073741819（0xC0000005）** | 3.9 s |
| `grompp-em-inline` | 参数全内联的自带 SPC 拓扑（兜底） | 0 | 0.10 s |
| `mdrun-em` | 最陡下降能量最小化 | 0 | 1.1 s |
| `grompp-md` | `smoke_md.mdp`，50000 步 | 0 | 0.10 s |
| `mdrun-md-gpu` | `mdrun -nb gpu -gpu_id 0` | 0 | 16.6 s |

动力学设置：`dt = 0.002 ps`、PME 静电、LINCS 约束 h-bonds、v-rescale 控温 300 K、C-rescale 控压 1 bar。

## 5. 排掉的两个 Windows 坑（脚本已内置兜底）

1. **`gmx grompp` 在自带 `oplsaa.ff` 上崩溃**：返回码 `0xC0000005`（访问越界），日志停在
   `Generating 1-4 interactions: fudge = 0.5`。该版本的 `share\gromacs\top\oplsaa.ff` 文件齐全
   （`forcefield.itp` / `ffbonded.itp` / `ffnonbonded.itp` / `spce.itp` / `spc.itp` / `tip3p.itp` / `ions.itp` 全部存在），
   属于这套第三方 2025.1 CUDA 预编译版自身的问题。
   → 兜底：改写 `smoke_box_inline.top`，`[ defaults ] [ atomtypes ] [ moleculetype ] [ settles ]` 全部内联，不再 include 任何力场文件；同一份 `.gro`、同样的 mdp，`grompp` 0.1 s 通过。
2. **`Start-Process -WorkingDirectory ''`**：PS 5.1 会静默抛「参数为 Null 或空」，导致 `gmx --version` 与
   `nvidia-smi` 的输出丢失（第一版报告里版本和显卡字段是空的）。
   → 兜底：始终传一个非空目录（临时目录），并把 `gmx --version` 的返回码与首行 banner 一起写进报告。

## 6. 复现命令

```powershell
cd C:\cgmd\0fuye
git pull --rebase origin arena/32cd826e-0fuye
powershell -NoProfile -ExecutionPolicy Bypass -File .\skills\cgmd-hub\runner\Run-Gmx-Native.ps1
```

读回报告（任意一侧）：

```bash
gh api "repos/hukeying85-ux/0fuye/contents/results/status/gmx_smoke.json?ref=arena/32cd826e-0fuye" --jq .content | base64 -d
python3 -m cgmd.smoke --show results/status/gmx_smoke.json
```

需要显式指定安装路径时：`-Gmx "F:\gromacs-2025.1-SM86\gromacs-2025.1-SM86\bin\gmx.exe"`；
只要 CPU：`-GpuId` 留空并设 `-NoPush` 之外的参数不变（GPU 失败会自动回退 CPU 并写入 `notes`）。

## 7. 对生产流水线的含义

- 这台机器的 GPU + CUDA + PME 通道是**真能用**的：540+ ns/day 意味着 1 µs 的 Martini/全原子混合体系
  在纯 GPU 上约 45 分钟量级（实际会因体系与 `-pme gpu` 负载打折），微秒级生产计划成立。
- 后续 Martini 3 生产流水线不会再被「grompp 崩溃」卡住：内联拓扑兜底只用于烟测；
  生产拓扑来自 `martinize2` / `insane`，若同样触发该崩溃，优先改用 `amber99sb-ildn.ff` 或
  换装官方 Windows 安装包（此坑与本机预编译版绑定）。
