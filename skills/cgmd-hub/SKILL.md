---
name: cgmd-hub
description: Operate the DESKTOP-IEUDGS5 CGMD hub through the git mailbox, migrate legacy results and the watcher from C: to the fixed F: layout, and run/verify native Windows GROMACS Martini 3 simulations without asking the user to type desktop commands. Use for CGMD desktop discovery, mailbox jobs, F-drive migration, watcher handover, Martini peptide-membrane runs, checkpoint continuation, trajectory verification, insertion-depth analysis, staging cleanup, and hub troubleshooting.
---

# CGMD Hub：F 盘迁移与 Martini 3 原生 GPU 运行

本 skill 是可执行操作规范，不是状态猜测。所有台式机动作都必须走
`refs/heads/hub/mailbox` 信箱或已存在的基座自动化；不得要求用户在台式机
粘贴命令。代码修改默认只提交、推送当前 Arena 会话分支，默认不创建或合并 PR。

## 0. 先分清三种状态

汇报时必须逐项使用下表措辞，不能把三者混为一谈：

| 标签 | 证据门槛 |
|---|---|
| **代码已提交** | 文件在本仓库当前会话分支中，且有 commit SHA |
| **已部署** | DESKTOP-IEUDGS5 实际克隆的 tree/commit 中包含该文件，并有桌面回执或该克隆分支 tree 证据 |
| **已加载并实测** | 目标 kind 的真实 mailbox 回执成功，且回执 detail 能证明实际脚本、工作目录和输出路径 |

仓库里存在 `pipeline`、`files` 或 `SKILL.md`，只证明“代码已提交”，不证明
台式机已加载。必须先读桌面固定分支的实际 tree，再发对应 kind 取得回执。

### 2026-10-30 实测快照（后续会话必须重新核验）

| 项目 | 实际回执 |
|---|---|
| 台式机 | `DESKTOP-IEUDGS5`，Windows 10，用户 `BNI` |
| ping 工单 | `20261030T071030-88d7`，15:10:55+08:00，`ok` |
| 原生 GROMACS | 工单 `20261030T071636-eb87`，`F:\gromacs-2025.1-SM86\gromacs-2025.1-SM86\bin\gmx.exe`，2025.1，GPU support CUDA |
| GPU | NVIDIA RTX A4000，16376 MiB，ping detail 驱动字段 `596.71` |
| 当前桌面克隆 | `C:\cgmd\0fuye`，分支 `arena/32cd826e-0fuye`；mailbox worktree 为 `C:\cgmd\0fuye\skills\cgmd-hub\state\mailbox` |
| 当前已加载 worker | 只有 `ping/selfcheck/sync/smoke/gmx/deskdiag/deskfix/shell`；`allow_shell=false`，`MaxJobSeconds=3600`，Poll 包裹层 2700 秒；没有 `pipeline`、没有 `files`，deskfix 不能改 branch |
| files 活探针 | 工单 `20261030T074626-9153`，15:46:56+08:00，`unsupported: unknown kind: files`；这是“新版 files 尚未部署/加载”的直接回执 |
| pipeline 活探针 | 工单 `20261030T074736-15f9`，15:47:55+08:00，`unsupported: the Martini pipeline job kind is not wired yet`；未执行任何模拟 |
| F 目标目录 | 工单 `20261030T071719-b39b` 的 `gmx solvate -o F:\cgmd\runs\probe-dir-check.gro` 返回 File input/output error，证明 `F:\cgmd\runs` 当时不存在 |
| 自检 | 工单 `20261030T071928-c462`：18 项为 15 pass / 3 warn / 0 fail；缺 Martini3、vermouth、insane、MDAnalysis、matplotlib；“855.6 GB free”是 WSL home，不是 F 盘实测空间 |

因此，在桌面固定分支尚未包含本 skill 对应 worker 代码前：**不能远程创建
F 目录、复制 C→F、克隆 F 基座、重新注册值守，也不能启动任何会把运行数据
写到 C 盘的生产任务。** 这不是可通过多发几个 `gmx` 工单绕过的问题。

## 1. 硬边界

1. 代码只进入当前 Arena 会话分支；信箱派单只写
   `refs/heads/hub/mailbox`。不切换、创建或推送其他工作分支。默认不建 PR；
   只有用户明确要求合入 `main` 时才走 PR。
2. CGMD 仓库、值守状态、暂存、运行数据和结果不得继续写入 C 盘。Windows
   系统自身文件不在此列。若 F 路径未经回执证明存在，停止运行，不用 C 路径
   临时顶替。
3. `.tpr/.xtc/.gro/.edr/.cpt/.top/.itp` 等重数据只留台式机 F 盘，绝不进 Git。
   迁移只复制，保留 C 盘原件，不擅自删除。目标冲突先保留并报告。
4. 不把阶段成功、25,000 步基准、`gmx check -s1` 成功或旧文件存在说成
   100 ns 完成。完成门槛见第 9 节。
5. 不把膜插入深度当作成孔证据。0.15 M 只能标为建系目标/近似值，必须报告
   实际 Na/Cl 数和总电荷中性核验。

## 2. 固定路径与配置

| 用途 | 固定路径 |
|---|---|
| F 基座仓库 | `F:\cgmd\0fuye` |
| 重运行数据 | `F:\cgmd\runs\<任务ID>` |
| 小型结果 | `F:\cgmd\results\<任务ID>` |
| F 值守状态 | `F:\cgmd\0fuye\skills\cgmd-hub\state` |
| F mailbox worktree | `F:\cgmd\0fuye\skills\cgmd-hub\state\mailbox` |
| F 本地配置 | `F:\cgmd\0fuye\skills\cgmd-hub\config\cgmd_hub.local.json` |
| C 旧结果源 | `C:\cgmd\0fuye\skills\cgmd-hub\state\cgmd_100ns*` |
| 原生 gmx | `F:\gromacs-2025.1-SM86\gromacs-2025.1-SM86\bin\gmx.exe` |

配置模板在 `skills/cgmd-hub/config/cgmd_hub.json`，桌面真实配置是
gitignored 的 `cgmd_hub.local.json`。关键键：`repo_path`、`branch`、
`run_root`、`result_root`、`f_repo_path`、`migration_source_dir`、
`legacy_task_name`、`f_task_name`、`mailbox_ref=hub/mailbox`、
`allow_shell=false`。模板已更新不等于桌面本地配置已更新。

## 3. 发现基座：每次先做

在沙箱仓库根目录运行：

```bash
python3 -m core.hub_mailbox caps
python3 -m core.selfcheck heartbeat
python3 -m core.hub_mailbox run --kind ping --timeout 300
```

再核对桌面实际固定分支，禁止用当前会话分支文件代替：

```bash
git fetch origin <桌面分支>:refs/remotes/origin/<桌面分支>
git show refs/remotes/origin/<桌面分支>:results/status/hub_heartbeat.json
git show refs/remotes/origin/<桌面分支>:results/status/hub_mailbox.json
git show refs/remotes/origin/<桌面分支>:skills/cgmd-hub/runner/Invoke-CgmdMailbox.ps1 \
  | grep -E 'function Invoke-Job|MaxJobSeconds|Invoke-CgmdPipeline|branchValue'
git ls-tree -r --name-only refs/remotes/origin/<桌面分支> \
  skills/cgmd-hub/runner | grep -E 'Pipeline|Files' || true
```

判读：

- `ping ok` 只证明值守和原生 gmx 在线；
- `pipeline/files` 必须再用真实回执验证。若返回 `unknown kind` 或 runner
  missing，则是“未部署/未加载”；
- Poll 每轮对桌面克隆执行 `checkout --force + reset --hard origin/<cfg.branch>`，
  子 worker 在 reset 后按路径加载，所以新代码通常要经过一个后续轮询周期；
- 旧 worker 的 deskfix 只能写 `peer_repos`，不能切 branch，也不能改
  `repo_path`。不要把当前分支代码表述为可由旧 worker 自动加载。

辅助脚本入口：

```bash
python3 skills/cgmd-hub/scripts/f_hub.py caps
python3 skills/cgmd-hub/scripts/f_hub.py files --action survey --dry-run
python3 skills/cgmd-hub/scripts/f_hub.py pipeline \
  --task-id <任务ID> --dry-run
```

## 4. mailbox kind 与安全修复

优先使用专用 kind，不启用任意 shell：

| kind | 用途 | 关键限制 |
|---|---|---|
| `ping` | 主机、原生 gmx、GPU、LAN/bridge 提示 | 不证明 pipeline 已加载 |
| `selfcheck` | 18 项基线 | disk 字段可能是 WSL home，不能当 F 空间 |
| `files` | F 盘调查、SHA-256 迁移、F 克隆部署、两阶段值守切换/回滚 | 仅固定路径；变更动作需要确认串 |
| `pipeline` | 原生 Python + `gmx.exe` 全链 | workdir/outdir 必须在 F roots 下 |
| `gmx` | 白名单 GROMACS 子命令 | 新版支持 `args.stdin_text` 与 F 盘 `args.workdir` |
| `deskdiag/deskfix` | Arena Desk 诊断/修复 | 不是文件迁移或通用配置接口 |
| `shell` | 任意命令 | 默认关闭；本 skill 不依赖它 |

`gmx energy` 等交互工具不得靠等待超时“碰运气”。新版 worker 的安全修复是：
handler 将 `args.stdin_text` 写成 ASCII 临时 stdin 文件，并在 cmd 中以
`< file` 喂给 gmx；这已做仓库侧静态/结构测试，但在桌面加载新版 worker 前
仍只能标为“代码已提交，未部署、未实测”。

## 5. F 盘迁移运行手册

所有变更命令都先 `survey`，逐个工单核验，不并行改状态。

### 5.1 调查（只读）

```bash
python3 -m core.hub_mailbox run --kind files \
  --json-args '{"action":"survey","task_id":"legacy-cgmd-100ns-20261030","source_prefix":"cgmd_100ns","timeout_s":1800}' \
  --timeout 1800
```

必须从回执逐项记录：

- C/F `DriveInfo` 总量与可用空间；
- `C:\cgmd\0fuye`、当前 branch、script/state/log/worktree 实际路径；
- `cgmd_100ns*` 每个源文件的完整源路径、目标路径、bytes、SHA-256；
- F 目标已存在文件的 bytes/SHA-256 与冲突数；
- 源文件总 bytes、预计 F 占用，以及旧/新计划任务 action/state。

`survey` 不创建目录。若返回 `unsupported/unknown kind`，停在门外并报告未部署。

### 5.2 复制历史结果（保留 C 原件）

确认串由本地 helper 的 `--confirm-mutation` 显式加入：

```bash
python3 skills/cgmd-hub/scripts/f_hub.py files \
  --action migrate \
  --task-id legacy-cgmd-100ns-20261030 \
  --source-prefix cgmd_100ns \
  --confirm-mutation --timeout 5400
```

桌面脚本规则：

1. 先盘点全部目标冲突；任一同名目标 hash 不同则整批在复制前中止；
2. 要求 F 可用空间至少为源总量 + max(1 GB, 5%)；
3. 每文件先复制为同目录 `.partial-<stamp>`，核对 size + SHA-256 后才
   移为最终名，再对最终文件复算 SHA-256；
4. 已存在且 hash 相同记为 `already_verified`；
5. 回执与 F 结果目录的 `migration-receipt-<stamp>.json` 必须逐文件列出
   source、target、bytes、source/target SHA-256 和状态；
6. 不删除 C 原件。校验失败不得宣称迁移完成；保留 partial 证据并报告。

### 5.3 部署 F 基座

```bash
python3 skills/cgmd-hub/scripts/f_hub.py files \
  --action deploy \
  --task-id legacy-cgmd-100ns-20261030 \
  --branch <桌面应加载的分支> \
  --copy-credentials --confirm-mutation --timeout 1800
```

`deploy` 只允许目标 `F:\cgmd\0fuye` 和锁定仓库
`hukeying85-ux/0fuye`。已有克隆必须 origin 正确且工作区干净；脏工作区或
非 git 目录直接 `conflict`，不 reset、不覆盖。它写入目标本地配置，固定
`run_root/result_root`，并把计划任务名设为独立的 `CGMD-Hub-Poll-F`。
凭据文件只在本机旧 state → 新 state 间复制，内容不进日志和回执；未明确
传 `--copy-credentials` 时必须把 push 凭据标为未核验。

### 5.4 两阶段值守切换与回滚

```bash
# 阶段 1：备份计划任务 XML，构建静默启动器，注册 F 任务但保持 Disabled
python3 skills/cgmd-hub/scripts/f_hub.py files \
  --action handover_stage --branch <分支> --confirm-mutation

# 阶段 2：禁用旧任务并启用 F 任务；不停止正在运行的旧 poll
python3 skills/cgmd-hub/scripts/f_hub.py files \
  --action handover_enable --branch <分支> --confirm-mutation

# 等至少两个轮询周期后，用新 worker 自证
python3 skills/cgmd-hub/scripts/f_hub.py files --action status
python3 -m core.hub_mailbox run --kind ping --timeout 300
```

完成判据不是 `handover_enable ok` 一项，而是后续 `files status` 回执同时
满足：`script`、`state_dir`、`log_dir`、mailbox worktree 和后续输出路径均在
`F:\cgmd\0fuye`/`F:\cgmd\...` 下。回滚命令：

```bash
python3 skills/cgmd-hub/scripts/f_hub.py files \
  --action handover_rollback --confirm-mutation
```

回滚只禁用 F 任务、重新启用旧 `CGMD-Hub-Poll`，不删除 F 克隆、数据或备份。

## 6. Martini 3 建系契约

优先使用已实测加载的 native `pipeline`。其桌面链为：
序列 → 全原子结构 → martinize2 → insane → 同目录平铺拓扑 → index →
EM → POSRES 平衡 → 生产 → 分析。

- Martini 3 参数不在 PyPI。需要时浅克隆
  `marrink-lab/martini-forcefields`，定位
  `martini_forcefields/regular/v3.0.0/gmx_files` 或
  `regular/v3.0.0/gmx_files`；仓库的 `fetch_martini_forcefields` 已封装。
- martinize2 只用 vermouth 内置 `martini3001`，禁止传外部
  `-ff-dir/-map-dir`；二级结构按残基数逐个展开；在 workdir 内运行，
  使 `<molecule>.itp` 落在正确目录。
- `topol.top` 只能 include 与它同目录的平铺 `.itp`，避免跨目录相对 include
  和已知的 Windows grompp 崩溃。
- insane 后用仓库 `salt.ensure_salt_pairs` 补加盐对；报告实际 `W/NA/CL`
  数、肽净电荷、POPG 负电荷和总电荷。0.15 M 是按名义水体积的建系近似，
  不是轨迹实测浓度。
- MDP 必须是 Martini 3 reaction-field；禁止给动力学传 `-pme`。
- 动力学固定 `-nb gpu -bonded gpu -gpu_id 0`。只要传 `-ntomp`，同时传
  `-ntmpi 1`。
- GROMACS `steep` 不支持 GPU bonded；EM 使用 CPU bonded（如
  `-nb cpu -ntomp N`），回执中如实记录 EM 非键/键合设备、Fmax、势能和警告。
- 预处理失败、EM/平衡发散、checkpoint 不可验证时立即停止，不启动或宣称
  生产成功。

Magainin-2 复现参数固定为：`GIGKFLHSAKKFGKAFVGEIMNS`，
`POPE:POPG=3:1`，310 K，目标 0.15 M NaCl，10 ns 平衡，100 ns 生产。
`dt=0.02 ps` 时对应平衡 500,000 步、生产 5,000,000 步。

```bash
python3 skills/cgmd-hub/scripts/f_hub.py pipeline \
  --task-id magainin2-100ns-<YYYYMMDD> \
  --attempts 6 \
  --artifact-dir results/cgmd/magainin2-100ns-<YYYYMMDD>
```

该命令生成的 payload 已固定 `F:\cgmd\runs\<任务ID>` 和
`F:\cgmd\results\<任务ID>`。只有 `files status` 证明 F 值守已加载后才可去掉
`--dry-run` 真正发送。

## 7. 超时与 checkpoint 分段

不要背固定数字；先从桌面实际 tree 读出三层上限。2026-10-30 旧 worker 为
Poll 2700 秒硬杀整棵进程、worker 3600 秒、gmx 默认参数 900 秒。仓库新版为
Poll 5700 秒、worker 5400 秒，但新版未在该桌面加载。

- 每次 mdrun 的 `-maxh` 必须小于“最短硬超时 − 启动/发布余量”。旧 worker
  建议 `-maxh 0.6`，并显式设置较大的 args/request timeout；
- 同一任务 ID、同一 workdir、同一 deffnm 重发；续跑显式 `-cpi <prefix>.cpt`；
- 每段后运行 `gmx check -f <F prefix>.xtc`，核对帧数/最后时间和日志完成步；
- job 超时只能证明可能有 checkpoint 进度，不能证明目标 ns 完成；
- 若日志出现 LINCS、blowing up、温度/压力爆炸或 checkpoint 时间倒退，停止
  并报告，不盲目续跑。

## 8. 备用 gmx 链（仅已存在 F 输入时）

若 native pipeline 未加载，但已核验的建系文件已经位于 F 任务目录，可由
sandbox 计算 MDP/index 参数并用 mailbox `gmx` 分段驱动。不得为了省事把
`.gro/.top` 写进 Git 或 C state；若没有安全的文件到达 F 的通道，停止。

所有 deffnm 前缀都写成 `F:\cgmd\runs\<任务ID>\<stage>`。在已加载支持
`workdir/stdin_text` 的 worker 上，用 helper 保证 workdir：

```bash
# EM grompp 与 CPU-bonded 最小化
python3 skills/cgmd-hub/scripts/f_hub.py gmx --task-id <任务ID> --timeout 1800 -- \
  grompp -f F:\cgmd\runs\<任务ID>\em.mdp \
         -c F:\cgmd\runs\<任务ID>\system.gro \
         -p F:\cgmd\runs\<任务ID>\topol.top \
         -n F:\cgmd\runs\<任务ID>\index.ndx \
         -o F:\cgmd\runs\<任务ID>\em.tpr -maxwarn 2
python3 skills/cgmd-hub/scripts/f_hub.py gmx --task-id <任务ID> --timeout 2400 -- \
  mdrun -deffnm F:\cgmd\runs\<任务ID>\em -nb cpu -ntomp 12
```

动力学每段示例：

```bash
gmx mdrun -deffnm F:\cgmd\runs\<任务ID>\prod \
  -nb gpu -bonded gpu -gpu_id 0 -ntmpi 1 -ntomp 12 \
  -maxh 0.6 -cpi F:\cgmd\runs\<任务ID>\prod.cpt
```

首段没有 checkpoint 时不要伪造 `-cpi`。平衡使用 POSRES MDP，并以 EM
坐标作为 `-r` 参考；生产以平衡 checkpoint 作为 grompp `-t` 输入。

## 9. 回执核验、分析与“100 ns 完成”门槛

生产完成必须同时具备：

1. mailbox `pipeline` 回执 `status=ok`、`completed=true`、`diverged!=true`；
2. `completed_ns >= 100` 且 `steps_completed >= 5,000,000`（dt=0.02 ps）；
3. `gmx check -f F:\cgmd\runs\<任务ID>\prod.xtc` 的最后时间达到 100,000 ps；
4. 生产日志有正常结束与 Performance，记录实际 ns/day；
5. EM Fmax、平衡完成、LINCS/警告和离子中性核验可追溯。

非交互分析优先顺序：

- `distance`：使用 `-select` 或自编 index，输出
  `F:\cgmd\runs\<任务ID>\distance*.xvg`；
- `gyrate`：使用选择语法或已修复的 `stdin_text`，禁止无 stdin 空等到超时；
- `energy`：先用 `gmx dump -e ...` 读取平均能作证据；需要 XVG 时，
  先从真实能量项列表确定编号，再经 `stdin_text` 传编号与 `0`，不得猜编号；
- `check/dump`：核对帧数、最后时间、原子数、步数与盒子。

插入深度要写明采样窗口。原生 pipeline 的 MDAnalysis 指标是肽珠质心相对
磷酸中面的 PBC 距离。备用 XVG 路线可把肽/磷酸坐标与 box 写到 F 任务目录，
回收小型 XVG 后在当前会话计算：

```bash
python3 skills/cgmd-hub/scripts/f_hub.py insertion-depth \
  peptide.xvg phosphate.xvg box.xvg --start-ps 80000 --end-ps 100000
```

该实现以肽首珠为参考做 minimum-image 解包，以磷酸 z 的圆均值定双层中面；
`insertion_depth = 磷酸半厚度 − |肽质心 − 中面|`。正值只表示质心位于两层
平均磷酸面之间，不是成孔证据。

## 10. 结果、暂存清理与交付

- 权威小型结果只放 `F:\cgmd\results\<任务ID>`；`summary_metrics.json` 与
  SVG 总量应小于 1 MB。pipeline 回执会嵌入 summary 与每个不超过 256 KB
  的 SVG，helper 的 `--artifact-dir` 只生成当前会话副本。
- 若曾用 mailbox 暂存少量文本，必须记录精确路径，任务后运行：

```bash
python3 skills/cgmd-hub/scripts/f_hub.py cleanup-staging <精确路径...>
```

再 fresh fetch 核验路径消失；但 Git 历史中曾提交过的文本可能仍可追溯，
交付时要明说。helper 主动拒绝 `.gro`、二进制和超过 1 MB 的暂存。
- 交付必须包含工单号、F 完整路径、迁移逐文件校验、完成步数/时间、
  GPU 速度、分析窗口与方法、清理回执；未实测项逐项标注。

## 11. 常见故障

| 症状 | 结论与处理 |
|---|---|
| `unknown kind: pipeline/files` | 桌面加载的是旧 worker；标为未部署，停止 F 运行 |
| `shell jobs are disabled` | 这是安全设计，不要试图用 gmx 参数注入 shell |
| `F:\cgmd\runs\... File input/output error` | 目标目录不存在；GROMACS 不会 mkdir，先完成 files 迁移链 |
| `gmx check -s` exit 1，但 `-s1` exit 0 | 先查 GROMACS 2025.1 参数语义，不单凭一个错误选项判文件无效；也不能因此宣称模拟完成 |
| Windows grompp `0xC0000005` | 优先同目录平铺/内联拓扑并保留 stderr；不要继续用崩溃产物 |
| martinize2 mapping/file missing | 删去外部 `-ff-dir/-map-dir`，回到内置 martini3001 并在 workdir 运行 |
| job timeout | 查 checkpoint 与 `gmx check` 实际时间后同 ID 续跑；不把 timeout 当完成 |
| energy/gyrate 停在提示符 | 当前 worker 无 stdin；使用 `-select` 或等新版 stdin 修复部署后再实测 |
| selfcheck status=fail 但 0 fail | 可能是 exit 6=warn 映射；逐项读 checks，不只看 wrapper status |
| 目标文件已存在且 hash 不同 | `conflict` 后停止，保留双方并汇报，不覆盖 |
| handover 后无回执 | 不再连续派单；报告最后备份路径与两任务状态，按 rollback 设计处理 |

## 12. 仓库内对应实现

- 客户端：`core/hub_mailbox.py`、`skills/cgmd-hub/scripts/f_hub.py`
- 桌面 worker：`skills/cgmd-hub/runner/Invoke-CgmdMailbox.ps1`
- F 文件引擎：`skills/cgmd-hub/runner/Invoke-CgmdFiles.ps1`
- 原生 pipeline：`skills/cgmd-hub/runner/Invoke-CgmdPipeline.ps1`
- 科学管线：`code/cgmd/cgmd/{pipeline,engine,topology,salt,analyze}.py`
- 回归测试：`tests/test_f_drive_skill.py`、`tests/test_ps_syntax.py`、
  `tests/test_desktop_pipeline_kind.py`
