# Go + Vue 3 / TypeScript 硬约束落地模板

面向 Go 后端 + Vue 3 / TypeScript 前端 + MySQL + Playwright 技术栈的高 ROI 确定性护栏清单，可按需剪裁复制到目标项目。

---

## 1. 前端硬约束（推荐 `oxlint` 极速扫描或 ESLint Flat Config）

### 1.1 关键禁止规则清单

| 保护目标 | 规则实现 | Error-Driven 报错方向 |
|---|---|---|
| 禁用易出错原生异步加载 | `no-restricted-imports` 禁 `defineAsyncComponent`（仅封装模块豁免） | 提示改用 `safeAsyncComponent` |
| 禁止绕过统一 API 客户端 | 禁业务代码直接调用 `fetch(`（仅 `api.ts` / 探针豁免） | 提示通过 `@/api` 发起请求以保证鉴权/超时/401 处理 |
| 禁止视图间网状耦合 | 禁 `src/views/<A>/*` 导入 `../<B>/*` | 提示将共享逻辑下沉至 `src/domain/` 或 `src/components/shared/` |
| 禁止逃生舱类型断言 | 禁 `as any`、`@ts-ignore`、`@ts-expect-error`（非测试文件） | 提示补齐显式类型或类型守卫 |
| 防范树遍历 O(N²) 退化 | 静态规则拦截 `.map(... .lines.filter(...))` 等嵌套过滤模式 | 提示使用预聚合索引（如 `indexLinesByOrg`）并补双跑等价单测 |
| 控制副作用与文件膨胀 | 新文件限制 `watch`/`watchEffect` 数量与单文件最大行数（如 600 行） | 提示优先使用 `computed` 或事件回调，并按职责拆 composable |

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

## 2. 后端硬约束（`server/.golangci.yml` 精简高信噪比版）

聚焦“防跨层、防漏错、防 SQL 资源泄漏”，避免风格类噪音消耗 Agent 迭代轮次：

```yaml
version: "2"
linters:
  default: none
  enable:
    - govet
    - staticcheck
    - errcheck
    - bodyclose
    - sqlclosecheck
    - rowserrcheck
    - depguard
    - forbidigo
  settings:
    depguard:
      rules:
        domain-is-pure:
          files: ["**/internal/domain/**/*.go"]
          deny:
            - pkg: "database/sql"
              desc: "domain 层必须保持纯函数无副作用，禁止依赖 database/sql"
            - pkg: "net/http"
              desc: "domain 层禁止依赖 net/http"
        api-no-direct-sql:
          files: ["**/internal/api/**/*.go"]
          deny:
            - pkg: "database/sql"
              desc: "HTTP 层禁止直接操作数据库，请通过 internal/app 用例层封装"
        app-no-api:
          files: ["**/internal/app/**/*.go"]
          deny:
            - pkg: "**/internal/api"
              desc: "app 用例层禁止反向依赖 api 传输层"
    forbidigo:
      forbid:
        - pattern: '\.DB\.(Query|QueryRow|Exec)'
          msg: "禁止从外部包直接访问 Service.DB 执行裸 SQL，请在 app/store 封装语义方法"
```

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
