# fnos-remote-ops 技能归档

> English summary below.

归档自本机 QoderWork 技能 `~/.qoderwork/skills/fnos-remote-ops/`（v1.1.0，2026-08-25）。

## 这个技能是干什么的

它是这台 NAS 的 Agent 远程操作 playbook，也是飞牛桥「Agent 直接调用」能力的使用手册。

飞牛桥网关不只是给人用的——它让 Agent 能直接调用 NAS：`/ssh-ws` 端点使 Agent 经 WebSocket 拿到完整 NAS shell（shell/scp/sudo），2026-08-25 的 SSH 打通全程就是 Agent 自主通过这个通道完成的。这个技能把 Agent 操作 NAS 需要的知识固化下来：

- **通道选择**：ssh nas 首选、trim-cli 兜底、qp-nginx 取件路由最后手段；
- **变更安全流程**：备份 → 隔离（永不永久删除）→ 验证 → 清理；
- **服务地图**：QwenPaw、qp-nginx、trendradar、fnos-gateway、fnOS 反代各自的位置与坑；
- **坑集**：docker exec 要 `-i`、confd 临时文件禁 .conf 后缀、cron 永不触发的写法等。

人直接 SSH 上 NAS 维护时它同样适用，只是首要读者是 Agent。

## Agent 直调能力现状

| 层 | 端点 | 状态 |
| --- | --- | --- |
| Shell 层 | `/ssh-ws` | 已验证，Agent 直调主通道 |
| 结构化接口层 | `POST /api/{endpoint}` | v1.2 待通：被 fnOS ws 登录握手拦住（errno 65534） |

细节见 `../README.md`「Agent 直接调用」与 `../docs/process-20260825.md`「Agent 直调能力验证与遗留」。

---

## What this is (English)

Archived from the local QoderWork skill `fnos-remote-ops` (v1.1.0, 2026-08-25). It is the Agent remote-ops playbook for this NAS, and the user manual for feiniu-bridge's agent-invocation capability: the gateway's `/ssh-ws` endpoint gives an agent a full NAS shell over WebSocket, and the entire 2026-08-25 SSH enablement was carried out by an agent through it. The skill codifies channel selection, the safe-change flow (backup → isolate → verify → clean up), the service map, and the known pitfalls. The shell layer is verified; the structured `POST /api` layer is pending the fnOS ws login handshake (v1.2).
