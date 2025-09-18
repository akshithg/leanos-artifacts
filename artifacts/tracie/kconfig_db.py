#!/usr/bin/env python3
"""
kconfig_db.py — build a CSV of where CONFIG_* options appear, with ranges for preprocessor branches.

Input:  path to kernel source root
Output: CSV rows:
  CONFIG_name, CONFIG_expression, Source File, Start Line, End Line

Notes:
- For #if/#ifdef/#ifndef/#elif/#else branches, Start/End cover the branch *body* (between directives).
- For macro/single-line occurrences (e.g., IS_ENABLED), Start==End==that line.
"""

import argparse
import csv
import os
import re
import sys
from dataclasses import dataclass, field
from typing import List, Optional

# Extensions to scan
SCAN_EXTS = {
    ".c", ".h", ".S", ".s", ".ld", ".lds", ".dts", ".dtsi", ".asm", ".inc", ".rs"
}

# Directories to skip
SKIP_DIRS_DEFAULT = {
    ".git", ".github", ".gitlab", "Documentation", "samples", "usr", "tools/perf/tests",
}

# Regexes
RE_CONFIG = re.compile(r"\bCONFIG_[A-Z0-9_]+\b")
RE_PREPROC = re.compile(r"^\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)$")
RE_DEFINED = re.compile(r"\bdefined\s*\(\s*(CONFIG_[A-Z0-9_]+)\s*\)")
MACROS = ["IS_ENABLED", "IS_REACHABLE", "IS_BUILTIN", "IS_MODULE"]
RE_MACROS = re.compile(r"\b(" + "|".join(MACROS) + r")\s*\(([^)]*?)\)")

@dataclass
class Branch:
    kind: str                 # 'if'|'ifdef'|'ifndef'|'elif'|'else'
    expr_text: str            # raw text after directive ('' for else)
    directive_line: int       # line number of the directive itself
    start_body: int           # first line of body (directive_line + 1)
    end_body: Optional[int] = None  # inclusive end line of body (set when branch closes)

@dataclass
class IfStackEntry:
    branches: List[Branch] = field(default_factory=list)

def should_scan_file(path: str) -> bool:
    _, ext = os.path.splitext(path)
    return ext in SCAN_EXTS

def iter_files(root, skip_dirs):
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel = os.path.relpath(dirpath, root)
        parts = set(rel.split(os.sep)) if rel != "." else set()
        if parts & {d.strip(os.sep) for d in skip_dirs}:
            dirnames[:] = []  # prune
            continue
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            if should_scan_file(fp):
                yield fp

def extract_configs_from_expr(expr: str):
    """
    Return set of CONFIG_* appearing in an expression (handles defined(CONFIG_...)).
    """
    configs = set(RE_CONFIG.findall(expr))
    for dm in RE_DEFINED.finditer(expr):
        configs.add(dm.group(1))
    return configs

def flush_branch_rows(writer, cfgs, expr, relfp, start_body, end_body):
    if end_body is None:
        end_body = start_body  # safety
    for cfg in sorted(cfgs):
        writer.writerow([cfg, expr, relfp, start_body, end_body])

def process_file(fp: str, relfp: str, writer: csv.writer):
    """
    Stream a file, maintaining a stack of conditional blocks to compute ranges.
    Also emit single-line macro occurrences.
    """
    stack: List[IfStackEntry] = []
    # We also record macro/single-line occurrences on the fly
    with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
        for lineno, line in enumerate(fh, start=1):
            m = RE_PREPROC.match(line)
            if m:
                directive = m.group(1)
                tail = m.group(2).strip()

                if directive in ("if", "ifdef", "ifndef"):
                    # Close any currently open branch at this nesting level? No—new nesting starts.
                    entry = IfStackEntry()
                    br = Branch(
                        kind=directive,
                        expr_text=tail,
                        directive_line=lineno,
                        start_body=lineno + 1,
                    )
                    entry.branches.append(br)
                    stack.append(entry)

                elif directive == "elif":
                    if not stack or not stack[-1].branches:
                        # Unbalanced; ignore gracefully
                        continue
                    # Close previous branch body at the line before this elif
                    prev = stack[-1].branches[-1]
                    if prev.end_body is None:
                        prev.end_body = lineno - 1
                    # Start new branch
                    br = Branch(
                        kind="elif",
                        expr_text=tail,
                        directive_line=lineno,
                        start_body=lineno + 1,
                    )
                    stack[-1].branches.append(br)

                elif directive == "else":
                    if not stack or not stack[-1].branches:
                        continue
                    prev = stack[-1].branches[-1]
                    if prev.end_body is None:
                        prev.end_body = lineno - 1
                    br = Branch(
                        kind="else",
                        expr_text="",
                        directive_line=lineno,
                        start_body=lineno + 1,
                    )
                    stack[-1].branches.append(br)

                elif directive == "endif":
                    if not stack:
                        continue
                    # Close the current branch at line before #endif
                    curr_entry = stack[-1]
                    if curr_entry.branches:
                        last = curr_entry.branches[-1]
                        if last.end_body is None:
                            last.end_body = lineno - 1
                    # Emit rows for all branches of this if-block
                    for br in curr_entry.branches:
                        # build a readable expression string
                        expr_str = f"#{br.kind} {br.expr_text}".strip()
                        cfgs = extract_configs_from_expr(expr_str)
                        if cfgs:
                            flush_branch_rows(writer, cfgs, expr_str, relfp, br.start_body, br.end_body)
                    # Pop the if-block
                    stack.pop()

                # Regardless of directive, also continue to next line
                continue

            # Macro helpers like IS_ENABLED(CONFIG_FOO)
            if any(macro in line for macro in MACROS):
                for mm in RE_MACROS.finditer(line):
                    macro = mm.group(1)
                    args = mm.group(2)
                    cfgs = extract_configs_from_expr(args)
                    if cfgs:
                        expr = f"{macro}({args})"
                        for cfg in sorted(cfgs):
                            writer.writerow([cfg, expr, relfp, lineno, lineno])

            # Generic single-line CONFIG_* mentions (fallback)
            if "CONFIG_" in line:
                # Skip if already accounted via macros; still OK if duplicated—but we can de-dupe per line.
                found = set(RE_CONFIG.findall(line))
                if found:
                    snippet = line.strip()
                    if len(snippet) > 200:
                        snippet = snippet[:197] + "..."
                    for cfg in sorted(found):
                        # Avoid double-counting defined(CONFIG_X) which are covered by #if branches.
                        if f"defined({cfg})" in line.replace(" ", ""):
                            continue
                        writer.writerow([cfg, snippet, relfp, lineno, lineno])

def main():
    ap = argparse.ArgumentParser(description="Build a CSV mapping CONFIG_* references (with ranges for preprocessor branches).")
    ap.add_argument("src", help="Path to the Linux kernel source root")
    ap.add_argument("-o", "--output", help="Output CSV file (default: stdout)")
    ap.add_argument("--skip-dir", action="append", default=[],
                    help=f"Directory name to skip (repeatable). Default skips: {', '.join(sorted(SKIP_DIRS_DEFAULT))}")
    args = ap.parse_args()

    src_root = os.path.abspath(args.src)
    if not os.path.isdir(src_root):
        print(f"error: source path not found or not a directory: {src_root}", file=sys.stderr)
        sys.exit(1)

    skip_dirs = set(SKIP_DIRS_DEFAULT) | set(args.skip_dir)

    out_fh = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
    writer = csv.writer(out_fh)
    writer.writerow(["CONFIG_name", "CONFIG_expression", "Source File", "Start Line", "End Line"])

    total_files = 0
    try:
        for fp in iter_files(src_root, skip_dirs):
            total_files += 1
            relfp = os.path.relpath(fp, src_root)
            try:
                process_file(fp, relfp, writer)
            except (OSError, UnicodeDecodeError) as e:
                print(f"warn: skipping {fp}: {e}", file=sys.stderr)
    finally:
        if out_fh is not sys.stdout:
            out_fh.close()

    print(f"Scanned {total_files} files.", file=sys.stderr)

if __name__ == "__main__":
    main()
