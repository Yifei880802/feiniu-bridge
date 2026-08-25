---
name: fnos-remote-ops
description: 家用 fnOS NAS（nas.example.com / 192.168.1.100，占位示例）远程操作 playbook：通道选择（ssh nas 首选、trim-cli 兜底、qp-nginx 取件路由最后手段）、变更标准流程（备份-隔离-验证-清理）、服务地图（QwenPaw/qp-nginx/trendradar/fnos-gateway/fnOS 反代）与坑集；也是网关 Agent 直调能力的使用手册。当用户要求诊断、配置、修改 NAS 上的服务、容器、cron、反向代理映射或取文件时使用。
version: 1.1.0
---

# fnOS NAS 远程操作 Playbook

> **脱敏归档副本**：本文件中的域名、IP、用户名、路由 token 均为占位示例（`*.example.com`、`192.168.1.100`、`alice`、`k7m9x2p`），不是真实值；使用时替换为你自己的环境。

目标机：fnOS ME mini（LAN 192.168.1.100，用户 alice uid=1000，HOME=/home/alice，sudo 密码=登录密码，远程用 `echo pwd | sudo -S`）。

## 通道选择

1. **ssh nas（首选）**：免密密钥登录；ssh config Host nas 的 ProxyCommand 为 `websocat -b wss://remote.example.com/ssh-ws`（fnOS 内置 L7 反代无 TCP 透传，靠 fnos-gateway 的 /ssh-ws 做 WS→22 桥接）。shell/scp/sftp/sudo 全可用。非交互输密码用 `SSH_ASKPASS=<脚本> SSH_ASKPASS_REQUIRE=force DISPLAY=:0`（expect 在本机偶报 "no more ptys"）。
2. **trim-cli**（命令细节见 trim-cli 技能）：文件/docker/应用/存储的结构化管理；SSH 断时也可用。报 wss 连接失败或 errno 135168 多为 session 过期，先重新 login，`file ls` 快速测连通。
3. **取件路由（最后手段）**：需要批量取文本输出且前两者不可用时，见下文。

## 服务地图

- QwenPaw：venv /vol1/@apphome/com.example.app/venv/；数据/日志 /vol1/@appshare/com.example.app/.qwenpaw/；重启只能 App Center 停用→启用；活体看 backflow records.jsonl 的 proxy_event_index 递增 + output_tokens。
- qp-nginx：confd /vol2/<uid>/qwenpaw-nginx/confd 挂载为 /etc/nginx/conf.d，**全部 *.conf 都会被加载**——临时文件禁用 .conf 后缀（重复 upstream 致 nginx 起不来、全站 502）；常态只留 qp.conf（干净基线 1572B、不含取件路由 token，上传前 grep 确认）。
- trendradar：/vol1/trendradar/config|output；入口 `python -m trendradar`（cwd=/app，非 main.py）；entrypoint 每次启动用 CRON_SCHEDULE 环境变量重新生成 /tmp/crontab（现值 "0 0 29 2 *"≈永不触发）；推送靠宿主 cron 7:00/7:10（crontabs/com.example.app，引用容器名 trendradar，重建容器须保名）。
- fnos-gateway（飞牛桥，源码归档 /vol2/<uid>/projects/feiniu-bridge/）：/vol1/docker/fnos-gateway（compose 8081→8080，FastAPI）；镜像 COPY 代码——改 gateway.py 后须 `docker cp` + restart（或 compose build，否则重建容器回退旧版）。Agent 直调两层：① /ssh-ws 让 Agent 经 websocat 拿完整 shell（已验证，即本技能主通道）；② POST /api/{ep} 转 fnOS ws appcgi.*（同 trim-cli 协议）的结构化 HTTP 面——当前裸 ws 缺 fnOS 登录握手，appcgi/user.* 一律 errno 65534，待 v1.2 实现 user.authToken→user.tokenLogin 握手或 session 注入。
- 公网边缘 = fnOS 内置 L7 反代：无 TCP 透传、支持 WS；域名映射（remote.example.com 等）在 fnOS 面板改 Service 指向。

## 变更标准流程

1. 备份原件：`cp x x.bak-<YYYYMMDD>`。
2. 永不永久删除：`file mv` 隔离到 /vol2/<uid>/.trash-quarantine-<日期>/。
3. 改后验证：服务活体 + 站点根 200 + 取件口已关（返回 SPA HTML 兜底页）。
4. 清理清单：恢复干净 qp.conf → restart qp-nginx → 隔离 confd 临时文件 → `docker container rm --yes` 临时容器 → 删本地含凭据临时文件。

## 取件路由（最后手段诊断通道）

1. 脚本上传 confd（.sh/.txt 后缀）。
2. qp.conf 临时加（路由 token 自选随机串，注意保密）：
   ```
   location /k7m9x2p/ { alias /etc/nginx/conf.d/; add_header Cache-Control no-store; }
   ```
3. `docker container restart qp-nginx`；经 https://app.example.com/k7m9x2p/<file> 取结果。
4. 跑脚本的容器模板（/run 挂载后可用宿主 docker CLI）：
   `docker container create --name qp-x --image nginx:alpine --start --mount /vol1:/vol1 --mount /vol2:/vol2 --mount /var:/var --mount /usr:/usr --mount /lib:/lib --mount /lib64:/lib64 --mount /bin:/bin --mount /run:/run --cmd sh --cmd /vol2/<uid>/qwenpaw-nginx/confd/x.sh`
5. 用完必走清理清单。

## 坑集

- trim-cli `--cmd` 含空格被 word-split → 一律上传 .sh 传路径。
- `docker exec` 传 stdin/heredoc 必须加 `-i`，否则静默无输出。
- `container rm` 必须 `--yes`；errno 52428814 = 容器不存在。
- cron 永不触发：用 "0 0 29 2 *"（2月29日，下次 2028，安静）；"0 0 30 2 *"（2月30日）会让 supercronic 每秒刷 warning 撑爆日志。
- `grep -c` 无匹配 exit 1 会断 `&&` 链。
- sshd 加固与 fnOS SSH 开关共存：加固行追加在 /etc/ssh/sshd_config.d/trim_sshd.conf（该 include 先于主配置生效），`systemctl reload ssh` 生效。

## 验证

`ssh nas 'echo ok'`；`curl -s -o /dev/null -w '%{http_code}' https://app.example.com/` 得 200；`curl https://app.example.com/k7m9x2p/任意文件` 返回 SPA HTML（路由已关）。
