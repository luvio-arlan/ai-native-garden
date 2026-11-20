#!/usr/bin/env python3
"""
AI-Native Codebase Garden Auditor (zero external dependencies).

Scans a repository for structural slop, guardrail gaps, and "paper linters"
aligned with Lauren Tan's Inverted Trust Pyramid:
  1. God files, bloated packages & comment bloat (Codebase as Memory)
  2. Real vs. paper guardrails (uninvoked linters, non-empty ratchets, -race gaps)
  3. TypeScript & Go escape hatches / unchecked error discards / watch & O(N^2) hotspots
  4. CSS token discipline (z-index / dark-mode contrast) & duplicate AI rule files
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path

IGNORE_DIRS = {
    ".git",
    ".agents",
    ".claude",
    ".cursor",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".venv",
    "venv",
    "__pycache__",
    "outputs",
    "tmp",
    "test-data",
    "test-results",
    "playwright-report",
    ".gocache",
    ".liteapp-build",
}

CODE_EXTS = {".go", ".ts", ".tsx", ".vue", ".js", ".jsx", ".mjs", ".cjs", ".py", ".rs", ".java"}
CSS_EXTS = {".css"}
TEST_PATTERNS = ("_test.go", ".test.ts", ".spec.ts", ".test.tsx", ".test.js", ".spec.js")


def is_test_file(path: Path) -> bool:
    name = path.name
    return any(name.endswith(p) for p in TEST_PATTERNS) or "e2e" in path.parts


def walk_files(root: Path, exts: set[str]):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS)
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            if p.suffix in exts:
                yield p


def collect_automation_corpus(root: Path) -> str:
    chunks: list[str] = []
    candidates: list[Path] = []
    for folder in (".github/workflows", "scripts", ".githooks"):
        d = root / folder
        if d.is_dir():
            candidates.extend(sorted(p for p in d.rglob("*") if p.is_file()))
    for name in ("package.json", "web/package.json", "Makefile", "dev.sh"):
        p = root / name
        if p.is_file():
            candidates.append(p)
    for p in candidates:
        try:
            chunks.append(p.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            pass
    return "\n".join(chunks)


def has_nonempty_ratchet(root: Path) -> list[str]:
    found: list[str] = []
    for rel in ("web/scripts/lint-arch.mjs", "scripts/lint-arch.mjs"):
        p = root / rel
        if not p.is_file():
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"const\s+([A-Z_]*RATCHET)\s*=\s*\{([^}]*)\}", txt, re.S):
            body = m.group(2).strip()
            if body:
                entries = len([ln for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("//")])
                found.append(f"{m.group(1)} ({entries} 项)")
    return found


def check_guardrail_files(root: Path, prod_paths: list[Path]) -> list[tuple[str, str]]:
    def first_exists(patterns: list[str]) -> Path | None:
        for pat in patterns:
            matches = sorted(root.glob(pat))
            if matches:
                return matches[0]
        return None

    corpus = collect_automation_corpus(root)
    has_go = any(p.suffix == ".go" for p in prod_paths)
    has_fe = any(p.suffix in {".ts", ".tsx", ".vue", ".js", ".jsx"} for p in prod_paths)
    results: list[tuple[str, str]] = []

    if has_fe:
        fe_cfg = first_exists([
            "eslint.config.*", ".eslintrc*", "oxlint*", ".oxlintrc*", "biome.json*",
            "web/eslint.config.*", "web/.eslintrc*", "web/oxlint*", "web/.oxlintrc*", "web/biome.json*",
            "web/scripts/lint-arch.mjs", "scripts/lint-arch.mjs",
        ])
        if not fe_cfg:
            results.append(("❌", "**Frontend Linter** — 缺少前端静态分析与架构边界拦截"))
        else:
            rel_cfg = str(fe_cfg.relative_to(root))
            wired = (
                "lint-arch" in corpus
                or "eslint" in corpus
                or "oxlint" in corpus
                or "biome" in corpus
                or any("archguard" in str(p) for p in root.glob("web/src/*.test.ts"))
            )
            if wired:
                ratchets = has_nonempty_ratchet(root)
                if ratchets:
                    results.append(("⚠️", f"**Frontend Linter (`{rel_cfg}`)** — 已接入门禁，但仍存在历史棘轮白名单：{', '.join(ratchets)}"))
                else:
                    results.append(("✅", f"**Frontend Linter (`{rel_cfg}`)** — 已接入且零棘轮白名单"))
            else:
                results.append(("⚠️", f"**Paper Linter (`{rel_cfg}`)** — 配置文件存在但未接入 `package.json`/CI/门禁脚本"))

    if has_go:
        golangci = first_exists([".golangci.yml", ".golangci.yaml", "server/.golangci.yml", "server/.golangci.yaml"])
        arch_tests = sorted(root.glob("server/internal/archguard/*_test.go")) + sorted(root.glob("internal/archguard/*_test.go"))
        golangci_wired = bool(re.search(r"golangci-lint\s+run", corpus))
        if golangci and not golangci_wired:
            rel_gl = str(golangci.relative_to(root))
            results.append(("⚠️", f"**Paper Linter (`{rel_gl}`)** — 存在配置但 CI/门禁脚本从未调用 `golangci-lint run`，建议删除或接入 CI"))
        if arch_tests:
            rel_arch = str(arch_tests[0].relative_to(root))
            results.append(("✅", f"**Go Archguard (`{rel_arch}`)** — Go AST 架构守卫随 `go test` 强制执行"))
        elif golangci and golangci_wired:
            results.append(("✅", "**Go Linter (`golangci-lint`)** — 已接入 CI/门禁"))
        else:
            results.append(("❌", "**Go Guardrails** — 后端仅靠基础 `go vet`，缺少 `depguard`/`sqlclosecheck`/`rowserrcheck`/`bodyclose`"))

        if "-race" in corpus:
            if re.search(r"go\s+test\s+-race[^\n]*(?:\./internal/app|\./\.\.\.)", corpus):
                results.append(("✅", "**Go Race Detector (`-race`)** — 全仓/核心用例层均启用竞态检测"))
            else:
                results.append(("⚠️", "**Go Race Detector (`-race`)** — 已配置但疑似跳过 `internal/app` 核心用例层，建议扩展至 `./...`"))
        else:
            results.append(("❌", "**Go Race Detector (`-race`)** — 缺少并发竞态检测"))

    has_ci = bool(first_exists([".github/workflows/*.yml", ".github/workflows/*.yaml"]))
    results.append(("✅" if has_ci else "❌", "**CI Pipeline (.github/workflows)**" + ("" if has_ci else " — 缺少自动化 CI 门禁")))

    has_agents = (root / "AGENTS.md").is_file()
    results.append(("✅" if has_agents else "❌", "**Single AI Rule Entry (AGENTS.md)**" + ("" if has_agents else " — 建议设立唯一规则入口 AGENTS.md")))

    dup_rules = first_exists(["CLAUDE.md", ".cursor/rules/*", ".cursorrules"])
    results.append(("⚠️" if dup_rules else "✅", "**Duplicate Rule Files Absent**" + (" — 存在多份 AI 规则副本，易漂移" if dup_rules else "")))
    return results


def audit_repo(root: Path, large_line_limit: int) -> str:
    all_code_files = list(walk_files(root, CODE_EXTS))
    prod_files: list[tuple[int, Path]] = []
    prod_paths: list[Path] = []
    pkg_counts: Counter[str] = Counter()
    go_unchecked = 0
    ts_escapes = 0
    watch_hotspots: Counter[str] = Counter()
    todo_count = 0
    total_nonblank = 0
    total_comments = 0
    raw_sql_files: Counter[str] = Counter()
    nested_filter_hits: list[str] = []
    raw_zindex_hits: list[str] = []

    re_ts_escape = re.compile(r"@ts-ignore|@ts-expect-error|\bas\s+any\b|\bas\s+never\b|\bas\s+unknown\s+as\b")
    re_go_discard = re.compile(r"^\s*_\s*=")
    re_watch = re.compile(r"\b(watch|watchEffect|useEffect)\s*\(")
    re_todo = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")
    re_sql = re.compile(r"(?<!URL)\.(Query|QueryRow|Exec)(Context)?\(")
    re_nested_filter = re.compile(r"\.(?:map|forEach|reduce)\(.*lines\.filter\(")
    re_zindex = re.compile(r"(?:\bz-index\s*:\s*(?:[5-9]\d|\d{3,})\b|:z-index\s*=\s*[\"']\d+[\"'])")

    for p in all_code_files:
        if is_test_file(p):
            continue
        rel = p.relative_to(root)
        try:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue

        prod_paths.append(p)
        prod_files.append((len(lines), rel))
        pkg_counts[str(rel.parent)] += 1

        in_comment_block = False
        for idx, line in enumerate(lines, start=1):
            s = line.strip()
            if not s:
                continue
            total_nonblank += 1
            if s.startswith(("/*", "<!--")):
                in_comment_block = "*/" not in s and "-->" not in s
                total_comments += 1
            elif in_comment_block:
                total_comments += 1
                if "*/" in s or "-->" in s:
                    in_comment_block = False
            elif s.startswith(("//", "#", "*")):
                total_comments += 1

            if re_todo.search(line) and "archguard" not in rel.parts and "lint-arch" not in p.name:
                todo_count += 1
            if p.suffix == ".go":
                if re_go_discard.search(line):
                    go_unchecked += 1
                if re_sql.search(line) and "db" not in rel.parts and "store" not in rel.parts:
                    raw_sql_files[str(rel)] += 1
            if p.suffix in {".ts", ".tsx", ".vue", ".js", ".jsx"}:
                if re_ts_escape.search(line):
                    ts_escapes += 1
                if re_watch.search(line):
                    watch_hotspots[str(rel)] += 1
                if re_nested_filter.search(line):
                    nested_filter_hits.append(f"{rel}:{idx}")
                if p.suffix == ".vue" and re_zindex.search(line):
                    raw_zindex_hits.append(f"{rel}:{idx}")

    for css_p in walk_files(root, CSS_EXTS):
        if css_p.name == "tokens.css":
            continue
        rel_css = css_p.relative_to(root)
        try:
            for idx, line in enumerate(css_p.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
                if re_zindex.search(line):
                    raw_zindex_hits.append(f"{rel_css}:{idx}")
        except OSError:
            pass

    prod_files.sort(key=lambda x: x[0], reverse=True)
    oversized = [(n, rel) for n, rel in prod_files if n >= large_line_limit]
    comment_pct = (total_comments * 100.0 / total_nonblank) if total_nonblank else 0.0

    out: list[str] = []
    out.append(f"# Codebase Garden Audit: `{root.name}`\n")
    out.append("## 1. 静态硬约束、纸面门禁与 CI 覆盖")
    for icon, desc in check_guardrail_files(root, prod_paths):
        out.append(f"- {icon} {desc}")

    out.append("\n## 2. 上下文健康度与巨型文件（Codebase as Memory）")
    out.append(f"- 非测试源码文件数：**{len(prod_files)}**，非空代码行：**{total_nonblank:,}**，注释占比：**{comment_pct:.1f}%**")
    out.append(f"- 超过 `{large_line_limit}` 行的巨型文件：**{len(oversized)}** 个")
    if oversized:
        out.append("\nTop 10 最大文件：")
        for n, rel in oversized[:10]:
            out.append(f"  - `{rel}`: **{n}** 行")

    bloated_dirs = [(d, c) for d, c in pkg_counts.most_common(5) if c >= 15]
    if bloated_dirs:
        out.append("\n扁平高密度目录（≥15 个源码文件）：")
        for d, c in bloated_dirs:
            out.append(f"  - `{d}/`: **{c}** 个文件")

    out.append("\n## 3. 风险模式与逃生舱统计")
    out.append(f"- TypeScript 类型逃生舱（`as any` / `as never` / `@ts-ignore` / `as unknown as`）：**{ts_escapes}**")
    out.append(f"- Go 显式丢弃返回值（`_ =`）：**{go_unchecked}**")
    out.append(f"- 硬编码 `z-index >= 50` 魔数：**{len(raw_zindex_hits)}**")
    out.append(f"- `TODO / FIXME / HACK / XXX` 残留：**{todo_count}**")

    if watch_hotspots:
        out.append("\n副作用钩子热点（`watch` / `watchEffect` / `useEffect` Top 5）：")
        for rel, c in watch_hotspots.most_common(5):
            out.append(f"  - `{rel}`: **{c}** 处")

    if raw_sql_files:
        out.append(f"\n业务/接口层裸 SQL 分布（共 **{len(raw_sql_files)}** 个文件，Top 5）：")
        for rel, c in raw_sql_files.most_common(5):
            out.append(f"  - `{rel}`: **{c}** 处")

    if nested_filter_hits:
        out.append("\n疑似树遍历嵌套 `lines.filter(...)` 命中：")
        for hit in nested_filter_hits[:10]:
            out.append(f"  - `{hit}`")

    if raw_zindex_hits:
        out.append("\n硬编码 `z-index >= 50` 命中（Top 10）：")
        for hit in raw_zindex_hits[:10]:
            out.append(f"  - `{hit}`")

    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a codebase against AI-Native Garden standards.")
    parser.add_argument("path", nargs="?", default=".", help="Repository root directory")
    parser.add_argument("--limit", type=int, default=800, help="Large file line threshold (default: 800)")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"Error: not a directory: {root}", file=sys.stderr)
        return 1
    print(audit_repo(root, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
