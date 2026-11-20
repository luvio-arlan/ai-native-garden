# Go + Vue 3 / TypeScript 硬约束落地模板

面向 Go 后端 + Vue 3 / TypeScript 前端 + MySQL + Playwright 技术栈的高 ROI 确定性护栏清单，可按需剪裁复制到目标项目。

---

## 1. 前端硬约束（推荐 `oxlint` 极速扫描或 ESLint Flat Config）

### 1.1 关键禁止规则清单

| 保护目标 | 规则实现 | Error-Driven 报错方向 |
|---|---|---|
| 禁用易出错原生异步加载 | 禁 `defineAsyncComponent`（仅 `versionGuard.ts` 豁免） | 提示改用 `safeAsyncComponent` 防发版旧 chunk 404 自愈重刷 |
| 禁止绕过统一 API 客户端 | 禁业务代码直接调用 `fetch(`（仅底层 `api/client.ts`、`api/ai.ts` 豁免） | 提示通过 `@/api` 发起请求以保证鉴权/超时/401 处理 |
| 禁止视图间网状耦合 | 禁 `src/views/<A>/*` 导入 `../<B>/*` | 提示将共享逻辑下沉至 `src/shared/` 或 `src/ui/` |
| 禁止全类 TS 逃生舱 | 禁 `as any`、`as never`、`as unknown as T`、`@ts-ignore`、`@ts-expect-error` | 提示补齐泛型约束或类型守卫 |
| 禁止 `z-index` 魔数导致遮罩反压 | 禁 CSS `z-index >= 50`（仅 `tokens.css` 豁免）及数字 `:z-index` prop | 提示使用语义令牌 `--z-modal` / `--z-modal-nested` / `--z-popover` |
| 禁止深色模式下 `--ink` 前景色失配 | 检测同规则块 `background: var(--ink)` + `#fff`/`white`/`var(--bg)`/`var(--text-on-accent)` | 提示改用 `color: var(--text-on-ink)` |
| 禁止未净化 `v-html` 与漏守卫 `beforeunload` | 检查 `v-html` 必经 sanitizer；检查 `beforeunload` 必配 `registerDirtyCheck` | 提示 XSS 净化与版本热更新前脏数据保护 |
| 防范 O(N²) 与巨型包体积倍增 | 禁循环内 `lines.filter` 或 `new Map/Set([...])`、禁子组件共享巨型 scoped CSS、清零孤儿 `.vue` 与分包 gzip 预算门禁 | 提示 `indexLinesByOrg`、原地写入、`safeAsyncComponent` 拆分与删废文件 |
| 控制副作用与文件膨胀 | 全仓清零棘轮（`{}`）：单文件 ≤ 800 行、≤ 4 `watch`、注释 ≤ 5% | 提示拆 composable / subcomponent 与用 `computed`/事件替代 `watch` |

### 1.2 `tsconfig.json` 推荐严格项

```json
{
  "compilerOptions": {
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noImplicitReturns": true,
    "noUncheckedIndexedAccess": true
  }
}
```

---

## 2. 后端硬约束（Go 原生 `archguard` AST Test 优先，拒绝无人调用的纸面 `.golangci.yml`）

与其在仓库放一份 CI 从不运行的 `.golangci.yml`（纸面门禁），不如将核心约束写进 `server/internal/archguard/*_test.go`——**随 `go test ./...` 零配置必跑**：

1. **全仓扫描（`internal/` + `cmd/`）**：行数 ≤ 850 行零例外、注释 ≤ 5%、零 `TODO/FIXME/HACK`。
2. **分层 `depguard` + `no-api-db-bypass`**：`domain` 纯函数零内部/SQL/HTTP 依赖；`api` 禁导 `database/sql` 且禁直触 `Service.DB`；`app` 禁反向依赖 `api`。
3. **资源零泄漏（按查询/请求计数）**：
   - `sqlclosecheck` / `rowserrcheck`：函数内每次 `Query`/`QueryContext` 必须匹配对应次数的 `Close()` 与 `Err()` 检查（防止同函数变量重用漏关/漏判）。
   - `http-body-close`：每次 HTTP `Do`/`Get`/`Post`/`Head` 返回的 `resp`（未作为返回值交出时）必须在函数内关闭 `resp.Body.Close()`。
4. **零静默吞错**：
   - `no-unchecked-scan-or-unmarshal`：禁止裸调用 `rows.Scan` / `json.Unmarshal` / `.Decode` / `.Commit`。
   - `no-risky-discard`：禁止 `_ =` 静默丢弃 `Commit` / `Unmarshal` / `Decode` / `Scan` / `Exec` 的错误返回。
5. **DDL Parity 守卫**：若离线脚本（如 `provision`）含兜底 `CREATE TABLE IF NOT EXISTS`，用测试解析 `migrations/*.sql` 校验列与索引与最新迁移 100% 一致。

## 2.5 高频隐藏 Bug → L2/L3 机器门禁速查表

| 隐藏 Bug 类型 | L1/L2 静态拦截 | L3 运行/构建门禁 |
|---|---|---|
| 嵌套弹窗遮挡（`z-index` 写死） | `tokens.css` 语义层级 `--z-*` + `z-index-token-only` | — |
| 深色模式浅字浅底失效 | `--text-on-ink` + `no-dark-mode-ink-mismatch` | — |
| `html.lite` 白屏或抽屉硬切 | `no-scoped-global-descendant` + `drawer-collapse-requires-motion` | 构建产物禁裸 `html.lite` + Playwright 抽屉测试 |
| 条件弹窗拖垮首屏或复用巨型 CSS | `no-shared-huge-scoped-css` + `safeAsyncComponent` | `check-bundle-budget.mjs` 入口与异步分包 gzip 上限 |
| HTTP `Body.Close` / 多次 `Query` 漏关 | Go `archguard` 按变量计数检查 | CI + `--full` 全仓 `go test -race` |
| 兜底建表脚本缺历史 ALTER 列 | 解析 `migrations/*.sql` | `TestProvisionSessionsDDLParity` |

---

## 3. 跨端单一真源（消除 Go ↔ TS 手工镜像漂移）

### 3.1 业务算法跨语言 Golden Parity 测试

当核心规则因实时交互需要前后端各写一份时，**绝不靠人工同步**：

1. 在仓库根目录建 `testdata/parity/<feature>.json`，存放覆盖全部边界（含 `null` / 空值 / 极值 / 异常态）的输入与期望输出。
2. Go 单测读取该 JSON 跑后端实现并全字段断言；Vitest 读取同一 JSON 跑前端实现并全字段断言。
3. 任意一端改动公式未同步另一端，门禁在 1 秒内必红。

### 3.2 API DTO 契约漂移门禁

- 使用 `tygo`（从 Go struct 生成 TS interface）或 OpenAPI schema 生成 `web/src/api.generated.ts`。
- 在统一门禁脚本中加入契约一致性校验：重新生成后执行 `git diff --exit-code web/src/api.generated.ts`，有漂移即阻断提交。

---

## 4. 统一质量门禁设计原则（Single Source of Truth）

本地快检、GitHub CI、发版脚本**必须调用同一个入口脚本**，避免三套检查漂移：

1. **禁止手写测试白名单正则**：默认跑全量包；仅用 Go 原生 `if testing.Short() { t.Skip(...) }` 隔离少数超长压测，防止新测试静默漏跑。
2. **强制数据库集成测试不跳过**：始终注入 `CI=true`，缺少测试数据库直接报错退出。
3. **竞态与安全扫描常态化**：全量门禁及 CI 必跑 `go test -race`（至少覆盖含并发锁/goroutine 的包）与 `govulncheck ./...`。
4. **生产红线物理锁死**：
   - Gate 1：Git 禁止跟踪 `.env`、密钥、数据快照、压缩包与多余规则副本；生产高危开关双重锁定。
   - Gate 2：对照上一正式 Tag，禁止修改旧迁移；新增迁移严禁破坏性 DDL（`DROP`/`RENAME`/`TRUNCATE`/`MODIFY`/`CHANGE COLUMN`），保证可单换代码秒级回滚。
5. **E2E 一键隔离闭环**：提供单命令脚本自动分配空闲端口与独立测试 schema → 启服务 → 跑 Playwright → 失败输出 trace/截图路径 → `trap` 自动回收进程，让 Agent 改完 UI 后可独立自证通过。
