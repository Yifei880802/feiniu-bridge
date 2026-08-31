# 飞牛桥 feiniu-bridge（fnos-gateway）

> English: [README_EN.md](README_EN.md)

自研的 fnOS NAS 网关服务。做三件事：

1. **`/ssh-ws`**：WebSocket → SSH（TCP 22）桥接。fnOS 内置的公网反代是纯 L7、不支持 TCP 透传，SSH 过不去；这个端点把 SSH 裹进 WebSocket，让办公室能 `ssh nas` 免密直连 NAS。
2. **`/api/{endpoint}`**：HTTP → fnOS WebSocket `appcgi.*` 桥接（与 trim-cli 同协议），供外部工具调用 fnOS 能力。
3. **`/sag-mcp/`**（v1.1.1）：带鉴权的 MCP 反向代理，把局域网内 SAG 知识库的 Streamable HTTP MCP 端点暴露到公网。网关代持知识库 JWT、要求访问令牌，配合无状态 HTTP 传输，让 MCP 客户端在网络抖动后自动恢复，不再依赖脆弱的长连接 WS + stdio 隧道。

## 脱敏说明

本归档已脱敏，文中所有域名、IP、用户名、主机名均为**占位示例，不是真实值**：

| 占位符 | 含义 | 使用时替换为 |
| --- | --- | --- |
| `remote.example.com` | 公网域名（经 fnOS 面板映射到本网关） | 你自己的域名 |
| `192.168.1.100` | NAS 局域网 IP | 你的 NAS 局域网 IP |
| `alice` | NAS 登录用户名 | 你的 fnOS 用户名 |
| `/vol2/<uid>/` | fnOS 用户目录路径 | 你的实际用户目录 |
| `k7m9x2p_REPLACE_ME` | `/sag-mcp/` 访问令牌占位 | 你自己生成的强随机值（`openssl rand -hex 32`） |
| `your-sag-user` | SAG 知识库单用户名 | 你的知识库用户名 |

源码中的 IP 同样是占位值——照抄部署前必须先改成你自己的 NAS 地址。

## 架构

```
办公室 Mac
  └─ ssh nas  (ProxyCommand: websocat -b wss://remote.example.com/ssh-ws)
       └─ 公网边缘：fnOS 内置 L7 反代（443 TLS，支持 WS，无 TCP 透传）
            └─ fnos-gateway 容器（192.168.1.100:8081，uvicorn + FastAPI）
                 ├─ /ssh-ws ──asyncio TCP──▶ 192.168.1.100:22 (sshd)
                 ├─ /api/* ──websockets──▶ ws://192.168.1.100:5666 (fnOS appcgi)
                 └─ /sag-mcp/* ──httpx 流式反代──▶ http://192.168.1.100:8000/mcp/ (SAG 知识库)
```

## 目录结构

- `src/` — 部署源码：`gateway.py`（v1.1.1）、`Dockerfile`、`docker-compose.yml`
- `backup/` — `gateway.py.bak-20260825`（v1.0.0 原件，无 /ssh-ws）、`gateway.py.bak-20260831`（v1.1.0 原件，无 /sag-mcp/）
- `docs/` — 过程文档（SSH 打通的排查与决策记录；MCP 隧道断连根因排查与 HTTP 自愈代理设计）
- `skill/` — fnos-remote-ops 技能归档（Agent 远程操作 playbook），用途见 `skill/README.md`
- `deploy.sh` — 把 `src/gateway.py` 同步到部署目录并热更新容器
- `LICENSE` — MIT 许可证

## 部署关系

- **部署目录**：`/vol1/docker/fnos-gateway`（fnOS 面板注册的 compose 项目，8081→8080）
- **本目录**：源码归档与文档（source of truth）
- **更新流程**：改 `src/gateway.py` → 跑 `./deploy.sh`（cp 到部署目录 + `docker cp` + `restart`）。
  注意镜像是 `COPY gateway.py` 进镜像的——只改部署目录不 docker cp，容器重建会回退旧版；要彻底更新镜像请 `docker compose build && up -d`。
- **依赖**：v1.1.1 起镜像内需有 `httpx`（`Dockerfile` 已含）。若走 `docker cp` + `restart` 热更新而非重建镜像，须先在容器内 `pip install httpx`，详见 `docs/process-20260831.md` 的部署纪要。

## 客户端配置（Mac）

```
# ~/.ssh/config
Host nas
  HostName remote.example.com
  User alice
  ProxyCommand websocat -b wss://remote.example.com/ssh-ws
```

依赖 `brew install websocat`。配好后直接 `ssh nas`（已推 ed25519 公钥，免密）。

## fnOS 面板映射

`remote.example.com` → Service `http://192.168.1.100:8081`（fnOS 内置反代，L7 + WS 透传）。

## 安全现状

- 仅密钥登录：`/etc/ssh/sshd_config.d/trim_sshd.conf` 追加了 `PasswordAuthentication no` 与 `KbdInteractiveAuthentication no`，`systemctl reload ssh` 生效
- `/ssh-ws` 端点本身无认证——安全边界在 sshd（密钥），等同把 22 端口的认证面暴露成 WS 面，可接受；如要进一步收紧可在端点加 query token
- `/sag-mcp/` 端点有访问令牌（`X-SAG-Token` 头或 `?token=` 查询参数，时序安全比较），未配置令牌时返回 503 禁用。知识库 JWT 由网关代持、不出网。uvicorn 已关 access log，避免令牌出现在请求行日志。令牌本身是知识库内容的访问凭证，勿泄露、勿写入日志

## Agent 直接调用

这个网关本身就是给 Agent 直接调用的——2026-08-25 的 SSH 打通全程就是 Agent（QoderWork）经本网关自主完成的。Agent 直调分两层：

- **Shell 层（已验证，现阶段主通道）**：`/ssh-ws` + websocat，Agent 拿到完整 SSH 会话（shell/scp/sudo），操作 NAS 与人无异。配套技能 `fnos-remote-ops` 已归档于 `skill/`，其中固化了通道选择与变更安全流程。
- **结构化接口层（v1.2 待通）**：`POST /api/{endpoint}` 设计上让 Agent 以纯 HTTP 方式调用 fnOS 能力（JSON 进出，无需 ws 客户端），但当前被 fnOS ws 登录墙拦住（errno 65534）。排查细节与待实现的登录握手（`user.authToken` → `user.tokenLogin`）见 `docs/process-20260825.md`。

## API 参考

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/` | GET | 健康检查，返回版本 |
| `/api/{endpoint}` | POST | body JSON 转发为 `appcgi.{endpoint}` 到 fnOS ws，返回响应 JSON |
| `/ssh-ws` | WS | 原始字节流 ↔ SSH TCP 桥接 |
| `/sag-mcp/{subpath}` | GET/POST/DELETE | 带令牌的 MCP 反代，流式转发到知识库 `/mcp/`，网关注入 JWT |

## 许可与声明

- 本项目按 [MIT 许可证](LICENSE) 开源。
- 本项目为个人独立项目，与飞牛 fnOS 官方无关联、未获官方背书；「飞牛」「fnOS」及相关标识的商标权归其权利人所有。
- fnOS 接口协议基于对其接口行为的自行观察分析，仅供个人设备互操作参考；fnOS 更新可能随时导致接口变化而失效。
- 软件按「现状」提供，无任何明示或暗示担保，使用风险自负。

## 变更日志

- **v1.1.1**（2026-08-31）：新增 `/sag-mcp/` MCP 反代端点（带访问令牌、网关注入知识库 JWT、流式转发）；镜像加 `httpx` 依赖、uvicorn 关 access log。背景：MCP 长连接隧道反复断连，改走无状态 HTTP 自愈，见 `docs/process-20260831.md`
- **v1.1.0**（2026-08-25）：新增 `/ssh-ws` SSH 桥接端点
- **v1.0.0**（2026-08-17）：初版，`/api` 桥接
