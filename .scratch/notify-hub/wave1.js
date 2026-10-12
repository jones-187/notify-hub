// 第一波：技术探查 + 工单 01
// 规格见 /home/jones/projects/notify-hub/.scratch/notify-hub/spec.md
// 工单见 /home/jones/projects/notify-hub/.scratch/notify-hub/issues/

const NOTES = "/home/jones/projects/notify-hub-notes/python-sdk-and-apprise.md";

const scoutTask = [
  "你是技术探查员。目标：把后面的实现子代理需要照做的技术事实查清楚。",
  "",
  "项目根目录（读文件用）：/home/jones/projects/notify-hub",
  "先读这两个：.scratch/notify-hub/spec.md 和 .scratch/notify-hub/issues/01-internal-notify-endpoint.md",
  "",
  "做法：在 /tmp/notify-probe 建一个临时虚拟环境（本机有 uv），装 `mcp`（官方 Python SDK）和 `apprise`，直接读装出来的源码与包内文档。不要把任何东西装进项目仓库。",
  "",
  "必须回答下面 5 条，每条都要给可核验的依据（文件路径或官方链接）：",
  "1) 用官方 Python SDK 建一个 streamable HTTP 的 MCP 服务，最小可运行代码长什么样：工具怎么定义、怎么启动、端点路径是什么。",
  "2) 怎么让这个 MCP 服务和一个普通 HTTP 应用跑在同一个进程、监听两个不同端口（一个端口只挂 MCP，另一个端口挂 /notify 和 /healthz）。给出可用的写法。",
  "3) 怎么校验请求头里的 bearer 令牌，写在哪一层最省事；令牌不对时怎么返回干净的 401。给出可用的写法。",
  "4) Apprise 库：怎么从 URL 建实例；怎么逐个通道发送并拿到每个通道各自的成功或失败结果（`apobj.servers` 的正确用法）；异常和超时表现成什么样。",
  "5) 上面用到的确切版本号，以及官方 SDK v1 与 v2 之间会踩到的差异。",
  "",
  "规矩：只写你能核实的。核不到就写「未核到」。不要猜。笔记用简体中文，代码片段要能直接跑。"
].join("\n");

const t01Task = [
  "你在实现一个工单。先按顺序读这四份材料（都在 /home/jones/projects/notify-hub 里，但你只能在你的工作树里改代码）：",
  "1) .scratch/notify-hub/spec.md（规格，重点看「Implementation Decisions」与「Testing Decisions」）",
  "2) .scratch/notify-hub/issues/01-internal-notify-endpoint.md（你的工单，验收条件是硬要求）",
  "3) GLOSSARY.md（术语，必须用里面的词）",
  "4) docs/adr/（已定决策，不要违背）",
  "另外读技术探查笔记：/home/jones/projects/notify-hub-notes/python-sdk-and-apprise.md（里面有官方 SDK 与 Apprise 的用法与版本）。",
  "",
  "范围：只做工单 01。不要做 MCP 端点、不要做排期、不要做 Docker。多做的部分会被退回。",
  "你所在的工作树已经基于集成分支 feat/notify-hub，先自己确认一遍（git log、git status），不是就切过去。",
  "按 TDD 做：读 /home/jones/.agents/skills/tdd/SKILL.md 并照它走，一次一个红-绿小步。先写会失败的测试，再写实现。",
  "测试里必须用假的转发出口，绝不真的发通知到手机。",
  "语言：Python 3.11+。依赖用 uv 管理（uv 已安装，本机没有 Docker）。",
  "",
  "完成标准：工单 01 的每条验收条件都有对应的自动化测试，测试全绿。",
  "收尾：把集成分支 feat/notify-hub 的最新提交合并进你的分支，跑一次完整测试，然后用 Conventional Commits 提交（描述用简体中文）。",
  "报告用简体中文、短句，写清：做了什么、怎么验证的（贴命令与结果）、还剩什么风险或没做的事。"
].join("\n");

const scout = await runs.run("scout", { agent: "scout", output: NOTES, task: scoutTask });
const t01 = await runs.run("t01", {
  agent: "worker",
  cwd: "/home/jones/projects/notify-hub-wt-01",
  output: "/home/jones/projects/notify-hub-notes/t01-report.md",
  task: t01Task
});

return {
  scoutRunId: scout.runId,
  t01RunId: t01.runId,
  scoutNotes: NOTES,
  scoutOutput: scout.output,
  t01Output: t01.output
};
