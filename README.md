# ai-native-garden · AI 时代的代码库园艺

> 能用代码硬性拦截的，绝不靠人记；用测试把关，不在文档里堆字；内循环没修好之前，不要急着自动化。

这是一个给 AI 编程代理（Cursor、Claude Code、Codex 等）用的 **Agent Skill**。它通过 Gemini Neon 提炼，素材来自土豆姐 Lauren Tan（[@poteto](https://github.com/poteto)）在 **AI Engineer CODE Summit 2026** 上 17 分钟的演讲 **《All Code Is Slop (Except Mine)》**，再结合生产项目里“零容错”的工程实践，整理成一套能直接落地的工作流。在我看来，这是目前 AI 工程化领域含金量很高的一份实战复盘。

一句话说它能干嘛：**让 AI 写出来的代码越来越可信，不必靠人逐行盯 diff。**

---

## 解决什么问题

AI 写代码几乎不花钱以后，瓶颈就从“写”转到了“验证和维护”。常见的坑有三个：

- **规则写在 `AGENTS.md` 里没人听**：上下文一长，自然语言规则的遵从率就会掉下去。
- **代码库本身才是 Agent 最信的上下文**：文档说“别用 X”，仓库里却到处是 X，Agent 一定照着 X 写。
- **人工 Review 追不上生成速度**：把人卡在看 diff 上，最后只会陷入低信任的死循环。

这个 Skill 的思路是：**把软规则一层层升级成硬约束**，让错误写不出来、编译不过、测试过不去。

## 核心方法：信任金字塔

有问题要修时，按杠杆从高到低选手段，不准跳级直接加文档：

| 层级 | 手段 | 效果 |
|---|---|---|
| L1 | 架构边界与 API 设计 | 错误**写不出来**（收窄导出面、只留一个安全封装、单向依赖） |
| L2 | Lint、严格类型、依赖图规则 | 错误**编译不过**（报错文案直接告诉 Agent 该改用什么） |
| L3 | 确定性验证闭环与不变量测试 | 错误**测试过不去**（统一门禁、零 skip、Golden Fixture、E2E） |
| L4 | 极简规则文档 | 只兜底前三层表达不了的流程；一旦有代码拦截，就删掉对应文字 |

铁律：**同一类错误出现第二次，至少升级到 L2 或 L3。**

## 它能帮你做什么

1. **给仓库做一次量化体检**：自带零依赖脚本 `scripts/audit-slop.py`，几秒钟扫出：
   - **纸面门禁（Paper Linters）**：配置躺在仓库里但 CI/门禁从不调用（如无人执行的 `.golangci.yml`）、未清零的 Lint 棘轮（Ratchet）、遗漏核心业务层的 `-race` 检测
   - **上下文健康度**：巨型文件（默认超过 800 行）、扁平高密度目录、注释占比、孤儿组件
   - **全栈逃生舱与风险模式**：TS 逃生舱（`as any` / `as never` / `@ts-ignore` / `as unknown as`）、Go `_ =` 静默丢错、硬编码 `z-index >= 50` 魔数、`watch` / `useEffect` 副作用热点、业务/接口层裸 SQL、嵌套 `lines.filter`、`TODO / FIXME / HACK` 残留
2. **把反复出现的错误变成硬规则**：用一棵纠错升级决策树来定级，并提供高频隐藏 Bug → L2/L3 机器门禁速查表，写清楚 **Error-Driven** 报错文案让 Agent 看一次就能改对。
3. **治理历史债，直到棘轮彻底清零**：新代码零容忍，旧文件锁定基线只降不升（Ratchet），并在抽离完成后彻底清空棘轮为 `{}`。
4. **给 Go + Vue 3 / TypeScript + MySQL + Playwright 栈提供现成模板**：
   - 前端 zero-dep AST 架构脚本 `lint-arch.mjs`（禁逃生舱/`fetch`/裸异步组件/深色 `--ink` 失配/数字 `z-index`/未净化 `v-html`/无 `registerDirtyCheck` 离开守卫/孤儿组件/巨型 scoped CSS 复用）与异步分包 gzip 预算守卫
   - 后端 Go 原生 AST 单测 `archguard`（零配置随 `go test` 必跑：扫描 `internal/`+`cmd/`、`depguard`、按查询计数 `sqlclosecheck`/`rowserrcheck`、`http-body-close`、`no-unchecked-scan-or-unmarshal`、`no-risky-discard` 与 DDL Parity 校验）
   - 前后端同一算法的 Golden Parity 测试、DTO 反射/代码生成漂移门禁
   - 统一门禁入口（含工作区未提交/未跟踪迁移检验、动态包发现、全仓 `-race` 与一键隔离 E2E）
5. **给 `AGENTS.md` 瘦身**：附一份检查清单，目标是 60 秒内能读完、全文不自相矛盾。

## 什么时候用

- 想评估一个仓库对 AI 是否友好，或者要重构它
- 想把 `AGENTS.md` 里的“软规定”升级成 Lint、类型、架构或 CI 硬约束
- 要清理巨型文件和反模式
- 同一类 AI 错误反复出现
- 要搭一套确定性的自动化验证闭环

## 安装

把 `ai-native-garden` 目录放进你的代理的 skills 目录即可，例如：

```sh
git clone https://github.com/luvio-arlan/ai-native-garden.git
# Cursor
cp -r ai-native-garden ~/.cursor/skills/
# Claude Code
cp -r ai-native-garden ~/.claude/skills/
```

之后对 Agent 说一句“用 ai-native-garden 给这个仓库做体检”就行。

只想用体检脚本的话（Python 3.8+，不需要装任何依赖）：

```sh
python3 scripts/audit-slop.py <repo-root>          # 默认阈值 800 行
python3 scripts/audit-slop.py <repo-root> --limit 600
```

脚本只读不写，输出是 Markdown 报告。

## 工作流（四步）

1. **体检**：先拿到证据，不凭感觉动手重构。
2. **升级**：对照手册，把发现的坏模式升级成 L1、L2 或 L3 守卫，不只修眼前这一处。
3. **落地**：按 ROI 推进。P0 是统一门禁和 Linter，P1 是契约单一真源和 E2E，P2 是持续修剪。
4. **验收**：故意写一条违规代码，确认新规则会报错、文案清楚，然后还原；再把唯一门禁跑到全绿，最后检查 `git status` 是干净的。

## 目录结构

```text
ai-native-garden/
├── SKILL.md                              # Skill 入口：信任金字塔、四步工作流、工程红线
├── scripts/
│   └── audit-slop.py                     # 零依赖的仓库体检脚本
└── references/
    ├── trust-pyramid-playbook.md         # 演讲要点、纠错决策树、Error-Driven Lint、棘轮法、AGENTS.md 瘦身
    └── go-vue-guardrails.md              # Go + Vue/TS 硬约束模板
```

## 致谢

方法论来自 Lauren Tan（[@poteto](https://github.com/poteto)）的演讲《All Code Is Slop (Except Mine)》（AI Engineer CODE Summit 2026）。本仓库是个人学习整理和工程化落地，不代表原作者观点；如有理解偏差，欢迎提 Issue 指正。

## 交流

欢迎提 Issue、PR，或者直接来交流 AI 工程化实践。

## License

[MIT](./LICENSE)
