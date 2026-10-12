// 第三波：工单 03（MCP 入口与两个工具）与工单 06（保留清理）并行
// 规格：/home/jones/projects/notify-hub/.scratch/notify-hub/spec.md
// 进度：工单 01、02、05 已合入集成分支 feat/notify-hub（提交 795c736）

const preamble = (ticketFile) => [
  "你在实现一个工单。前面有子代理只输出一句计划就结束、一行代码没改，所以记住：先动手，不要先讲计划；没有提交就不算完成。",
  "",
  "先按顺序读这几份材料（都在 /home/jones/projects/notify-hub 里，但你只能在你的工作树里改代码）：",
  "1) .scratch/notify-hub/spec.md（规格，重点看 Implementation Decisions 与 Testing Decisions）",
  "2) " + ticketFile + "（你的工单，验收条件是硬要求）",
  "3) GLOSSARY.md（术语，必须用里面的词）",
  "4) docs/adr/（已定决策，不要违背）",
  "5) /home/jones/projects/notify-hub-notes/python-sdk-and-apprise.md（技术探查笔记，里面的代码片段在本机实测跑通过。注意：mcp 是 2.x，FastMCP 已改名 MCPServer；apprise 是 2.x，apobj.servers 已不存在。网上多数例子是旧版，不要照抄）",
  "6) 已有代码：src/notify_hub/app.py（内网入口 ASGI 应用与令牌校验）、forwarder.py（转发层与重试）、store.py（SQLite 存储与可注入时钟）、scheduler.py（后台循环）；测试在 tests/（现在 17 个全绿）。",
  "",
  "规矩：",
  "- 只做你的工单。多做的部分会被退回。",
  "- 你所在的工作树已经基于集成分支 feat/notify-hub，先自己确认（git log、git status）。",
  "- 按 TDD 做：读 /home/jones/.agents/skills/tdd/SKILL.md 并照它走，一次一个红-绿小步。",
  "- 测试里绝不真的发通知到手机，也绝不真等几十秒。",
  "- 现有的 17 个测试必须继续通过。",
  "- Python 3.11+，依赖用 uv 管理。",
  "- 收尾：把集成分支 feat/notify-hub 的最新提交合并进你的分支，跑一次完整测试（uv run pytest），再用 Conventional Commits 提交（描述用简体中文）。",
  "- 报告用简体中文、短句：做了什么、怎么验证的（贴命令与结果）、还剩什么风险。",
  ""
].join("\n");

const t03 = [
  "你的工单：03 MCP 入口与两个工具。做完之后，pi 能通过远程 MCP 连上服务；AI 能立刻发一条消息，也能排一条带绝对时间的消息。",
  "",
  "要点：",
  "- 一个进程两套监听：公网端口只挂 MCP（路径 /mcp），内网端口挂现有的 /notify、/healthz，再加上只读的 /messages。公网端口要返回 404 给 /notify，内网端口不挂 MCP。这条边界要有测试证明。",
  "- MCP 用官方 Python SDK（mcp 2.x，类名是 MCPServer，不是 FastMCP）。笔记里有实测跑通的写法。",
  "- MCP 端口的令牌用 SDK 自带的 token_verifier；内网端口用已有的 BearerAuthMiddleware。令牌只从环境变量读。",
  "- 工具一 `send_message`：标题、正文，立刻发，返回消息编号。",
  "- 工具二 `schedule_message`：标题、正文、发送时间（带时区的 RFC3339，例如 2026-10-13T08:00:00+08:00），写进排期，返回消息编号。时间落在过去要返回明确的错误，不要静默改成“现在发”。",
  "- 两个工具的说明文字要写清参数含义与时间格式，让 AI 不用猜。",
  "- 时间对外是带时区的 RFC3339，库里是 UTC：转换要写清楚，时区固定 Asia/Shanghai。",
  "- 要有一个启动入口，一次把两个端口和后台排期循环都起起来。",
  "- 测试里注意笔记里那条：用 httpx 的 ASGITransport 在进程内打 MCP 应用时，必须自己进入 Starlette 的 lifespan，否则会报 “Task group is not initialized”。",
  "- 不要做工单 04 的工具（list_messages、cancel_message），那是下一张工单。",
  "",
  "报告请写：两个端口怎么分开的、令牌怎么校验、怎么证明公网端口进不了内网接口。"
].join("\n");

const t06 = [
  "你的工单：06 保留清理。做完之后，数据库文件占用有上限，但排队中的消息不会被误删。",
  "",
  "要点：",
  "- 上限默认：数据库文件超过 10 MB 时，删最旧的“已发”和“已取消”消息，降到 8 MB 以下。",
  "- 阈值必须可配置，测试用很小的阈值（例如几十 KB），不要为了测试去造 10 MB 数据。",
  "- 未发的消息永不删除：要有一条测试造一条很久以前的未发消息，跑完清理后它仍然在。",
  "- 只按“最旧优先”删除，先删已发和已取消的；不要把未发的当候选。",
  "- 技术点：SQLite 删行以后文件不会自己变小。要真的回收空间（VACUUM 或等价做法），否则文件大小不会降到阈值以下。测试要断言清理后文件大小确实降下来了。",
  "- 清理要被后台循环定期调用（间隔可配置），不要只在启动时跑一次。",
  "- 另一个工单（03 MCP 入口）同时在改 app.py 和新增入口文件。你的改动尽量只碰 store.py 和 scheduler.py，别去动 app.py，减少冲突。",
  "",
  "报告请写：清理怎么触发、怎么回收空间、怎么证明未发消息没被删。"
].join("\n");

const [r03, r06] = await runs.all([
  {
    key: "t03",
    agent: "worker",
    cwd: "/home/jones/projects/notify-hub-wt-03",
    output: "/home/jones/projects/notify-hub-notes/t03-report.md",
    task: preamble(".scratch/notify-hub/issues/03-mcp-ingress-and-two-tools.md") + t03
  },
  {
    key: "t06",
    agent: "worker",
    cwd: "/home/jones/projects/notify-hub-wt-06",
    output: "/home/jones/projects/notify-hub-notes/t06-report.md",
    task: preamble(".scratch/notify-hub/issues/06-retention-cleanup.md") + t06
  }
]);

return {
  t03RunId: r03.runId,
  t06RunId: r06.runId,
  t03: r03.output,
  t06: r06.output
};
