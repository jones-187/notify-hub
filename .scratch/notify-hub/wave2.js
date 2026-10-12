// 第二波：工单 02（排期表与到点发送）与工单 05（失败重试与错误记录）并行
// 规格：/home/jones/projects/notify-hub/.scratch/notify-hub/spec.md
// 进度：工单 01 已合入集成分支 feat/notify-hub（提交 9cfc7a6）

const preamble = (ticketFile) => [
  "你在实现一个工单。先按顺序读这几份材料（都在 /home/jones/projects/notify-hub 里，但你只能在你的工作树里改代码）：",
  "1) .scratch/notify-hub/spec.md（规格，重点看「Implementation Decisions」与「Testing Decisions」）",
  "2) " + ticketFile + "（你的工单，验收条件是硬要求）",
  "3) GLOSSARY.md（术语，必须用里面的词）",
  "4) docs/adr/（已定决策，不要违背）",
  "5) /home/jones/projects/notify-hub-notes/python-sdk-and-apprise.md（技术探查笔记：官方 SDK 与 Apprise 的确切版本与用法。注意 mcp 是 2.x，apprise 是 2.x，网上多数例子是旧版本，不要照抄）",
  "6) 已完成的工作：git log --oneline 看提交；工单 01 的代码在 src/notify_hub/（app.py 内网入口、forwarder.py 转发层、store.py 存储、tests/ 测试）。",
  "",
  "规矩：",
  "- 只做你的工单。多做的部分会被退回。",
  "- 你所在的工作树已经基于集成分支 feat/notify-hub，先自己确认（git log、git status）。",
  "- 按 TDD 做：读 /home/jones/.agents/skills/tdd/SKILL.md 并照它走，一次一个红-绿小步。",
  "- 测试里绝不真的发通知到手机，也不真的等待几十秒。",
  "- Python 3.11+，依赖用 uv 管理。",
  "- 收尾：把集成分支 feat/notify-hub 的最新提交合并进你的分支，跑一次完整测试（uv run pytest），再用 Conventional Commits 提交（描述用简体中文）。",
  "- 报告用简体中文、短句：做了什么、怎么验证的（贴命令与结果）、还剩什么风险。",
  ""
].join("\n");

const t02 = [
  "你的工单：02 排期表与到点发送。做完之后，写一条未来时间的消息能在到点时自动发出，服务重启也不丢。",
  "",
  "要点：",
  "- 消息表要能表达：编号、标题、正文、通道集合、发送时间、状态（未发 / 已发 / 失败 / 已取消）、创建时间、尝试次数、最后错误。现在 messages 表只有少量列，需要按规格补齐。",
  "- 后台循环每秒检查一次到期消息，一次最多取 50 条。发送复用已有的转发层出口。",
  "- 时钟必须可替换：测试把「现在」设到某一刻，再推进几秒，断言消息发出，不许真等。",
  "- 重启后未发的消息按原定时间继续发出。要有一条测试证明这件事（例如新建一个 Store 实例连同一个数据库文件，再推进时钟）。",
  "- 时间在库里存 UTC，对外用带时区的 RFC3339 字符串（规格里有）。本工单只要求存储与循环，MCP 工具是工单 03 的事。",
  "- 另一个工单（05 失败重试）同时在改 store.py。你的改动尽量只做加法：不要重命名或重排已有列，新列加在表末尾。",
  "",
  "报告请写：改了哪些表与列、循环怎么起停、重启恢复是怎么验证的。"
].join("\n");

const t05 = [
  "你的工单：05 失败重试与错误记录。做完之后，某个通道临时出问题时消息不会丢，而成功的通道不会收到重复消息。",
  "",
  "要点：",
  "- 一条消息的多个通道分别发送、分别记录结果。现在 forwarder.deliver 已经逐通道发送并返回每个通道的结果，你要在此基础上做重试。",
  "- 只有失败的通道重试，最多 3 次，间隔递增。",
  "- 重试的等待时间必须能被测试替换：测试不许真等几十秒。",
  "- 成功的通道绝不重发。要有一条测试用假出口统计每个通道被调用的次数来证明这件事。",
  "- 重试仍失败时，失败原因写进消息记录（attempts 与 last_error 之类的列），并且能通过存储读出来。",
  "- 某个通道失败不影响其它通道收到消息。",
  "- 另一个工单（02 排期表）同时在改 store.py 的表结构。你的改动尽量只做加法：不要重命名或重排已有列，新列加在表末尾。",
  "",
  "报告请写：重试放在哪一层、间隔怎么定、怎么证明没有重复发送。"
].join("\n");

const [r02, r05] = await runs.all([
  {
    key: "t02",
    agent: "worker",
    cwd: "/home/jones/projects/notify-hub-wt-02",
    output: "/home/jones/projects/notify-hub-notes/t02-report.md",
    task: preamble(".scratch/notify-hub/issues/02-schedule-store-and-due-sending.md") + t02
  },
  {
    key: "t05",
    agent: "worker",
    cwd: "/home/jones/projects/notify-hub-wt-05",
    output: "/home/jones/projects/notify-hub-notes/t05-report.md",
    task: preamble(".scratch/notify-hub/issues/05-delivery-retry-and-errors.md") + t05
  }
]);

return {
  t02RunId: r02.runId,
  t05RunId: r05.runId,
  t02: r02.output,
  t05: r05.output
};
