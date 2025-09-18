#!/usr/bin/env python3
"""
normalize_backslashes.py — create a mirror of the kernel tree where any lines ending
with '\' are joined with their successors (across chains), while preserving original
line counts by inserting placeholder comment lines.

This lets simple parsers see full preprocessor expressions like:
    #if !defined(CONFIG_USB_STORAGE_SDDR09) && \
        (defined(CONFIG_...) || defined(CONFIG_...))
as a single physical line, without shifting subsequent line numbers.

Usage:
  python normalize_backslashes.py /path/to/linux /tmp/linux_norm

Only code-ish file extensions are processed; others are copied as-is.
"""
import os
import shutil
import sys

SCAN_EXTS = {
    ".c", ".h", ".S", ".s", ".ld", ".lds", ".dts", ".dtsi", ".asm", ".inc", ".rs"
}
SKIP_DIRS = {".git", ".github", ".gitlab"}

PLACEHOLDER = "/* kconfig-db:join-placeholder */"

def should_scan_file(path: str) -> bool:
    _, ext = os.path.splitext(path)
    return ext in SCAN_EXTS

def normalize_file(src_path: str, dst_path: str):
    with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    out_lines = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        j = i
        # Count how many backslash-continued lines follow starting at i
        # We treat any trailing '\' (possibly with trailing spaces/tabs) as a continuation.
        buf = line.rstrip("\r\n")
        cont = 0
        while buf.rstrip().endswith("\\") and (j + 1) < n:
            cont += 1
            # strip the trailing backslash and any trailing whitespace
            buf = buf.rstrip()
            buf = buf[:-1].rstrip()  # remove '\' and any spaces before it
            # append next physical line content
            j += 1
            next_line = lines[j].rstrip("\r\n")
            buf += " " + next_line.lstrip()  # join with a single space

        out_lines.append(buf + "\n")
        # For each removed newline, add a placeholder line to preserve line count
        for _ in range(cont):
            out_lines.append(PLACEHOLDER + "\n")

        i = j + 1

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, "w", encoding="utf-8", newline="") as f:
        f.writelines(out_lines)

def copy_file(src_path: str, dst_path: str):
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    shutil.copy2(src_path, dst_path)

def main():
    if len(sys.argv) != 3:
        print("usage: normalize_backslashes.py <src_root> <dst_root>", file=sys.stderr)
        sys.exit(1)
    src_root = os.path.abspath(sys.argv[1])
    dst_root = os.path.abspath(sys.argv[2])

    if not os.path.isdir(src_root):
        print(f"error: not a directory: {src_root}", file=sys.stderr)
        sys.exit(1)

    for dirpath, dirnames, filenames in os.walk(src_root, followlinks=False):
        # prune skip dirs
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            src_path = os.path.join(dirpath, fn)
            rel = os.path.relpath(src_path, src_root)
            dst_path = os.path.join(dst_root, rel)
            if should_scan_file(src_path):
                try:
                    normalize_file(src_path, dst_path)
                except Exception as e:
                    print(f"warn: passthrough {rel} due to error: {e}", file=sys.stderr)
                    copy_file(src_path, dst_path)
            else:
                copy_file(src_path, dst_path)

if __name__ == "__main__":
    main()
