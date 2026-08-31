FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn websockets httpx
COPY gateway.py .
EXPOSE 8080
# --no-access-log：避免请求行（含 ?token= 查询参数）进入容器日志
CMD ["uvicorn", "gateway:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
