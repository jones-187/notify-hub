# notify-hub 部署步骤（Windows NAS）

照这份步骤做，你会在 NAS 上用**一个容器**把 notify-hub 跑起来：公网只开 MCP 一个
**入口**，内网另开普通 HTTP 接口，**排期**和**消息**都落在宿主机的一个数据目录里，
容器重建后还在。

术语见 [GLOSSARY.md](../GLOSSARY.md)。端口边界的决策见
[docs/adr/0002](../docs/adr/0002-expose-only-the-ingress.md)。

## 你会得到什么

| 端口 | 路径 | 谁用 | 是否经内网穿透 |
| --- | --- | --- | --- |
| 8080 | `/mcp` | AI（pi），对公网 | 是，**只映射这一条** |
| 8081 | `/notify`、`/healthz`、`/messages` | 监控工具与脚本，只在内网 | 否 |

- **入口**（8080）只挂 MCP，每次请求都要 `Authorization: Bearer <令牌>`。
- **内网端口**（8081）挂立刻发送、健康检查、只读列表；除 `/healthz` 外都要令牌。
- 数据库是单个文件，落在挂载卷里：宿主机 `./data/notify.db`，容器内 `/data/notify.db`。
- 令牌只从环境变量 `NOTIFY_TOKEN` 传入，不写进镜像、不入库、不进 git。

## 前置条件

- NAS 上装了 Docker，且带 Docker Compose v2（命令是 `docker compose`，不是老的
  `docker-compose`）。
- 本仓库的代码已经放到 NAS 上（下文用 `<仓库目录>` 指这个目录）。
- 一台 iPhone（装 Bark）和/或 Android、Windows（装 ntfy）。

## 步骤 1：生成令牌

生成一个 32 字节的十六进制令牌：

```
# Linux / macOS
openssl rand -hex 32

# Windows（PowerShell 或 cmd，只要有 Python）
python -c "import secrets; print(secrets.token_hex(32))"
```

把输出抄下来，下一步填进 `.env`。生成后不要提交到 git。

## 步骤 2：准备通道地址

一个**通道**就是一条 Apprise URL。现在支持两种：

- **Bark（iPhone）**：`bark://{host}/{device_key}`
  - `{host}`：Bark 服务器地址。用官方服务就填 `api.day.app`；自建就填自己的域名或
    IP。
  - `{device_key}`：Bark App 里那串设备 key。
  - 例：`bark://api.day.app/abcdEFG123`
- **ntfy（Android、Windows）**：`ntfy://{user}:{password}@{host}:{port}/{topic}`
  - `{port}`：官方服务是 `443`（走 `ntfys://` 时端口可省），自建常见 `2586`。
  - 例：`ntfy://myuser:mypass@ntfy.sh:443/mytopic`
  - 自建例：`ntfy://myuser:mypass@192.168.1.10:2586/notify`

一条消息会发给所有启用中的通道。以后加微信，就是往通道表里插一行，不改代码、
不重建镜像。

## 步骤 3：填 `.env`

```
cp .env.example .env
```

用编辑器打开 `.env`，把 `NOTIFY_TOKEN=` 后面填上步骤 1 生成的令牌。`.env` 已在
`.gitignore` 里，也不会进镜像。**不要在 `.env` 里留空令牌**：compose 会直接报错，
不会用空令牌把服务起起来。

## 步骤 4：起容器

```
cd <仓库目录>
docker compose up -d --build
```

第一次会构建镜像：基础镜像是 `python:3.12-slim`，用镜像里的 `uv` 按仓库里的
`uv.lock` 装依赖（`uv sync --frozen`），再装本项目。依赖版本由锁文件钉死。

## 步骤 5：把通道地址填进通道表

服务没有加通道的 HTTP 接口，用一条一次性命令在容器里写库：

```
docker compose exec notify-hub python -c "
from notify_hub.store import Store
s = Store('/data/notify.db')
s.add_channel('bark://api.day.app/你的device_key')
s.add_channel('ntfy://myuser:mypass@ntfy.sh:443/mytopic')
print('已添加，当前通道：')
for c in s.list_enabled_channels():
    print(c.id, c.apprise_url)
"
```

- 地址里有 `$`、`!` 等 shell 特殊字符时，注意引号；整条 `-c` 用双引号包住时，
  内部字符串用单引号。
- 这条命令是追加，重复执行会重复加同一行。
- 想临时关掉某个通道（例如换了手机），把它的 `enabled` 置 0 即可，不用重建容器。

## 步骤 6：看日志与健康检查

```
docker compose logs -f          # 日志全部走标准输出，一处看
docker compose ps               # 看 State 与健康状态
curl http://127.0.0.1:8081/healthz    # 回一行 ok，免令牌
```

从内网立刻发一条消息，验证端到端（**这一步会真的发到手机**）：

```
curl -X POST http://127.0.0.1:8081/notify ^
  -H "Authorization: Bearer <令牌>" ^
  -H "Content-Type: application/json" ^
  -d "{\"title\":\"测试\",\"body\":\"来自 NAS\"}"
```

Linux/macOS 上把续行符 `^` 换成 `\`。返回 `{"id": 1}` 说明服务收下了。查最近的消息：

```
curl -H "Authorization: Bearer <令牌>" http://127.0.0.1:8081/messages
```

每条消息带 `status`、`channel_results`、`last_error`，可以据此确认到底哪个通道失败。

## 步骤 7：配内网穿透（只映射 MCP 端口）

- 在节点小宝里，把内网穿透映射到 **8080**，最终地址形如
  `https://xxx.iepose.cn/mcp`（TLS 由穿透提供）。
- **不要映射 8081**。内网端口只给局域网里的监控工具用。
- 在 pi 侧用 `pi mcp add` 配上这个 URL 和 bearer 令牌（具体参数按 pi 文档；pi 不支持
  旧式 SSE，这里用的是 streamable HTTP，路径 `/mcp`）。

## 步骤 8：备份数据库文件

数据库就是单个文件 `./data/notify.db`，备份就是复制它。为保险起见先停容器再复制：

```
docker compose stop
cp data/notify.db data/notify.db.bak-$(date +%Y%m%d)
docker compose start
```

Windows PowerShell：

```
docker compose stop
Copy-Item data\notify.db "data\notify.db.bak-$(Get-Date -Format yyyyMMdd)"
docker compose start
```

恢复：把备份文件放回 `data/notify.db`，再 `docker compose up -d`。

## 步骤 9：升级镜像

```
cd <仓库目录>
git pull
docker compose build --pull
docker compose up -d
```

数据在挂载卷 `./data` 里，重建容器不会丢。要能回滚，就在构建新镜像前给旧的打个
标签（例如 `docker tag notify-hub:latest notify-hub:prev`），出问题就切回去。

## 本机验证不了的部分（重要）

这台开发机**没有 Docker**，所以下面几件事我在本机**没有验证过**，不假装验证过。
到 NAS 上按“怎么确认成功”一栏自己确认。

1. **构建镜像**：没跑过 `docker compose build`，所以不保证镜像一定构建成功。
   - 到 NAS 上确认：`docker compose build` 正常结束且无报错；
     `docker compose images` 能看到 `notify-hub`。
   - 已知风险：`Dockerfile` 里 `ghcr.io/astral-sh/uv:latest` 依赖外网拉取，NAS 若拉不动
     这个镜像，改成固定版本号或改用 `pip install uv`。
2. **起容器**：没起过，所以没验证过进程真的监听两个端口。
   - 到 NAS 上确认：`docker compose ps` 里 State 是 `Up`、健康状态是 `healthy`；
     `docker compose logs` 里能看到 `notify-hub 已启动：公网端口 8080（/mcp），内网端口 8081…`。
3. **真发一条通知**：从没真发到手机（本机的测试用假的转发层，绝不真发）。
   - 到 NAS 上确认：步骤 6 的 `curl` 返回 `{"id": ...}`，手机真的收到。
4. **重启后补发未发的消息**：只能在 NAS 上测（规格里也把这条列为部署后要实测的点）。
   - 测法：排一条一两分钟后的**消息**，到点前 `docker compose restart`，等过了发送时间
     看是否补发。预期会补发，因为排期存在数据库里，不在内存里。
5. **端口边界与穿透**：只映射 8080 是否真的对外、8081 是否只在内网，只能在配好穿透后
   从外部实际打一下确认。
6. **优雅关机**：容器收到 `SIGTERM` 时两个端口是否都干净退出，本机没验证。

## 本机验证了什么

- 新增的部署产物检查测试通过（`tests/test_deploy_artifacts.py`）：Dockerfile 基础镜像
  与锁文件、compose 的两个端口映射、数据卷与 `NOTIFY_DB`、免令牌健康检查、令牌只从
  环境变量来、`.env.example` 无真令牌、`.env` 进了 `.gitignore` 与 `.dockerignore`、
  部署文档包含必需步骤。
- 全部单元与集成测试（共 39 个原有 + 本次新增）继续通过。

## 故障排查

- `docker compose` 报 `NOTIFY_TOKEN 未设置`：`.env` 没填或没从 `.env.example` 复制。
- 容器起不来：`docker compose logs` 看是不是端口 8080/8081 被占用。
- 健康检查 `unhealthy`：内网端口没起来，看日志。
- 手机收不到：`GET /messages` 看该消息的 `last_error`。Apprise 地址写错会记成
  “通道地址无效”，网络问题会记成连接错误。
