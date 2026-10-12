// 第四波：工单 04（列出与取消）与工单 07（容器化与部署步骤）并行
// 规格：/home/jones/projects/notify-hub/.scratch/notify-hub/spec.md
// 进度：工单 01、02、03、05、06 已合入集成分支 feat/notify-hub（提交 cc17868，39 个测试全绿）

const preamble = (ticketFile) => [
  "你在实现一个工单。记住：先动手，不要先讲计划；没有提交就不算完成。",
  "",
  "先按顺序读这几份材料（都在 /home/jones/projects/notify-hub 里，但你只能在你的工作树里改代码）：",
  "1) .scratch/notify-hub/spec.md（规格，重点看 Implementation Decisions 与 Testing Decisions）",
  "2) " + ticketFile + "（你的工单，验收条件是硬要求）",
  "3) GLOSSARY.md（术语，必须用里面的词）",
  "4) docs/adr/（已定决策，不要违背）",
  "5) /home/jones/projects/notify-hub-notes/python-sdk-and-apprise.md（技术探查笔记，代码片段在本机实测跑通过。mcp 是 2.x、apprise 是 2.x，网上多数例子是旧版）",
  "6) 已有代码：src/notify_hub/ 下的 app.py（内网入口）、mcp_app.py（MCP 应用与令牌）、main.py（两个端口的启动入口）、messaging.py（立刻发送）、forwarder.py（转发与重试）、store.py（存储、时钟、清理）、scheduler.py（后台循环）；测试在 tests/（现在 39 个全绿）。",
  "",
  "规矩：",
  "- 只做你的工单。多做的部分会被退回。",
  "- 你所在的工作树已经基于集成分支 feat/notify-hub，先自己确认（git log、git status）。",
  "- 按 TDD 做：读 /home/jones/.agents/skills/tdd/SKILL.md 并照它走，一次一个红-绿小步。",
  "- 测试里绝不真的发通知到手机，也绝不真等几十秒。",
  "- 现有的 39 个测试必须继续通过。",
  "- Python 3.11+，依赖用 uv 管理。本机没有 Docker。",
  "- 收尾：把集成分支 feat/notify-hub 的最新提交合并进你的分支，跑一次完整测试（uv run pytest），再用 Conventional Commits 提交（描述用简体中文）。",
  "- 报告用简体中文、短句：做了什么、怎么验证的（贴命令与结果）、还剩什么风险。",
  ""
].join("\n");

const t04 = [
  "你的工单：04 列出与取消。做完之后，AI 能查已经排了什么，也能把排错的那条收回。",
  "",
  "要点：",
  "- 工具 `list_messages`：能列出未发的消息，也能看最近已发的消息；每条要有编号、发送时间、标题、状态；条数要有上限，别一次吐几千条。",
  "- 工具 `cancel_message`：取消一条未发的消息，返回是否成功。",
  "- 取消一个不存在的编号，或取消一条已经发出去的、已经取消的、失败的消息，都要返回明确的错误，不许静默成功。",
  "- 报错沿用工单 03 的做法：可预期的错误用 SDK 的 ToolError，把原因原文回给调用方。",
  "- 时间对外按 Asia/Shanghai（+08:00）显示，库里仍是 UTC。复用 store.py 里已有的格式化函数，不要另写一套。",
  "- 取消是改状态（状态值“已取消”已经存在），不是删行：要有一条测试证明取消后这条消息还在，且状态变成已取消。",
  "- 另一个工单（07 容器化）同时在做 Docker 相关文件。请你尽量只碰 mcp_app.py、store.py、以及必要的测试，不要动 Dockerfile、compose 或其他新文件。",
  "",
  "报告请写：两个工具的参数与返回、取消的语义、怎么证明不能取消已发的消息。"
].join("\n");

const t07 = [
  "你的工单：07 容器化与部署步骤。做完之后，你拿到一份照做就能在 Windows NAS 上跑起来的步骤文档。注意：本机没有 Docker，你无法在这里构建镜像，所以你要把不能验证的部分明确写出来，不要假装验证过。",
  "",
  "要点：",
  "- 一个 Dockerfile + 一个 compose 文件。基础镜像用 python:3.12-slim 之类；依赖用 uv（仓库里已有 pyproject.toml 与 uv.lock，要利用锁文件，别另起一套依赖管理）。",
  "- 两个端口分别映射：MCP 端口（默认 8080，对公网）与内网端口（默认 8081）。",
  "- 数据目录挂载到宿主机，数据库文件放在挂载卷里（NOTIFY_DB 指向它），容器重建后数据还在。",
  "- 令牌只从环境变量 NOTIFY_TOKEN 传入；仓库里给出 .env.example，绝不写真令牌；.env 要进 .gitignore。",
  "- compose 里可以给内网端口加健康检查（/healthz 免令牌），但不要把内网端口发布到公网。",
  "- 写一份部署步骤文档（放 docs/deploy.md）：生成令牌、准备通道地址、填通道表、起容器、看日志、备份数据库文件、升级镜像的步骤。通道地址怎么填要写清楚：Apprise 的 URL 形式，Bark 是 bark://{host}/{device_key}，ntfy 是 ntfy://{user}:{password}@{host}:{port}/{topic}。",
   "- 明确标出哪些步骤你在本机验证不了（构建镜像、起容器、真发通知），以及到了 NAS 上怎么检查成不成功。",
  "- 尽量只新增文件（Dockerfile、compose、.env.example、docs/deploy.md、.dockerignore），不要改 Python 代码；万不得已要改，只做加法。另一个工单（04）同时在改 mcp_app.py 与 store.py。",
  "",
  "报告请写：镜像怎么构建、两个端口怎么映射、数据与令牌怎么处理、你在本机验证了什么、哪些只能到 NAS 上验证。"
].join("\n");

const [r04, r07] = await runs.all([
  {
    key: "t04",
    agent: "worker",
    cwd: "/home/jones/projects/notify-hub-wt-04",
    output: "/home/jones/projects/notify-hub-notes/t04-report.md",
    task: preamble(".scratch/notify-hub/issues/04-list-and-cancel.md") + t04
  },
  {
    key: "t07",
    agent: "worker",
    cwd: "/home/jones/projects/notify-hub-wt-07",
    output: "/home/jones/projects/notify-hub-notes/t07-report.md",
    task: preamble(".scratch/notify-hub/issues/07-container-and-deploy-steps.md") + t07
  }
]);

return {
  t04RunId: r04.runId,
  t07RunId: r07.runId,
  t04: r04.output,
  t07: r07.output
};
