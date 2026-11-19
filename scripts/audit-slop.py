#!/usr/bin/env python3
"""
AI-Native Codebase Garden Auditor (zero external dependencies).

Scans a repository for structural slop & guardrail gaps aligned with
Lauren Tan's Inverted Trust Pyramid:
  1. God files & bloated packages (Codebase as Memory)
  2. Missing linters / pre-commit / CI guardrails
  3. TypeScript & Go escape hatches / unchecked error discards / watch hotspots
  4. Duplicate agent rule files & comment density
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

CODE_EXTS = {".go", ".ts", ".tsx", ".vue", ".js", ".jsx", ".py", ".rs", ".java"}
TEST_PATTERNS = ("_test.go", ".test.ts", ".spec.ts", ".test.tsx", ".test.js", ".spec.js")


def is_test_file(path: Path) -> bool:
    name = path.name
    return any(name.endswith(p) for p in TEST_PATTERNS) or "e2e" in path.parts


def walk_source_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS)
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            if p.suffix in CODE_EXTS:
                yield p


def check_guardrail_files(root: Path) -> list[tuple[str, bool, str]]:
    def any_exists(patterns: list[str]) -> bool:
        for pat in patterns:
            if list(root.glob(pat)):
                return True
        return False

    return [
        ("Frontend Linter (ESLint/oxlint/Biome)", any_exists([
            "eslint.config.*", ".eslintrc*", "oxlint*", ".oxlintrc*", "biome.json*",
            "web/eslint.config.*", "web/.eslintrc*", "web/oxlint*", "web/.oxlintrc*", "web/biome.json*",
        ]), "缺少前端静态分析与架构边界拦截"),
        ("Go Linter (golangci-lint)", any_exists([
            ".golangci.yml", ".golangci.yaml", "server/.golangci.yml", "server/.golangci.yaml",
        ]), "后端仅靠基础 go vet，缺少 depguard/errcheck/sqlclosecheck"),
        ("CI Pipeline (.github/workflows)", any_exists([".github/workflows/*.yml", ".github/workflows/*.yaml"]), "缺少自动化 CI 门禁"),
        ("Single AI Rule Entry (AGENTS.md)", (root / "AGENTS.md").is_file(), "建议设立唯一规则入口 AGENTS.md"),
        ("Duplicate Rule Files Absent", not any_exists(["CLAUDE.md", ".cursor/rules/*", ".cursorrules"]), "存在多份 AI 规则副本，易漂移"),
    ]


def audit_repo(root: Path, large_line_limit: int) -> str:
    prod_files: list[tuple[int, Path]] = []
    pkg_counts: Counter[str] = Counter()
    go_unchecked = 0
    ts_escapes = 0
    watch_hotspots: Counter[str] = Counter()
    todo_count = 0
    total_nonblank = 0
    total_comments = 0
    raw_sql_files: Counter[str] = Counter()
    nested_filter_hits: list[str] = []

    re_ts_escape = re.compile(r"@ts-ignore|@ts-expect-error|\bas\s+any\b|\bas\s+unknown\s+as\b")
    re_go_discard = re.compile(r"^\s*_\s*=")
    re_watch = re.compile(r"\b(watch|watchEffect|useEffect)\s*\(")
    re_todo = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")
    re_sql = re.compile(r"(?<!URL)\.(Query|QueryRow|Exec)(Context)?\(")
    re_nested_filter = re.compile(r"\.map\(.*lines\.filter\(")

    for p in walk_source_files(root):
        if is_test_file(p):
            continue
        rel = p.relative_to(root)
        try:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue

        prod_files.append((len(lines), rel))
        pkg_counts[str(rel.parent)] += 1

        for idx, line in enumerate(lines, start=1):
            s = line.strip()
            if not s:
                continue
            total_nonblank += 1
            if s.startswith(("//", "/*", "*", "<!--", "#")):
                total_comments += 1
            if re_todo.search(line):
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

    prod_files.sort(key=lambda x: x[0], reverse=True)
    oversized = [(n, rel) for n, rel in prod_files if n >= large_line_limit]
    comment_pct = (total_comments * 100.0 / total_nonblank) if total_nonblank else 0.0

    out: list[str] = []
    out.append(f"# Codebase Garden Audit: `{root.name}`\n")
    out.append("## 1. 静态硬约束与门禁覆盖")
    for label, ok, note in check_guardrail_files(root):
        icon = "✅" if ok else "❌"
        suffix = "" if ok else f" — {note}"
        out.append(f"- {icon} **{label}**{suffix}")

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
    out.append(f"- TypeScript 类型逃生舱（`as any` / `@ts-ignore` / `as unknown as`）：**{ts_escapes}**")
    out.append(f"- Go 显式丢弃返回值（`_ =`）：**{go_unchecked}**")
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
