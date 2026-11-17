#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
#
# Merge the .gcda files copied out of the guest by run_coupling_suite.py and
# report line/function coverage for the resctrl/MPAM files.

import os
import re
import shutil
import subprocess
import sys

HOME = "/home/r00799764/community"
SRC = HOME + "/kexec_fix"
BUILD = SRC + "/build/arm64-gcov"
GCOV_ROOT = os.environ.get("GCOV_ROOT", "/tmp/mpam_gcov")
WORK = "/tmp/mpam_gcov_merged"
GCOV = "aarch64-linux-gnu-gcov"
GCOV_TOOL = "aarch64-linux-gnu-gcov-tool"

TARGETS = [
    "fs/resctrl/rdtgroup.c",
    "fs/resctrl/monitor.c",
    "fs/resctrl/ctrlmondata.c",
    "fs/resctrl/pseudo_lock.c",
    "drivers/resctrl/mpam_resctrl.c",
    "drivers/resctrl/mpam_devices.c",
    "drivers/resctrl/mpam_fb.c",
    "arch/arm64/kernel/mpam.c",
]

LINE_RE = re.compile(r"^\s*([^:]+):\s*(\d+):(.*)$")
FUNC_RE = re.compile(r"^Function '([^']+)'")
EXEC_RE = re.compile(r"^Lines executed:([0-9.]+)% of (\d+)")


MARKER = "/build/arm64-gcov/"


def normalize(src, dst):
    """Keep only the object-relative part of every .gcda path."""
    shutil.rmtree(dst, ignore_errors=True)
    count = 0
    for root, _, files in os.walk(src):
        for name in files:
            if not name.endswith(".gcda"):
                continue
            path = os.path.join(root, name)
            rel = path.split(MARKER, 1)[1] if MARKER in path else name
            out = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copy2(path, out)
            count += 1
    return count


def merge_modules():
    mods = []
    for name in sorted(os.listdir(GCOV_ROOT)):
        d = os.path.join(GCOV_ROOT, name)
        if os.path.isdir(d) and any(f.endswith(".gcda")
                                    for _, _, fs in os.walk(d) for f in fs):
            mods.append(d)
    if not mods:
        raise SystemExit("no .gcda data under %s" % GCOV_ROOT)

    norm = []
    for i, d in enumerate(mods):
        out = "%s_norm_%d" % (WORK, i)
        if normalize(d, out):
            norm.append(out)

    shutil.rmtree(WORK, ignore_errors=True)
    if len(norm) == 1:
        shutil.copytree(norm[0], WORK)
    else:
        cur = norm[0]
        for i, d in enumerate(norm[1:], 1):
            out = WORK + "_m%d" % i
            shutil.rmtree(out, ignore_errors=True)
            subprocess.run([GCOV_TOOL, "merge", "-o", out, cur, d],
                           check=True)
            cur = out
        shutil.copytree(cur, WORK)
    print("merged coverage from %d module(s)" % len(mods))


def ensure_gcno(source):
    rel = source[:-2] + ".gcno"
    dst = os.path.join(WORK, rel)
    if os.path.exists(dst):
        return True
    src = os.path.join(BUILD, rel)
    if not os.path.exists(src):
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return True


def gcov_output(source):
    objdir = os.path.join(WORK, os.path.dirname(source))
    out = subprocess.run([GCOV, "-t", "-f", "-o", objdir, source],
                         cwd=SRC, capture_output=True, text=True)
    if out.returncode:
        return None
    return out.stdout


def parse(source, text):
    exec_lines = 0
    hit_lines = 0
    if text is None:
        return 0, 0, [], 0, 0
    functions = []
    cur_func = None
    for line in text.splitlines():
        m = FUNC_RE.match(line)
        if m:
            cur_func = m.group(1)
            continue
        m = EXEC_RE.match(line)
        if m and cur_func:
            pct = float(m.group(1))
            functions.append((cur_func, pct))
            cur_func = None
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        count = m.group(1).strip()
        if count == "-":
            continue
        exec_lines += 1
        if count not in ("#####", "=====") and not count.startswith("-"):
            hit_lines += 1
    covered = [f for f, p in functions if p > 0]
    return exec_lines, hit_lines, functions, len(covered), len(functions)


def main():
    merge_modules()
    rows = []
    all_exec = all_hit = 0
    for source in TARGETS:
        if not ensure_gcno(source):
            continue
        text = gcov_output(source)
        exec_lines, hit, funcs, fcov, ftotal = parse(source, text)
        if not exec_lines:
            continue
        rows.append((source, exec_lines, hit, fcov, ftotal, funcs))
        all_exec += exec_lines
        all_hit += hit

    print("\n%-38s %8s %8s %8s  %s" %
          ("file", "lines", "hit", "line%", "functions"))
    for source, total, hit, fcov, ftotal, _ in rows:
        print("%-38s %8d %8d %7.1f%%  %d/%d" %
              (source, total, hit, 100.0 * hit / total, fcov, ftotal))
    if all_exec:
        print("%-38s %8d %8d %7.1f%%" %
              ("TOTAL", all_exec, all_hit, 100.0 * all_hit / all_exec))

    print("\nUncovered functions (by file):")
    for source, _, _, _, _, funcs in rows:
        miss = [f for f, p in funcs if p == 0]
        if miss:
            print("  %s (%d): %s" % (source, len(miss),
                                     ", ".join(miss[:30])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
