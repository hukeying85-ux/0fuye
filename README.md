# CGMD-Engine · 台式机零闪窗守护 + 手机秒推信标 + Martini 3 抗菌肽膜打孔流水线

> 仓库：`hukeying85-ux/0fuye`（严格锁定，脚本会拒绝任何其它 origin）
> 目标机：Windows 11 高性能台式机 + WSL2 (Ubuntu) + NVIDIA GPU
> 手机端：小米（已订阅 ntfy 频道 `arena-beacon-95bc796a66`）
> 令牌消耗：**0**（本地 GROMACS + 本地 ntfy POST，不经过任何大模型）

---

## 0. 台式机上「仅需首次运行一次」的 1 行初始化命令

在**普通（非管理员）PowerShell 窗口**里粘贴执行这一行（首次会提示粘贴一次 GitHub Token，输入时不可见）：

```powershell
git clone -b arena/32cd826e-0fuye https://github.com/hukeying85-ux/0fuye.git C:\cgmd\0fuye 2>$null; powershell -NoProfile -ExecutionPolicy Bypass -File C:\cgmd\0fuye\skills\cgmd-hub\bootstrap_desktop.ps1
```

> 该分支（`arena/32cd826e-0fuye`，PR #1）合并进 `main` 之后，可以去掉 `-b` 参数：
>
> ```powershell
> git clone https://github.com/hukeying85-ux/0fuye.git C:\cgmd\0fuye 2>$null; powershell -NoProfile -ExecutionPolicy Bypass -File C:\cgmd\0fuye\skills\cgmd-hub\bootstrap_desktop.ps1
> ```
>
> 仓库已经克隆过时，直接跑第二段即可；`2>$null` 保证「已存在」的克隆失败不会中断后续初始化。

这一行会一次性完成：

| 步骤 | 内容 |
| --- | --- |
| 1 | 自检 PowerShell / git / WSL2 / `nvidia-smi` |
| 2 | 克隆（或复用）`hukeying85-ux/0fuye`，**校验 origin，不是本仓库立即中止** |
| 3 | **仅在本仓库内**写入 git 身份与凭据（`git config --local`），全局 git 配置与其他 GitHub 账号**完全不动** |
| 4 | 进 WSL2 跑 `code/cgmd/setup_env.sh`：GROMACS / CUDA / Martini 3 / MDAnalysis 全量自检 |
| 5 | 生成 `skills/cgmd-hub/config/cgmd_hub.local.json`（已 gitignore）与空闲任务文件 |
| 6 | 编译 `/target:winexe` 静默包装器 `CGMDHub.exe` |
| 7 | 注册计划任务 `CGMD-Hub-Poll`：**每 60 s 静默轮询**，入口是 `wscript.exe`（GUI 子系统，物理上不可能弹出控制台黑框） |
| 8 | 立刻做一次静默验证轮询 + 往手机推一条上线信标 |

轮询分支 = **克隆里当前 checkout 的分支**（上面这行就是 `arena/32cd826e-0fuye`）。想固定到别的分支，在 `skills/cgmd-hub/config/cgmd_hub.local.json` 里改 `"branch"` 即可。

> 全部 PowerShell / VBS / C# 源文件都是**纯 ASCII**（有单元测试强制校验），因此 GBK 代码页的 Windows PowerShell 5.1 也不会解析乱码。

## 1. 三层架构总览

```
                         ┌─────────────────────────────┐
   手机 / Arena / 笔记本  │  results/status/cgmd_task.json │  status = "pending"
                         └──────────────┬──────────────┘
                                        │  git push（任意客户端）
   ┌────────────────────────────────────▼──────────────────────────────────┐
   │ Windows 11 台式机                                                     │
   │  wscript.exe  ──▶ Invoke-CgmdPoll.ps1  （每 60 s，零窗口）             │
   │     │  1. flock 防重入  2. 校验 origin  3. fetch/reset 当前分支        │
   │     │  4. 读任务状态    5. 调 WSL2 runner 6. 只提交 results/ 并 push  │
   │     ▼                                                                 │
   │  WSL2 + CUDA: desktop_runner.py                                       │
   │     claim → Martini3 流水线 → 分析 → status=completed_on_desktop      │
   │     └── node_agent.py watch prod.log ──▶ ntfy.sh ──▶ 小米手机弹窗震动 │
   └───────────────────────────────────────────────────────────────────────┘
```

| 目录 | 作用 |
| --- | --- |
| `core/` | 三层共用契约（零依赖）：任务状态机、ntfy 信标、GROMACS 日志解析 |
| `skills/cgmd-hub/` | Windows 侧零闪窗守护：`bootstrap_desktop.ps1`、轮询脚本、计划任务注册、winexe 包装器 |
| `code/federation/node_agent.py` | 本地零 Token 守护：解析 `prod.log`，推送开始/进度/完成/发散 |
| `code/federation/desktop_runner.py` | WSL2 侧任务执行器：认领任务 → 跑流水线 → 回写 JSON |
| `code/cgmd/` | Martini 3 流水线：`martinize2` + `insane` + GROMACS GPU + 分析出图 |
| `results/status/` | 与手机/外部客户端握手的状态文件（`cgmd_task.json`、`cgmd_result.json`） |
| `results/cgmd/<task_id>/` | 回传 Git 的**精简结果**：`summary_metrics.json` + `figures/*.svg` |
| `tests/` | 40+ 条离线单元测试（含「重型轨迹绝不入库」「脚本纯 ASCII」两条硬约束） |

---

## 2. 任务契约（手机 / 任意客户端如何下单）

`results/status/cgmd_task.json` 是唯一握手文件，例：

```json
{
  "schema": "cgmd.task.v1",
  "task_id": "cgmd-20261028-120000-ab12",
  "status": "pending",
  "peptide": { "name": "magainin2", "sequence": "GIGKFLHSAKKFGKAFVGEIMNS", "secondary_structure": "C" },
  "membrane": { "lipids": { "POPE": 3, "POPG": 1 }, "box_xy_nm": 12.0, "salt_M": 0.15, "temperature_K": 310 },
  "simulation": { "production_ns": 1000, "equilibration_ns": 20, "gpu_id": 0, "dt_fs": 20 }
}
```

* 状态机：`idle → pending → claimed → running → completed_on_desktop`（异常分支 `failed_on_desktop` / `cancelled`）；
* 所有时间戳都是**北京时间**（`Asia/Shanghai`，带 `+08:00`）；
* 认领超过 6 小时的 `claimed/running` 任务视为「机器重启导致的孤儿」，允许被重新认领；
* 生成/校验一手命令：

```bash
python3 -m core.task_contract new --sequence GIGKFLHSAKKFGKAFVGEIMNS --name magainin2 \
        --production-ns 1000 --write results/status/cgmd_task.json
python3 -m core.task_contract validate --path results/status/cgmd_task.json
python3 -m core.task_contract show      --path results/status/cgmd_task.json
```

台式机完成后会自动写入 `result.headline`（嵌膜深度 / 脂序参数 / 水孔 / ns/day）并同步到 `results/status/cgmd_result.json`。

---

## 2.5 打通验证：台式机同步 + 自检（18 项，结果进 git）

「台式机接上了没有」不再靠猜：一条命令同步代码（含 Arena Desk）+ 18 项检查，结论写进
`results/status/desktop_selfcheck.json`（schema `cgmd.selfcheck.v1`），随分支同步。

```powershell
# 台式机上一条命令：拉最新 -> 重新部署 Arena Desk -> 18 项自检 -> 报告自动 push
powershell -NoProfile -ExecutionPolicy Bypass -File C:\cgmd\0fuye\skills\cgmd-hub\runner\Sync-Desktop.ps1 -Desk -Notify
```

```bash
# 远程点名（任何客户端都能发起）：台式机 <=60 s 内自动跑一次自检
python3 -m core.selfcheck request --note "换网卡后复测" --write
python3 -m core.selfcheck request --desk --note "顺带部署 desk" --write   # 连 desk 一起
git add results/status/selfcheck_request.json && git commit -m "queue selfcheck" && git push

# 值守活着没？轮询器最多每小时推一次 300 B 心跳到 results/status/hub_heartbeat.json
python3 -m core.selfcheck heartbeat

# 稍后读回结论（桌面上报后这个命令会给出 PASS/WARN/FAIL 与逐项明细）
python3 -m core.selfcheck status
python3 -m core.selfcheck show results/status/desktop_selfcheck.json
```

```powershell
# 或在台式机前直接跑（带表格 + 推送 + 自动 push 报告）
powershell -NoProfile -ExecutionPolicy Bypass -File C:\cgmd\0fuye\skills\cgmd-hub\runner\Test-CgmdHub.ps1 -Push -Notify
```

### 100 ps 实跑（证明 GROMACS 真能积分，而不只是「装着」）

**Windows 原生版 GROMACS（不走 WSL，零依赖，连 Python 都不需要）**：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\cgmd\0fuye\skills\cgmd-hub\runner\Run-Gmx-Native.ps1
```

* 力场用 GROMACS 自带的 `oplsaa.ff` + `spce.itp`，`gmx solvate -cs spc216.gro` 灌 2.5 nm 盒子（约 500 个 SPC 水）；
* EM → `50000 × 0.002 ps = 100 ps` NPT 300 K（PME + LINCS h-bonds + v-rescale + C-rescale）；
* 先 `-nb gpu`，失败自动回退 CPU；报告字段与 Python 通道一致（`cgmd.gmxsmoke.v1`）→ `results/status/gmx_smoke.json`，自动 push；
* **已实测通过**（2026-10-29，`DESKTOP-IEUDGS5`）：GROMACS 2025.1 / mixed / AVX2_256 / CUDA 12.8（驱动 13.2）/ FFTW3，RTX A4000 16 GB（驱动 596.71），`ps_completed = 100`，`accelerator = gpu`，`540–576 ns/day`，端到端 23 s。细节见 `docs/gmx_smoke_native_zh.md`；
* **两条 Windows 坑（脚本已内置兜底，勿删）**：① 这套 2025.1 预编译版 `gmx grompp` 在读自带 `oplsaa.ff` 时会以 `0xC0000005` 崩溃，脚本自动改用「参数全内联的自带 SPC 拓扑」(`smoke_box_inline.top`) 重跑，日志写明原因；② PS 5.1 的 `Start-Process -WorkingDirectory ''` 会静默报错，导致 `gmx --version` / `nvidia-smi` 拿不到输出（版本与显卡字段为空），已改成始终传一个非空目录；
* 自检同步升级：WSL 探测失败但 Windows 有 `gmx.exe` 时，`gromacs`/`gpu` 直接判 pass（`native windows`），不再误报 7 项 fail。

```powershell
# WSL 版（Linux GROMACS）等价入口，加 -Native 即转调上面那条
powershell -NoProfile -ExecutionPolicy Bypass -File C:\cgmd\0fuye\skills\cgmd-hub\runner\Run-Smoke.ps1 -Native
```

```bash
# 让台式机自己在下次轮询时跑（有 gmx.exe 走原生，否则走 WSL 里的 python3 -m cgmd.smoke）
python3 -m core.selfcheck request --smoke --note "验证 gmx 100 ps" --write
python3 -m cgmd.smoke --show results/status/gmx_smoke.json   # 读回版本/软件清单
```

| 退出码 | 含义 |
| --- | --- |
| `0` | 18 项全绿，可接微秒级任务 |
| `6` | 有告警（如 WSL 磁盘 < 20 GB、GROMACS 无 CUDA、分支落后），仍可跑 |
| `7` | 有失败（无 GPU / 缺依赖 / 缺 Martini 3 / 计划任务未注册 / desk 源码不全） |
| `9` | Arena Desk 部署失败（`Sync-Desktop.ps1 -Desk`） |
| `8` | git 工作区脏或同步冲突，先提交或加 `-Force` |
| `5` | origin 不是被锁定的仓库，拒绝运行 |
| `4` | 配置缺失，需要先跑 bootstrap |

检查项：`repo` `origin` `branch` `creds` `wsl` `gpu` `gromacs` `martini3` `python` `tools` `disk` `launcher` `task` `beacon` `desk-src` `desk-app` `desk-http`。
同步记录：`results/status/desktop_sync.json`（`cgmd.desksync.v1`，含 `from_sha`→`to_sha`、desk 版本、自检结论）。
自检不启动模拟、不占 GPU；WSL 侧只跑一次约 2 s 的探测。bootstrap 的最后一步会自动执行它并以报告收尾。

---

## 3. 零 Token 手机推送（ntfy：`arena-beacon-95bc796a66`）

```bash
# 1. 验证手机链路（会立刻弹窗+震动）
python3 code/federation/node_agent.py test

# 2. 跟踪一次生产模拟：开始 / 每 10% 或每 15 min / 完成 / 发散
python3 code/federation/node_agent.py watch \
    --log ~/cgmd-runs/<task_id>/prod.log \
    --task results/status/cgmd_task.json --progress-every 900

# 3. 只跟任务文件（台式机守护会自动拉起这一条）
python3 code/federation/node_agent.py task --task-file results/status/cgmd_task.json

# 4. 无 GROMACS 也能演示整条信标序列
python3 code/federation/node_agent.py demo          # 加 --diverge 演示发散告警
```

推送内容示例（UTF-8 JSON `POST https://ntfy.sh`，`priority: 5`，标题带 emoji tag）：

```
[CGMD] 进度 60%
生产模拟进行中
进度: 60.0% (600.0 / 1000.0 ns)
速度: 980.50 ns/day
剩余: 9 h 47 m
肽: magainin2 (23 aa)
任务: cgmd-20261028-120000-ab12
北京时间 2026-10-28T20:28:24+08:00
```

异常检测：`LINCS WARNING` / `Too many LINCS warnings` / `NaN` / `blowing up` / `Segmentation fault` / `CUDA_ERROR_OUT_OF_MEMORY` → 立即推 `rotating_light` 告警并停止等待（返回码 3）。

Windows 侧同样有 `skills/cgmd-hub/runner/Send-CgmdBeacon.ps1`（同一协议、同一频道、北京时间戳）。

---

## 4. Martini 3 抗菌肽「膜打孔」流水线

```bash
# 0. 环境（WSL2 内）
bash code/cgmd/setup_env.sh --check          # 只看
bash code/cgmd/setup_env.sh --install --yes  # 装 python 侧（vermouth/insane/martini-forcefields/MDAnalysis）

# 1. 肽描述（电荷 / pI / GRAVY / 疏水力矩 / 两亲性）
python3 -m cgmd.cli describe GIGKFLHSAKKFGKAFVGEIMNS

# 2. 干跑（无需 GPU，打印完整命令计划）
python3 -m cgmd.cli plan --sequence GIGKFLHSAKKFGKAFVGEIMNS \
    --workdir ~/cgmd-runs/demo --output results/cgmd/demo

# 3. 真跑：能量最小化 → 20 ns 预平衡 → 微秒级 GPU 生产 → 分析出图
python3 -m cgmd.cli run --task results/status/cgmd_task.json \
    --workdir ~/cgmd-runs/<task_id> --output results/cgmd/<task_id>
```

> 📄 **逐步详解**（12 个阶段 · 参数逐条解释 · 报错排查表 · QC 清单 · 参考文献）：
> 仓库内 [`docs/cgmd_pipeline_steps_zh.md`](docs/cgmd_pipeline_steps_zh.md)；同一份已导出为 Google 文档
> <https://docs.google.com/document/d/130wwAf1ZM4B8ifwf9dujOUJqskNHCn4vC7SM1Hl4aWE/edit>
> （归档位置：Google Drive `02_科研与学术论文 / 20261029_CGMD_Martini3粗粒化MD_详细步骤`）。
> 需要重新导出 docx/PDF：`python3 docs/md2docx.py docs/cgmd_pipeline_steps_zh.md out.docx "标题"`。

流水线要点：

1. **结构**：`--structure-pdb`（AlphaFold/实验结构）> `--predictor "colabfold_batch {fasta} {outdir}"` > 内置 NeRF 建模器（理想伸展链/理想螺旋，重原子 173 个，两两无碰撞）；
2. **martinize2**：`-ff martini3001 -elastic -p backbone -ignh`，自动探测 vermouth 可用力场名；
3. **insane.py**：`-pbc rectangular -x/-y/-z`（盒子按肽尺寸自动扩张，避免周期像重叠）`-l POPE:3 -l POPG:1 -sol W -salt 0.15`；旧版 insane 自动加 `-ff M3`，新版自动省略；
4. **拓扑重建**：`cgmd/topology.py` 递归索引 Martini 3 全部 `[ moleculetype ]`，把 insane 的 `NA+ → NA`、`Protein → Protein_0` 重写，按需 `#include` 力场文件，并把原子数与 `.gro` 交叉校验（对不上直接告警）；
5. **索引**：直接生成 `index.ndx`（`Peptide/Membrane/POPE/POPG/Water/Ions/Headgroups/Tails`），不依赖交互式 `make_ndx`；
6. **GROMACS**：Martini 3 标准参数（`reaction-field, rcoulomb=1.1, epsilon_r=15, Verlet buffer, Potential-shift, v-rescale 1.0, semiisotropic`），生产段 `dt=20 fs`、`Parrinello-Rahman tau-p=12`，`mdrun -nb gpu -pme cpu -bonded gpu -gpu_id N -pin on`；
7. **断点续跑**：`stages.json` 记录每个阶段，`--no-resume` 才重算；`.cpt` 崩溃后自动续。

回传 Git 的只有（`< 1 MB` 合计）：

```
results/cgmd/<task_id>/summary_metrics.json   约 7–40 kB
results/cgmd/<task_id>/figures/*.svg          每张 10–50 kB
```

指标定义：

| 指标 | 定义 |
| --- | --- |
| `membrane_insertion.z_distance_nm` | 肽珠质心 − 磷酸基团中平面（负值 = 偏向下层小叶），并给出逐残基深度曲线 |
| `lipid_order.sn1/sn2` | Martini 尾链相邻键对膜法向的 `S = <P2(cosθ)>`，总体 + 每种脂质 |
| `pore.water_in_core` | 肽横向位置半径 1.2 nm 圆柱、膜芯 ±0.9 nm 内的水珠数；`pore_score` = 该处水密度 / 本体水密度；> 0.25 且占平衡段 > 10% 判定成孔 |
| `membrane.thickness_nm` | 上下层磷酸基团平均间距 |

---

## 5. 验收自测（全离线，约 2 秒）

```bash
PYTHONPATH=.:code/cgmd:code/federation MPLBACKEND=Agg python -m pytest tests -q
```

覆盖：任务契约状态机、北京时间戳、GROMACS 日志解析（含 LINCS/NaN 发散）、肽物化描述与结构建模、
MDP 渲染、拓扑重写、轨迹分析（MDAnalysis 合成轨迹）、干跑全链路握手、**`.xtc/.trr/.tpr/.cpt/.gro` 绝不入库**、
**`.ps1/.vbs/.cs` 纯 ASCII**。

---

## 6. 运维小抄

```powershell
Get-ScheduledTask -TaskName CGMD-Hub-Poll | Get-ScheduledTaskInfo   # 上次/下次运行
Get-Content C:\cgmd\0fuye\skills\cgmd-hub\logs\hub-*.log -Tail 30 -Wait
Get-Content C:\cgmd\0fuye\skills\cgmd-hub\state\hub-state.json      # 心跳（含上次任务摘要）
C:\cgmd\0fuye\skills\cgmd-hub\runner\Invoke-CgmdPoll.ps1 -Force      # 手动触发一次（前台版，便于排错）
C:\cgmd\0fuye\skills\cgmd-hub\runner\Sync-Desktop.ps1 -Desk -Notify      # 同步+部署 desk+18 项自检
C:\cgmd\0fuye\skills\cgmd-hub\runner\Test-CgmdHub.ps1 -Push -Notify    # 只自检并回传报告
C:\cgmd\0fuye\skills\cgmd-hub\runner\Unregister-CgmdHubTask.ps1      # 彻底停止守护
```

* **为什么永远不会闪黑框**：计划任务的动作是 `wscript.exe`（GUI 子系统）→ `CgmdPoll.vbs` → `CGMDHub.exe`（`/target:winexe`）→ `powershell -WindowStyle Hidden`，整条链路没有任何 `conhost` 机会被创建；`Invoke-CgmdPoll.ps1` 内部调用 WSL 也统一走 `Start-Process -NoNewWindow` + 临时 `.cmd` 重定向。
* **令牌消耗为 0**：所有解析、分析、推送都在本机完成，ntfy 是公开 HTTP 服务，无账号无计费。
* **Git 卫生**：`.gitignore` 硬性排除 `.xtc/.trr/.tpr/.cpt/.gro/.edr/.h5/.dcd`，轮询器还有一道兜底 `prune()`，即使误放也删不掉不进去；`results/` 下任何文件超过 1 MB 会被运行时裁剪并由测试断言把关。

---

## 7. 排错速查

| 现象 | 处理 |
| --- | --- |
| 计划任务 0x1、日志空 | 手动跑一次 `Invoke-CgmdPoll.ps1 -Force` 看前台报错 |
| `REFUSING to run: origin is ...` | 该 clone 指向了别的账号，按提示改回 `hukeying85-ux/0fuye` |
| `wslpath: command not found` | WSL 未安装或 distro 名不对，`wsl -l -v` 后传 `-WslDistro` |
| `Martini 3 force field not found` | `pip install martini-forcefields`，或设 `CGMD_MARTINI3_DIR=/path/to/gmx_files` |
| `GPU support: no` | 装 CUDA 版 GROMACS（`-DGMX_GPU=CUDA`）或 `apt install gromacs` 新版 |
| 手机收不到推送 | `python3 code/federation/node_agent.py test`，检查 topic 拼写与手机 ntfy 订阅 |
| 任务卡在 `claimed` | 超过 6 h 会自动重领；急用可 `python3 code/federation/desktop_runner.py reset` |
| 不确定台式机能不能接单 | `python3 -m core.selfcheck status`；没有报告就 `python3 -m core.selfcheck request --write` 再 push |
