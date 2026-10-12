// 代码审查：两个轴并行（Standards / Spec），各自写报告
// 固定点：master（分支起点）。集成分支：feat/notify-hub（提交 d220538）

const SMELLS = [
  "以下是固定的“坏味道”基线（Fowler《重构》第 3 章）。每条都是判断题，不是硬性违规。仓库里若有明文规范，明文规范优先。工具已经能查的（格式、类型、lint）跳过。",
  "- Mysterious Name：名字没说明它做什么或存什么。→ 改名；想不出诚实名字说明设计本身含糊。",
  "- Duplicated Code：同一段逻辑形状出现在多处。→ 抽出共享形状，两处都调它。",
  "- Feature Envy：一个方法访问别人的数据比访问自己的还多。→ 把方法搬到它羡慕的数据那边。",
  "- Data Clumps：同几个字段或参数总是结伴出现。→ 打包成一个类型传它。",
  "- Primitive Obsession：用基本类型或字符串代替一个本该有自己类型的领域概念。→ 给这个概念一个小类型。",
  "- Repeated Switches：同一个类型上的 switch 或 if 级联反复出现。→ 换成多态，或抽出两边共用的映射表。",
  "- Shotgun Surgery：一个逻辑改动逼你散着改很多文件。→ 把一起变的东西收进一个模块。",
  "- Divergent Change：一个文件因几种互不相关的原因被改。→ 拆开，让每个模块只因一个原因变。",
  "- Speculative Generality：为规格里不存在的需要加的抽象、参数、钩子。→ 删掉，等真需要再加。",
  "- Message Chains：a.b().c().d() 这种长链导航。→ 在第一个对象上包一个方法。",
  "- Middle Man：一个类或函数几乎只是转调。→ 删掉它，直接调真正的目标。",
  "- Refused Bequest：子类或实现者忽略或覆盖了它继承来的大部分东西。→ 去掉继承，改用组合。"
].join("\n");

const common = [
  "项目：/home/jones/projects/notify-hub（分支 feat/notify-hub，提交 d220538）。",
  "固定点是 master。差异命令：git diff master...feat/notify-hub",
  "提交清单：git log master..feat/notify-hub --oneline",
  "这是一个自建的提醒与通知服务（Python 3.11+，Starlette + 官方 MCP Python SDK + Apprise + SQLite）。",
  "术语表 GLOSSARY.md 里的词是硬约定：消息、排期、排期层、通道、转发层、入口。已定决策在 docs/adr/，代码不得违背。",
  "代码里的注释和文档用简体中文。",
  "只读：不要修改任何文件，只写你自己的报告文件。",
  ""
].join("\n");

const standardsTask = [
  common,
  "你的轴：Standards（代码是否符合本仓库明文的写法规范）。",
  "",
  "先找本仓库里所有写“代码该怎么写”的文件：CONTRIBUTING.md、CODING_STANDARDS.md、README.md、docs/ 下的文档、.scratch/notify-hub/spec.md 里关于写法与测试的部分。找到的都要读。仓库里没有 CONTRIBUTING.md 或 CODING_STANDARDS.md，这一点在报告里说明。",
  "",
  SMELLS,
  "",
  "报告要求：按文件或代码块给出：",
  "(a) 每一处违反明文规范的地方：引用规范（文件 + 那条规则）；",
  "(b) 你发现的坏味道：写出名字并引用那段代码。",
  "要区分硬违规与判断题：违反明文规范可以是硬违规，坏味道永远是判断题，明文规范优先于坏味道。",
  "重点看这些地方：令牌校验、两端口的边界、重试与去重语义、SQLite 的清理与 VACUUM（会不会阻塞事件循环）、可注入时钟的用法、测试是否只测外部行为。",
  "不超过 800 字。写成报告，用简体中文。"
].join("\n");

const specTask = [
  common,
  "你的轴：Spec（代码是否忠实实现了规格）。",
  "",
  "规格来源（都要读）：",
  "1) .scratch/notify-hub/spec.md",
  "2) .scratch/notify-hub/issues/ 下的 8 张工单（01 到 08）",
  "3) docs/adr/0001 到 0004（已定决策）",
  "4) GLOSSARY.md（术语）",
  "",
  "报告要求：",
  "(a) 规格要求了、但实现缺失或只做了一半的；",
  "(b) 规格没要求、但代码里做了的（范围扩张）；",
  "(c) 看起来实现了、但实现方式可疑或与规格不符的。",
  "每条都要引用规格或工单的原句作为依据。",
  "特别检查这几条已被确认的结果：数据库文件超过 10 MB 时应降到 8 MB 以下（注意清理候选只包含“已发”和“已取消”，想想这条能不能真的成立）；对公网只暴露 MCP 一个端口；重试只针对失败的通道；未发的消息永不删除；时间落在过去要报错而不是改成现在发；时区固定 Asia/Shanghai。",
  "工单 08 是人工工单（要在 NAS 上做），不算缺失。",
  "不超过 800 字。写成报告，用简体中文。"
].join("\n");

const [std, spec] = await runs.all([
  {
    key: "standards",
    agent: "reviewer",
    cwd: "/home/jones/projects/notify-hub",
    output: "/home/jones/projects/notify-hub-notes/review-standards.md",
    task: standardsTask
  },
  {
    key: "spec",
    agent: "reviewer",
    cwd: "/home/jones/projects/notify-hub",
    output: "/home/jones/projects/notify-hub-notes/review-spec.md",
    task: specTask
  }
]);

return { standards: std.output, spec: spec.output };
