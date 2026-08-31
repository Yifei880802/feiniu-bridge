from fastapi import FastAPI, Request, HTTPException, WebSocket
from fastapi.responses import StreamingResponse
import websockets
import httpx
import json
import asyncio
import hmac
import os
import logging
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="fnOS API Gateway", version="1.1.1")

SSH_HOST = "192.168.1.100"  # 占位示例：替换为你的 NAS 局域网 IP
SSH_PORT = 22

# ---- SAG MCP 代理配置 ----
# 占位示例：替换为你的 SAG 知识库 API 地址（本机容器网络）
SAG_API_BASE = "http://192.168.1.100:8000"
# 访问令牌从环境变量注入（见 docker-compose.yml），未设置时禁用该代理
SAG_MCP_TOKEN = os.environ.get("SAG_MCP_TOKEN", "")

_sag_jwt: Optional[str] = None
_sag_jwt_lock = asyncio.Lock()
_http_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=15.0, read=300.0, write=30.0, pool=15.0)
        )
    return _http_client


async def sag_login(client: httpx.AsyncClient) -> str:
    # SAG 单用户登录取 JWT；用户名按你的实例修改
    r = await client.post(f"{SAG_API_BASE}/api/v1/auth/login", json={"name": "your-sag-user"})
    r.raise_for_status()
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        raise RuntimeError(f"SAG login unexpected keys: {list(data.keys())}")
    return token


async def get_sag_jwt(client: httpx.AsyncClient, force: bool = False) -> str:
    global _sag_jwt
    async with _sag_jwt_lock:
        if _sag_jwt is None or force:
            _sag_jwt = await sag_login(client)
        return _sag_jwt


def check_mcp_token(request: Request) -> None:
    if not SAG_MCP_TOKEN:
        raise HTTPException(status_code=503, detail="sag-mcp proxy disabled")
    provided = request.headers.get("x-sag-token") or request.query_params.get("token", "")
    if not provided or not hmac.compare_digest(provided, SAG_MCP_TOKEN):
        raise HTTPException(status_code=401, detail="unauthorized")


# 不透传的请求头（认证由网关注入，hop-by-hop 头无意义）
_SKIP_REQ_HEADERS = {
    "host", "authorization", "x-sag-token", "content-length",
    "transfer-encoding", "connection", "keep-alive",
}
_SKIP_RESP_HEADERS = {"content-length", "transfer-encoding", "connection"}


async def _proxy_sag_mcp(subpath: str, request: Request):
    check_mcp_token(request)
    target = f"{SAG_API_BASE}/mcp/{subpath}"
    qs = [(k, v) for k, v in request.query_params.items() if k != "token"]
    body = await request.body()

    fwd_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in _SKIP_REQ_HEADERS
    }

    client = get_http_client()
    jwt = await get_sag_jwt(client)

    upstream = None
    for attempt in (1, 2):
        fwd_headers["Authorization"] = f"Bearer {jwt}"
        req = client.build_request(
            request.method, target, params=qs, content=body, headers=fwd_headers
        )
        upstream = await client.send(req, stream=True)
        if upstream.status_code == 401 and attempt == 1:
            await upstream.aclose()
            logger.info("sag-mcp: upstream 401, re-login and retry")
            jwt = await get_sag_jwt(client, force=True)
            continue
        break

    resp_headers = {
        k: v for k, v in upstream.headers.items()
        if k.lower() not in _SKIP_RESP_HEADERS
    }

    async def streamer():
        try:
            async for chunk in upstream.aiter_bytes(8192):
                yield chunk
        finally:
            await upstream.aclose()

    logger.info(f"sag-mcp: {request.method} /{subpath} -> {upstream.status_code}")
    return StreamingResponse(
        streamer(), status_code=upstream.status_code, headers=resp_headers
    )


@app.api_route("/sag-mcp", methods=["GET", "POST", "DELETE"])
@app.api_route("/sag-mcp/{subpath:path}", methods=["GET", "POST", "DELETE"])
async def sag_mcp_proxy(subpath: str, request: Request):
    return await _proxy_sag_mcp(subpath, request)


@app.get("/")
async def root():
    return {"service": "fnOS API Gateway", "status": "running", "version": "1.1.1"}


@app.websocket("/ssh-ws")
async def ssh_bridge(ws: WebSocket):
    """WebSocket -> SSH (TCP 22) 桥接，供 ProxyCommand websocat 使用"""
    await ws.accept()
    logger.info("ssh-ws: client connected")
    try:
        reader, writer = await asyncio.open_connection(SSH_HOST, SSH_PORT)
    except Exception as e:
        logger.error(f"ssh-ws: cannot reach sshd: {e}")
        await ws.close()
        return

    async def ws_to_tcp():
        try:
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                data = msg.get("bytes")
                if data is None and msg.get("text") is not None:
                    data = msg["text"].encode()
                if data:
                    writer.write(data)
                    await writer.drain()
        except Exception:
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def tcp_to_ws():
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                await ws.send_bytes(data)
        except Exception:
            pass
        finally:
            try:
                await ws.close()
            except Exception:
                pass

    await asyncio.gather(ws_to_tcp(), tcp_to_ws())
    logger.info("ssh-ws: session ended")


@app.post("/api/{endpoint:path}")
async def proxy(endpoint: str, request: Request):
    try:
        body = await request.json()
        import uuid
        req_id = str(uuid.uuid4())

        logger.info(f"收到请求: endpoint={endpoint}, req_id={req_id}")

        ws_msg = {"req": f"appcgi.{endpoint}", "reqid": req_id, **body}
        ws_url = f"ws://{SSH_HOST}:5666/websocket?type=main"

        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps(ws_msg))
            response = await asyncio.wait_for(ws.recv(), timeout=30)
            logger.info(f"收到响应: req_id={req_id}")
            return json.loads(response)

    except Exception as e:
        logger.error(f"错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
