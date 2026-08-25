#!/bin/sh
# 飞牛桥热更新：src/gateway.py -> 部署目录 -> 容器 -> 重启 -> 验证
# 注意：本归档已脱敏，以下路径与 IP 均为占位示例，直接运行前替换为你的实际值
set -e
SRC=/vol2/<uid>/projects/feiniu-bridge/src/gateway.py
DEPLOY=/vol1/docker/fnos-gateway/gateway.py
cp "$SRC" "$DEPLOY"
docker cp "$DEPLOY" fnos-gateway:/app/gateway.py
docker restart fnos-gateway
sleep 6
wget -q -O - --timeout=5 http://192.168.1.100:8081/ && echo && echo DEPLOY_OK
