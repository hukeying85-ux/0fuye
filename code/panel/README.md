# Arena Desk Desktop Edition v2.0

面向本机固定基座 (`git-sync-hub`) 的**原生 Windows 桌面应用**（编译型 `ArenaDesk.exe` + 系统托盘 + 专属定制多分辨率图标 `ArenaDesk.ico`），已从公开仓 `leanrea` 完整迁移至私人仓库 **`mqgg5630-cyber/0fuye`**（分支 `arena/89735ee7-0fuye`）。

## 核心设计原则

- **原生集成 DSH 视觉与陪伴插件能力，零 DeepSeek 依赖**：
  - 将 `dsh-video-skin`（MP4/WebM 循环动态背景、HTTP 206 流式加载、可点击跳过的开机动画、界面毛玻璃不透明度实时滑杆）、`dsh-wallpaper-engine`（Steam Wallpaper Engine `431960` 壁纸库扫描与液态玻璃预设）、`DeepSeek-Balance-Whale-Widget`（Q 弹按压、四边磁吸、贴左自动镜像翻转、错峰时钟与本机遥测轮播气泡的小鲸鱼挂件）全部原生内建于 Arena Desk，**不启动 `@deepseek-ai/dsh`，不消耗任何模型 Token**。
  - 独立桌面宠物 `dsh-pet-indesktop` v4.4.0（无聊天纯本地 WebM 版）保留于 `E:\0apps\DSHPet`，支持面板一键显隐与 `Ctrl+Alt+H`。
- **原生桌面应用体验（规避 Win11 Build 26200 Qt6 DLL 故障）**：
  - `ArenaDesk.cs` 通过 Windows 内置 `.NET Framework 4.x` `csc.exe` 零依赖编译为原生 `E:\0apps\ArenaDesk\ArenaDesk.exe`（内嵌 16/24/32/48/64/128/256 px 真彩 `ArenaDesk.ico` 图标、单实例互斥锁、系统托盘常驻菜单、Edge/Chrome `--app` 独立无地址栏原生窗口）。
- **固定值守基座只读保护 + 私人仓库热桥接**：
  - `git-sync-hub` 在后端硬编码受保护，任何 API 均无法停止或卸载。
  - `enable_private_hub.ps1` 利用基座预留的 `hub-worker.ps1` 热扩展点，将仓库发现接口从公开仓 `/users/.../repos` 无缝升级为认证接口 `/user/repos?affiliation=owner`，无需重启计划任务即可自动轮询 `0fuye` 等全部私人仓库。
- **七大功能模块一屏统管**：
  1. **运行总览**：基座心跳、结果集统计、私人仓一键热接入命令、快捷动作磁贴。
  2. **软件与安装（含 PyMOL）**：13 款科研与开发软件本机路径/版本扫描 + 一键静默安装（预置免商业授权完整版 `conda-forge::pymol-open-source`）+ 自定义包白名单新增安装。
  3. **远程控制中心**：校园超算 HPC `mu01`（经 WSL2 OpenSSH 跳板）、本机 WSL2 `Ubuntu-26.04`、实验室台式机 `desktop-ieudgs5`（Tailscale/SSH/RDP）及自定义节点连通探测与命令回显。
  4. **GitHub (`gh`) 认证管理**：检测 `gh` CLI、`repo` 私人仓作用域、GCM/DPAPI 免弹窗凭据与设备码登录引导。
  5. **多机一键诊断安装脚本**：面向 Windows (`.ps1` / `.bat`) 与 Linux/WSL/HPC/macOS (`.sh`) 动态生成定制体检与 PyMOL/工具链一键部署脚本。
  6. **Arena.ai 生态连接器**：真实核验并呈现 GitHub、Google Drive、Google Docs、Notion、Gmail、Linear、Google Calendar 七大生态连接状态、能力清单与协作指令模板。
  7. **外观 · 桌宠 · 台账**：5 套液态玻璃主题、自定义视频壁纸、小鲸鱼挂件工坊、Windows 计划任务管理与会话提示词安全台账。

## 本地验证

```bash
python3 code/panel/test_panel.py -v
bash code/check_all.sh
```
