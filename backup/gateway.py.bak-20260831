from fastapi import FastAPI, Request, HTTPException, WebSocket
import websockets
import json
import asyncio
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="fnOS API Gateway", version="1.1.0")

SSH_HOST = "192.168.1.100"  # 占位示例：替换为你的 NAS 局域网 IP
SSH_PORT = 22


@app.get("/")
async def root():
    return {"service": "fnOS API Gateway", "status": "running", "version": "1.1.0"}


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
        ws_url = "ws://192.168.1.100:5666/websocket?type=main"  # 占位示例：替换为你的 NAS 局域网 IP

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
