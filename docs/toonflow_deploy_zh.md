# AI 漫剧项目部署 —— 项目选型与执行单

生成时间：2026-10-30（Arena 会话）
目标机器：`DESKTOP-IEUDGS5`（Windows 10、RTX A4000 16 GB、48 核）
仓库分支：`arena/5308c7fc-0fuye`，提交 `8b8e047`

---

## 1. 连通性结论

台式机已打通，三条活回执为证（均为桌面本地时间 +08:00）：

| 工单 | 类型 | 结果 |
|---|---|---|
| `20261127T014735-e700` | ping | ok，1 秒，`DESKTOP-IEUDGS5 alive` |
| selfcheck | selfcheck | 15 pass / 3 warn / 0 fail |
| gmx `--version` | gmx | ok，exit 0 |

“打通”的准确含义：**我能通过 git 信箱派单并读回执**，不是双向任意文件通道。
当前桌面端加载的是旧 worker（分支 `arena/32cd826e-0fuye`），能力边界如下：

| 能力 | 状态 |
|---|---|
| ping / selfcheck / deskdiag / gmx / smoke / sync / deskfix | 可用 |
| `shell`（任意命令） | **禁用**（`allow_shell=false`），实测返回 `unsupported` |
| `files`（F 盘迁移） | **未加载**，返回 `unsupported: unknown kind: files` |
| `pipeline`（Martini 全链） | **未加载**，返回 `unsupported` |

结论：**没有任何通道能在桌面机上执行 `git clone` / `bun install` / 起服务**。
这不是故障，是安全设计（远程代码执行被默认关掉）。因此需要你运行一次脚本，
之后所有步骤全自动。

---

## 2. 项目选型

用 GitHub API 实测星数（2026-10-30，非记忆值）：

| 仓库 | 星 | 语言 | 许可 | 最近推送 | 适配 A4000 16 GB |
|---|---:|---|---|---|---|
| **HBAI-Ltd/Toonflow-app** | **22,941** | TypeScript | MIT | 2026-11-20 | 好 |
| chatfire-AI/huobao-drama | 18,030 | TypeScript | NOASSERTION | 2026-11-21 | 许可不明，排除 |
| Forget-C/Jellyfish | 7,351 | Python | Apache-2.0 | 2026-11-25 | 可作备选 |
| LingyiChen-AI/AIComicBuilder | 1,987 | TypeScript | Apache-2.0 | 2026-04-27 | 半年未更新，排除 |

**选 Toonflow**：星数最高、MIT 许可最干净、仍在活跃更新、内置 FFmpeg、
Windows 原生可跑（Bun + Vue，服务端 `bun build/server/index.js`，端口 3000）。

### 必须说清的一件事

**Toonflow 本身不含生成式视频模型。** 它是创作工作台：剧本、分镜、无限画布、
3D 白模预演、素材管理、剪辑合成。真正的 AI 画面需要二选一：

1. **接模型 API**：Seedance / Seedream / MiniMax / Wan，要在网页里填 API Key（付费）；
2. **接本地 ComfyUI**：用 A4000 16 GB 跑本地模型。

所以本次能给你的“测试视频”是**渲染管线验证片**（证明应用、服务、编码链全通），
**不是 AI 生成的漫剧**。AI 成片要等你提供 API Key 或让我再部署 ComfyUI。
把验证片说成 AI 作品是造假，这里明确区分。

---

## 3. 执行单（你只需运行一次）

在台式机上打开 **PowerShell**（普通权限即可），粘贴下面整段：

```powershell
$ErrorActionPreference='Stop'
$dir='F:\apps\_bootstrap'; New-Item -ItemType Directory -Force -Path $dir | Out-Null
git clone --depth 1 --filter=blob:none --sparse -b arena/5308c7fc-0fuye https://github.com/hukeying85-ux/0fuye.git "$dir\hub"
git -C "$dir\hub" sparse-checkout set skills/cgmd-hub/scripts
powershell -NoProfile -ExecutionPolicy Bypass -File "$dir\hub\skills\cgmd-hub\scripts\deploy_toonflow.ps1" -GitHubToken (Read-Host 'GitHub token (可留空，留空则回执只留在F盘)')
```

脚本会自行完成：装 Bun → clone Toonflow 到 `F:\apps\Toonflow\repo` →
`bun install` → `bun run build:server` → 起 3000 端口 → HTTP 就绪探测 →
生成测试视频 → 写回执 → 推回信使分支。

预计耗时：15–40 分钟（取决于网速，`bun install` 要拉几百个包）。

---

## 4. 部署产物路径（全部在 F 盘）

```
F:\apps\Toonflow\
├── repo\                    Toonflow 源码与构建产物
├── data\                    TOONFLOW_DATA_DIR，作品工作区
│   └── workspaces\myProject
├── tools\                   bun.exe、凭据文件
├── logs\server-*.log        服务端日志
└── receipt\
    ├── deploy-receipt.json  机器可读回执
    ├── toonflow-sample.mp4  测试视频
    └── frames\*.png         测试视频的源帧
```

访问方式：在台式机上开 `http://127.0.0.1:3000/`。

---

## 5. 脚本的诚实性保证

这些不是口号，是写进代码并由测试锁定的行为：

- **失败必返回 1**：早期写法 `exit (Write-Receipt ...)` 会把 JSON 转成 0，
  失败也返回成功码，已全部改为显式 `exit 1`（11 条失败路径逐条对应）。
- **端口被占不冒充成功**：3000 若被别的程序占用，脚本会验证页面是否真是
  Toonflow，不是就中止并报错，绝不把别人的服务当成自己的成果。
- **出不了视频就降级报告**：没有 ffmpeg 时状态写 `ready_no_sample`，
  不会假装生成了 mp4。
- **磁盘不足先拒绝**：剩余不足 8 GB 直接退出，不写半个 `node_modules`。
- **不写 C 盘**：脚本内无任何 C 盘写入路径（测试会检查）。
- **回执写清模型限制**：`model_note` 字段明确记录“不含生成式模型”。

---

## 6. 验证记录

- `tests/` 全量：**263 passed, 3 skipped**
- 部署脚本专项：**20 passed**（`tests/test_toonflow_deploy_script.py`）
- PowerShell 括号平衡、纯 ASCII、无 `$args` 误用、失败码正确：均通过仓库既有守卫
- 静态语法树（tree-sitter powershell）：`has_error = False`
- 脚本 SHA-256：`d0c633a1b48ae3dd19226ac5335fb34b1e58e8569672e0ef214ae827e7fc55c2`

**未验证项（如实标注）**：脚本未在真实 Windows 上执行过——沙箱无 PowerShell、
且桌面端 `shell` 通道关闭。所有验证都是静态的与契约级的。真实的
`bun install` 网络行为、Bun 1.4.3 在 Windows 10 的兼容性、Toonflow 构建是否
一次通过，都要等这次运行才能确认。脚本已按可失败、可重跑设计：失败会留下
带步骤名的回执，重跑会复用已有 clone 与已启动的服务。
