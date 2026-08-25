# 飞牛桥 feiniu-bridge（fnos-gateway）

> English: [README_EN.md](README_EN.md)

自研的 fnOS NAS 网关服务。做两件事：

1. **`/ssh-ws`**：WebSocket → SSH（TCP 22）桥接。fnOS 内置的公网反代是纯 L7、不支持 TCP 透传，SSH 过不去；这个端点把 SSH 裹进 WebSocket，让办公室能 `ssh nas` 免密直连 NAS。
2. **`/api/{endpoint}`**：HTTP → fnOS WebSocket `appcgi.*` 桥接（与 trim-cli 同协议），供外部工具调用 fnOS 能力。

## 脱敏说明

本归档已脱敏，文中所有域名、IP、用户名、主机名均为**占位示例，不是真实值**：

| 占位符 | 含义 | 使用时替换为 |
| --- | --- | --- |
| `remote.example.com` | 公网域名（经 fnOS 面板映射到本网关） | 你自己的域名 |
| `192.168.1.100` | NAS 局域网 IP | 你的 NAS 局域网 IP |
| `alice` | NAS 登录用户名 | 你的 fnOS 用户名 |
| `/vol2/<uid>/` | fnOS 用户目录路径 | 你的实际用户目录 |

源码中的 IP 同样是占位值——照抄部署前必须先改成你自己的 NAS 地址。

## 架构

```
办公室 Mac
  └─ ssh nas  (ProxyCommand: websocat -b wss://remote.example.com/ssh-ws)
       └─ 公网边缘：fnOS 内置 L7 反代（443 TLS，支持 WS，无 TCP 透传）
            └─ fnos-gateway 容器（192.168.1.100:8081，uvicorn + FastAPI）
                 ├─ /ssh-ws ──asyncio TCP──▶ 192.168.1.100:22 (sshd)
                 └─ /api/* ──websockets──▶ ws://192.168.1.100:5666 (fnOS appcgi)
```

## 目录结构

- `src/` — 部署源码：`gateway.py`（v1.1.0）、`Dockerfile`、`docker-compose.yml`
- `backup/` — `gateway.py.bak-20260825`（v1.0.0 原件，无 /ssh-ws）
- `docs/` — 过程文档（SSH 打通的排查与决策记录）
- `skill/` — fnos-remote-ops 技能归档（Agent 远程操作 playbook），用途见 `skill/README.md`
- `deploy.sh` — 把 `src/gateway.py` 同步到部署目录并热更新容器

## 部署关系

- **部署目录**：`/vol1/docker/fnos-gateway`（fnOS 面板注册的 compose 项目，8081→8080）
- **本目录**：源码归档与文档（source of truth）
- **更新流程**：改 `src/gateway.py` → 跑 `./deploy.sh`（cp 到部署目录 + `docker cp` + `restart`）。
  注意镜像是 `COPY gateway.py` 进镜像的——只改部署目录不 docker cp，容器重建会回退旧版；要彻底更新镜像请 `docker compose build && up -d`。

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

## 变更日志

- **v1.1.0**（2026-08-25）：新增 `/ssh-ws` SSH 桥接端点
- **v1.0.0**（2026-08-17）：初版，`/api` 桥接
