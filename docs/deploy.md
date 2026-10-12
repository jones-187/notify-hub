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

> 表里的 8080 / 8081 是**宿主机端口默认值**。这两个端口若已被别的服务占用，在 `.env`
> 里用 `MCP_HOST_PORT` / `INTERNAL_HOST_PORT` 覆盖（见步骤 3）。下文出现 8080 / 8081
> 的地方，换成你实际设的值。容器内部永远是 8080 / 8081，服务代码不用改。
- 数据库是单个文件，落在挂载卷里：宿主机 `./data/notify.db`，容器内 `/data/notify.db`。
- 令牌只从环境变量 `NOTIFY_TOKEN` 传入，不写进镜像、不入库、不进 git。

## 前置条件

- NAS 上装了 Docker，且带 Docker Compose v2（命令是 `docker compose`，不是老的
  `docker-compose`）。
- 本仓库的代码已经放到 NAS 上，见[步骤 0](#步骤-0把代码放到-nas-上)（下文用
  `<仓库目录>` 指这个目录）。
- 一台 iPhone（装 Bark）；平板或电脑可选装 ntfy，走内网。
- NAS 的时钟已开自动校时（NTP）。排期依赖绝对时间，时钟不准会让提醒提前或延后。

## 步骤 0：把代码放到 NAS 上

容器是在 NAS 上现构建的，所以代码得先到 NAS。三种办法，按推荐排序。

**办法 A（推荐）：用你 NAS 上已有的 git 服务器**

如果 NAS 上已经跑着 git 服务器（例如 `F:\git-server\`），把本仓库也放进去。

在**开发机**上执行：

```
ssh jnas "git init --bare F:\git-server\notify-hub.git"
git remote add lan jnas@192.168.31.72:F:/git-server/notify-hub.git
git push lan master
```

然后在 **NAS** 上克隆：

```
git clone F:\git-server\notify-hub.git <仓库目录>
```

好处：以后升级只要 `git pull`（见步骤 9），不依赖 NAS 能不能上 GitHub。

**办法 B：在 NAS 上直接从 GitHub 克隆**

```
git clone https://github.com/<你的账号>/notify-hub.git <仓库目录>
```

注意：国内网络访问 GitHub 常常不稳定，NAS 上未必拉得动。拉不动就用办法 A。

**办法 C：直接拷贝目录**

把整个仓库目录复制到 NAS 上（网络共享、U 盘都行）。能用，但以后升级要手动覆盖，
不推荐。

克隆完确认一下：`git -C <仓库目录> log --oneline -1` 能看到提交。

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
- **ntfy（平板、电脑；也可给手机用）**：`ntfy://{user}:{password}@{host}:{port}/{topic}`
  - `{port}`：官方服务是 `443`（走 `ntfys://` 时端口可省），自建常见 `2586`。
  - 例：`ntfy://myuser:mypass@ntfy.sh:443/mytopic`
  - 自建例：`ntfy://myuser:mypass@192.168.1.10:2586/notify`
- **ntfy 就跟本服务跑在同一台机器上时，要特别小心**：容器**连不到宿主机的局域网 IP**
  （Docker Desktop 在 Windows / macOS 上的既有行为）。直接用
  `ntfy://192.168.1.10:2586/topic` 会超时。要改成：
  1. 把 ntfy 的端口映射改成绑所有接口（`8444:80`，而不是 `192.168.31.72:8444:80`）；
  2. 地址里的主机名换成 `host.docker.internal`，例如
     `ntfy://host.docker.internal:8444/mytopic`。
  自己判断的方法：在容器里连宿主机 LAN IP 的任意已发布端口，**超时**就是这个原因；
  而绑 `0.0.0.0` 的服务用 `host.docker.internal` 能连上。

一条消息会发给所有启用中的通道。以后加通道（例如企业微信），就是往通道表里插一行，
不改代码、不重建镜像。

> **自建通道与“人在外面”**：本服务是**寄件人**——它把消息交给通道服务端，再由通道
> 服务端转给设备。所以自建的 Bark / ntfy 只在**内网可达**，设备一旦离开内网就收不到。
> 要在外网也收到，要么用公开可达的服务（例如官方 Bark），要么给自建服务端也开一条
> 内网穿透。**注意：不要把自建的 ntfy 直接暴露到公网**——它默认没有任何认证，谁连上
> 都能读写所有 topic。

## 步骤 3：填 `.env`

复制模板（Windows 用 `copy`，Linux / macOS 用 `cp`）：

```
copy .env.example .env      # Windows，cmd 与 PowerShell 都可用
cp .env.example .env        # Linux / macOS
```

用编辑器打开 `.env`，把 `NOTIFY_TOKEN=` 后面填上步骤 1 生成的令牌。`.env` 已在
`.gitignore` 里，也不会进镜像。**不要在 `.env` 里留空令牌**：compose 会直接报错，
不会用空令牌把服务起起来。

> **换行符陷阱（Windows 上很容易踩）**：`.env` 必须存成 **LF** 换行，不能是 CRLF。
> 存成 CRLF 时令牌末尾会多一个看不见的 `\r`，结果是**每次请求都 401，而且极难查**。
> 用编辑器确认换行符是 LF。

**端口冲突**：如果 NAS 上 8080 或 8081 已被别的服务占用（用 `netstat -ano | findstr
":8080"` 查），在 `.env` 里加上空闲端口：

```
MCP_HOST_PORT=18080
INTERNAL_HOST_PORT=18081
```

这两个是**宿主机**端口，容器内部始终是 8080 / 8081。步骤 7 配内网穿透时映射的是
`MCP_HOST_PORT`。

## 步骤 4：起容器

```
cd <仓库目录>
docker compose up -d --build
```

第一次会构建镜像：基础镜像是 `python:3.12-slim`，用镜像里的 `uv` 按仓库里的
`uv.lock` 装依赖（`uv sync --frozen`），再装本项目。依赖版本由锁文件钉死。

**只能跑一个副本。** 排期存在单个 SQLite 文件里，`docker compose up --scale 2`
会让两个进程抢同一个库，**不要这样做**。

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

日志已经配了轮转（单个文件 10 MB、最多 3 份，见 `compose.yaml` 的 `logging`），
不用另外管磁盘。

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

**先确认容器能出网**。排期发消息靠的是**出站**连接，不是入站。在容器里打一下通道的
主机：

```
docker compose exec notify-hub python -c "
import urllib.request, urllib.error
for url in ['https://api.day.app', 'https://ntfy.sh']:
    try:
        urllib.request.urlopen(url, timeout=5)
        print(url, 'OK')
    except urllib.error.HTTPError as exc:
        print(url, '能连上（HTTP', exc.code, '）')
    except Exception as exc:
        print(url, '连不上:', exc)
"
```

自建通道就换成自己的地址。这里连不上，消息会记成“失败”，原因是连接错误。

## 步骤 7：配内网穿透（只映射 MCP 端口）

- 在节点小宝里，把内网穿透映射到**宿主机的 MCP 端口**（`MCP_HOST_PORT`，默认 8080），
  最终地址形如 `https://xxx.iepose.cn/mcp`（TLS 由穿透提供）。
- **不要映射内网端口**（`INTERNAL_HOST_PORT`，默认 8081）。它只给局域网里的监控工具用。
- 在 pi 侧这样接（pi 不支持旧式 SSE，这里用的是 streamable HTTP，路径 `/mcp`）：

  ```
  pi mcp add notify-hub --url https://<你的域名>/mcp --bearer-token-env-var NOTIFY_TOKEN
  pi mcp list      # 确认连得上、工具是 4 个
  ```

  `NOTIFY_TOKEN` 这个环境变量要设在**跑 pi 的那台电脑**上（不是 NAS 上）。加完在 pi
  里 `/reload`。

## 步骤 8（可选）：手动备份，平时不用做

**这个服务不备份也没什么损失。** 先看它到底存了什么：整个数据库就是单个文件
`./data/notify.db`，里面只有两张表——`channels`（通道地址，通常就几行）和
`messages`（发过的消息记录）。

丢了会怎样：

- 丢 `channels`：把几条通道地址重新填一遍，两分钟的事。
- 丢 `messages`：只是历史记录，没它服务照常跑。

所以**平时不做备份，也不要配定时任务**——为一个能两分钟重建的配置文件养一个
定时任务，还要顺带管它的日志和失败告警，不划算。真正值钱的是“怎么从零重建”，
那就是这份文档前面的步骤。

只有一种情况值得手动备一份：你打算大改通道表、或者升级前心里没底。那就：

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

备份完把 `data\notify.db.bak-*` 留着还是删掉都行，它只是一个副本，不影响正在跑的
服务。

恢复：把备份文件改名为 `data/notify.db`（盖掉现的）再 `docker compose up -d`。

## 步骤 9：升级镜像

```
cd <仓库目录>
git pull
docker compose build --pull
docker compose up -d
```

数据在挂载卷 `./data` 里，重建容器不会丢。要能回滚，就在构建新镜像前给旧的打个
标签（例如 `docker tag notify-hub:latest notify-hub:prev`），出问题就切回去。

## 令牌轮换（怀疑泄露时）

令牌一换，所有调用方都要跟着换：

1. 生成新令牌（步骤 1）。
2. 改 NAS 上 `<仓库目录>\.env` 里的 `NOTIFY_TOKEN=`。
3. `docker compose up -d`（要重建容器才会读到新环境变量）。
4. 改**跑 pi 那台电脑**上的 `NOTIFY_TOKEN` 环境变量，然后在 pi 里 `/reload`。
5. 有内网脚本调 `/notify` 的，同步改。

漏掉第 4 步的表现是：pi 那边一直 401。

## 为什么现在不需要反向代理

只暴露一个端口、一个路径（`/mcp`），域名和 HTTPS 都由内网穿透提供，**没有东西需要
分流**，所以不装 nginx / Caddy。

将来如果要在一个域名下同时挂多个服务或多条路径（例如把 Web 界面或 `/notify` 也放
出去），那时才需要反向代理。加反代时**本服务不用改代码**，因为：

- 它**不依赖 Host 头，也不对外发任何绝对 URL**：401 响应里只有
  `www-authenticate: Bearer error=...`（**没有** `resource_metadata` 绝对地址）、
  尾斜杠重定向用的是相对路径 `location: /mcp`、OAuth 发现端点被故意关闭。所以放在
  任何反代后面都不会被带歪。
- **但 `/mcp` 是写死的**（`mcp_app.py` 里的 `streamable_http_path="/mcp"`，没有环境变量
  能改）。反代**不能给它套个前缀再原样转发**，必须先 strip 掉前缀，否则会 404。

所以分流方式建议：优先用**子域名**（每个服务一个）；非要按路径分流，就把前缀留给
**别的**服务（例如 `/ntfy/`），让 `/mcp` 保持原样。

> 反代只要把 `/mcp` 原样转发到本服务的 MCP 端口即可；穿透的目标改成反代端口就行，
> 本服务不需要重建镜像。

## 本机验证不了的部分（重要）

这台开发机**没有 Docker**，所以下面几件事我在本机**没有验证过**，不假装验证过。
到 NAS 上按“怎么确认成功”一栏自己确认。

1. **构建镜像**：没跑过 `docker compose build`，所以不保证镜像一定构建成功。
   - 到 NAS 上确认：`docker compose build` 正常结束且无报错；
     `docker compose images` 能看到 `notify-hub`。
   - 已知风险：`Dockerfile` 里的 uv 镜像已固定版本号（`ghcr.io/astral-sh/uv:0.12.21`），
     构建可复现；但它终究要从外网拉这个镜像，NAS 若拉不动，可改用 `pip install uv`
     或换一个能拉动的来源。
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
- 全部单元与集成测试继续通过（2026-10-12 复核：61 个，全绿）。

## 故障排查

- `docker compose` 报 `NOTIFY_TOKEN 未设置`：`.env` 没填或没从 `.env.example` 复制。
- 容器起不来：`docker compose logs` 看是不是端口 8080/8081 被占用。
- 健康检查 `unhealthy`：内网端口没起来，看日志。
- 手机收不到：`GET /messages` 看该消息的 `last_error`。Apprise 地址写错会记成
  “通道地址无效”，网络问题会记成连接错误。
- **一直 401**：先怀疑 `.env` 存成了 CRLF（见步骤 3），令牌末尾多了个 `\r`；再确认
  调用方用的令牌和 `.env` 里的一致。
- **消息状态是“失败”，`last_error` 是连接错误**：容器出不了网，按步骤 6 的连通性
  自检查。
- **只有自建 ntfy 收不到，其它通道正常**：ntfy 和本服务在同一台机器时，容器回不到
  宿主机 LAN IP。见步骤 2 里的说明：ntfy 绑 `0.0.0.0`，地址用 `host.docker.internal`。
- **Bark 偶尔失败、重试后才成功**：Bark 走公网，网络抖动时会失败。重试机制会兜住
  （看该通道 `channel_results` 里的 `attempts`，大于 1 就是靠重试救回来的）。
  偶尔一次不用管，频繁出现就要查那台机器的网络或代理了。
- **pi 连不上 MCP**：依次确认穿透映射的是 8080、路径是 `/mcp`、跑 pi 那台电脑上的
  `NOTIFY_TOKEN` 已设好、且已经 `/reload`。
- **服务没反应、`docker compose ps` 显示 unhealthy**：看 `docker compose logs`，
  多半是 8081 没起来或 `/data` 目录不可写。
