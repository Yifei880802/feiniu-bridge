# feiniu-bridge (fnos-gateway)

> 中文版: [README.md](README.md)

A self-built gateway service for the fnOS NAS. It does two things:

1. **`/ssh-ws`**: a WebSocket → SSH (TCP 22) bridge. The fnOS built-in public reverse proxy is pure L7 with no TCP passthrough, so raw SSH cannot cross it; this endpoint wraps SSH in WebSocket so the office Mac can `ssh nas` key-authenticated from anywhere.
2. **`/api/{endpoint}`**: an HTTP → fnOS WebSocket `appcgi.*` bridge (same protocol as trim-cli), letting external tools call fnOS capabilities.

## Sanitization notice

This archive is sanitized. All domains, IPs, usernames and hostnames below are **placeholders, not real values**:

| Placeholder | Meaning | Replace with |
| --- | --- | --- |
| `remote.example.com` | Public domain (mapped to this gateway via the fnOS panel) | Your own domain |
| `192.168.1.100` | The NAS's LAN IP | Your NAS's LAN IP |
| `alice` | NAS login username | Your fnOS username |
| `/vol2/<uid>/` | fnOS per-user directory path | Your actual user directory |

The IPs in the source code are placeholders too — change them to your own NAS address before deploying.

## Architecture

```
Office Mac
  └─ ssh nas  (ProxyCommand: websocat -b wss://remote.example.com/ssh-ws)
       └─ Public edge: fnOS built-in L7 reverse proxy (443 TLS, WS-capable, no TCP passthrough)
            └─ fnos-gateway container (192.168.1.100:8081, uvicorn + FastAPI)
                 ├─ /ssh-ws ──asyncio TCP──▶ 192.168.1.100:22 (sshd)
                 └─ /api/* ──websockets──▶ ws://192.168.1.100:5666 (fnOS appcgi)
```

## Layout

- `src/` — deployable source: `gateway.py` (v1.1.0), `Dockerfile`, `docker-compose.yml`
- `backup/` — `gateway.py.bak-20260825` (v1.0.0 original, without /ssh-ws)
- `docs/` — process notes (the SSH enablement investigation and decisions)
- `skill/` — archive of the fnos-remote-ops skill (Agent remote-ops playbook); purpose in `skill/README.md`
- `deploy.sh` — syncs `src/gateway.py` to the deploy dir and hot-updates the container

## Deployment relationship

- **Deploy dir**: `/vol1/docker/fnos-gateway` (compose project registered in the fnOS panel, 8081→8080)
- **This dir**: source archive and docs (source of truth)
- **Update flow**: edit `src/gateway.py` → run `./deploy.sh` (cp to deploy dir + `docker cp` + `restart`).
  Note the image `COPY gateway.py` at build time — without `docker cp`, a recreated container reverts to the baked-in version; to update the image for good, run `docker compose build && up -d`.

## Client setup (Mac)

```
# ~/.ssh/config
Host nas
  HostName remote.example.com
  User alice
  ProxyCommand websocat -b wss://remote.example.com/ssh-ws
```

Requires `brew install websocat`. Then just `ssh nas` (ed25519 key pushed, passwordless).

## fnOS panel mapping

`remote.example.com` → Service `http://192.168.1.100:8081` (fnOS built-in L7 proxy with WS passthrough).

## Security posture

- Key-only login: `PasswordAuthentication no` and `KbdInteractiveAuthentication no` appended to `/etc/ssh/sshd_config.d/trim_sshd.conf`, applied via `systemctl reload ssh`
- `/ssh-ws` itself is unauthenticated — the security boundary is sshd (pubkey). This is equivalent to exposing port 22's auth surface over WS; acceptable. To harden further, add a query-token check in the endpoint.

## Agent invocation

The gateway is built for direct agent invocation — the 2026-08-25 SSH enablement was itself performed autonomously by an agent (QoderWork) through this gateway. There are two invocation layers:

- **Shell layer (verified, the current primary channel)**: `/ssh-ws` + websocat gives an agent a full SSH session (shell/scp/sudo), letting it drive the NAS exactly like a human would. The companion skill `fnos-remote-ops` is archived in `skill/`, codifying channel selection and safe-change procedures.
- **Structured layer (v1.2, pending)**: `POST /api/{endpoint}` is designed for programmatic agent calls to fnOS capabilities (HTTP in, JSON out, no ws client needed), but is currently blocked by fnOS's ws login wall (errno 65534). Investigation details and the pending login handshake (`user.authToken` → `user.tokenLogin`) are documented in `docs/process-20260825.md`.

## API reference

| Endpoint | Method | Description |
| --- | --- | --- |
| `/` | GET | Health check, returns version |
| `/api/{endpoint}` | POST | JSON body forwarded as `appcgi.{endpoint}` to fnOS ws; returns response JSON |
| `/ssh-ws` | WS | Raw byte stream ↔ SSH TCP bridge |

## Changelog

- **v1.1.0** (2026-08-25): added `/ssh-ws` SSH bridge endpoint
- **v1.0.0** (2026-08-17): initial release, `/api` bridge
