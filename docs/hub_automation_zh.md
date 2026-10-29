# 解放双手：自愈值守 · 万能信箱 · 局域网直连

> 目标：**你不用再敲任何命令**。台式机自己发现问题、自己修、自己跑、自己回报；
> 任何会话、任何分支、任何机器都能直接把活派给它；同一个局域网里笔记本还能秒级直连。

---

## 1. 它自己会做什么（不需要你介入）

| 场景 | 以前 | 现在 |
| --- | --- | --- |
| 上一轮轮询被 `wsl.exe` 卡死、锁文件残留 | 值守静默数小时，要人上去删 `poll.lock` | 每轮检查 `state/poll.pid`：进程已死 → 立刻破锁；活着但锁龄超 90 min → `taskkill` 后破锁并继续 |
| 100 ps 没跑过 / 上次失败 / 结果超过 24 h | 要人手动排请求 | `smoke_auto`：自动排一次 100 ps，失败退避 180 min 再试，成功则 24 h 后再验 |
| 代码有更新 | 要人提醒 `git pull` | 每轮 `fetch` + `reset --hard origin/<branch>`（脏工作区先发布结果） |
| 手机不知道结果 | 要人查 | ntfy 推送 + `results/status/gmx_smoke.json` 进 git |
| 别的会话想用这台 GPU | 要人转述、要改分支 | 信箱总线，见第 2 节 |

自愈状态都在 `state/`（不进 git），对外可见的只有 `results/status/*.json`
（`gmx_smoke.json`、`hub_heartbeat.json`、`hub_mailbox.json`、`desktop_selfcheck.json`）。

可调参数（`skills/cgmd-hub/config/cgmd_hub.local.json`）：

```json
"stale_lock_minutes": 90,
"smoke_auto": true,
"smoke_interval_hours": 24,
"smoke_retry_minutes": 180,
"mailbox_enabled": true,
"mailbox_jobs_per_poll": 1,
"mailbox_ref": "hub/mailbox"
```

---

## 2. 信箱总线：任何会话 → 台式机 → 结果（走 git，不用登录）

请求和回执放在**独立分支** `hub/mailbox` 上，所以：

* 调用方永远不会提交到自己的工作分支 → **再也不会出现 rebase 冲突**（上一轮反复卡的就是这个）；
* 任何会话 / 任何分支 / 任何机器都能用（沙箱、笔记本、手机都行）；
* 台式机每轮（60 s）取 1 个任务，跑完把结果写回同一个 ref。

```
hub/mailbox
├── inbox/<id>.json     请求  cgmd.mailbox.request.v1
└── outbox/<id>.json    结果  cgmd.mailbox.result.v1
```

### 用法

```bash
# 1) 问一声（10 秒内回，验证链路）
python3 -m core.hub_mailbox run --kind ping --timeout 300

# 2) 让台式机跑 100 ps（GPU），阻塞直到拿到结果
python3 -m core.hub_mailbox run --kind smoke --timeout 1800

# 3) 在台式机上执行任意 gmx 子命令（白名单内，非交互）
python3 -m core.hub_mailbox run --kind gmx --arg --version
python3 -m core.hub_mailbox run --kind gmx --arg solvate --arg -cs --arg spc216.gro --arg -box --arg 3 --arg 3 --arg 3

# 4) 自检 / 同步
python3 -m core.hub_mailbox run --kind selfcheck --timeout 600
python3 -m core.hub_mailbox run --kind sync --timeout 600

# 5) 只看队列、只取结果
python3 -m core.hub_mailbox ls
python3 -m core.hub_mailbox wait 20261029T131500-1a2b --timeout 900
python3 -m core.hub_mailbox show 20261029T131500-1a2b
```

返回结果示例（所有传输共用同一 schema）：

```json
{"schema":"cgmd.mailbox.result.v1","id":"...","kind":"smoke","status":"ok",
 "summary":"gmx 2025.1: 100 ps integrated on gpu","seconds":23.5,
 "detail":{"report":{...},"artifact":"results/status/gmx_smoke.json"},
 "logs_tail":["..."]}
```

`status` 取值：`ok` `fail` `error` `unsupported` `timeout` `lost`。
`lost` / `timeout` 说明台式机没取到或还在忙——不会让你无限等。

### 安全边界

| 类别 | 说明 |
| --- | --- |
| `gmx` | 只允许白名单子命令（`mdrun` `grompp` `solvate` `energy` `check` …），参数里的 `; & | < > \`` `$(` 一律拒绝 |
| `shell` | **默认关闭**，必须用 `-AllowShell` 启动或配置 `"allow_shell": true` |
| 其他 | 未知 `kind` 会立刻回 `unsupported`，不会执行 |

---

## 3. 局域网直连：笔记本 ↔ 台式机（毫秒级）

信箱走公网 git，最慢要等一个轮询周期（≤60 s）。同一个 WiFi 下就直接打：

```powershell
# 台式机上跑一次（普通权限即可，不用管理员）
powershell -NoProfile -ExecutionPolicy Bypass -File C:\cgmd\0fuye\skills\cgmd-hub\runner\Invoke-CgmdBridge.ps1
```

监听 `0.0.0.0:8765`，接口只有三个：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | 活着吗、gmx 版本、显卡 |
| GET | `/status` | 最近一次 100 ps 报告 + 心跳 |
| POST | `/job` | `{"kind":"ping|smoke|selfcheck|gmx","args":{...}}` |

笔记本侧（任意有 Python 的机器）：

```bash
python3 -m core.desk_bridge ping   --host 192.168.1.23
python3 -m core.desk_bridge status --host 192.168.1.23
python3 -m core.desk_bridge smoke  --host 192.168.1.23 --timeout 900
python3 -m core.desk_bridge gmx    --host 192.168.1.23 -- --version
```

怎么知道台式机的 IP？让信箱告诉你（返回里带 `lan` 和 `bridge_port`）：

```bash
python3 -m core.hub_mailbox run --kind ping --timeout 300 | python3 -c "import json,sys;print(json.load(sys.stdin)['detail']['lan'])"
```

**访问控制**：回环与 `10/8`、`172.16/12`、`192.168/16` 直接放行；其他来源必须带
`X-CGMD-Token`（配置里 `bridge_token`）。`shell` 依旧默认关闭。

**首次放行端口**（可选，需要一次管理员权限，之后永久有效）：

```powershell
netsh advfirewall firewall add rule name="CGMD bridge" dir=in action=allow protocol=TCP localport=8765
# 或者：Invoke-CgmdBridge.ps1 -OpenFirewall（同样要管理员）
```

不做这一步也不影响互通——退回信箱总线即可，只是慢一点。

---

## 4. 两条链路怎么选

```
同局域网、要秒回、要立刻看 gmx 输出   →  局域网桥  core.desk_bridge.py
任何网络、要可靠、要留档、要跨会话     →  信箱总线  core.hub_mailbox.py
两者都挂了                            →  ntfy 推送照旧（arena-beacon-95bc796a66）
```

设计上两者返回同一个 `cgmd.mailbox.result.v1`，脚本可以「先试桥、失败退信箱」：

```python
from core import desk_bridge, hub_mailbox
try:
    result = desk_bridge.smoke("192.168.1.23", timeout=900)
except desk_bridge.BridgeError:
    job_id = hub_mailbox.send(".", "smoke", {"ps": 100})
    result = hub_mailbox.wait(".", job_id, timeout=1800)
```
