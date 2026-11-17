#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
#
# resctrl/MPAM coupling: MSC error interrupt path.
#
# Destructive: injecting an out-of-range RIS makes the MPAM driver handle the
# error and disable MPAM. Run this module last, on a kernel built with
# CONFIG_STRICT_DEVMEM=n (devmem access).

import os
import subprocess
import sys
import time

import mpam_suite_lib as L
from mpam_suite_lib import errname, read

# L3 cache MSC base for the 2-core / 1-cluster / 1-socket QEMU topology used
# by this module (same model as scripts/irq_path_test.py).
MSC_L3 = 0x0B00A000
ECR = 0xf0
ESR_LO = 0xf8
ESR_HI = 0xfc
PART_SEL = 0x100


def devmem(addr, width=None, value=None):
    args = ["busybox", "devmem", "0x%x" % addr]
    if width is not None:
        args.append("%d" % width)
    if value is not None:
        args.append("0x%x" % value)
    out = subprocess.run(args, capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else None


def irq_count():
    total = 0
    try:
        with open("/proc/interrupts") as f:
            for line in f:
                if "mpam" not in line:
                    continue
                head, _, _ = line.partition(":")
                for tok in head.split():
                    if tok.isdigit():
                        total += int(tok)
    except OSError:
        pass
    return total


def main():
    s = L.Suite("resctrl/MPAM coupling (irq)")
    rc = L.mount("debug", s)
    if rc:
        s.info("mount resctrl failed: %s" % errname(rc))

    pre_ecr = devmem(MSC_L3 + ECR, 32)
    pre_lo = devmem(MSC_L3 + ESR_LO, 32)
    pre_hi = devmem(MSC_L3 + ESR_HI, 32)
    pre_irq = irq_count()
    s.info("pre: ECR=%s ESR=%s/%s irq=%d" %
           (pre_ecr, pre_lo, pre_hi, pre_irq))
    s.check("MSC registers accessible", pre_ecr is not None, str(pre_ecr))

    # PART_SEL.RIS=15 (undefined) with PARTID=5 -> Undefined_RIS_PART_SEL.
    s.check("inject undefined RIS",
            devmem(MSC_L3 + PART_SEL, 32, (15 << 24) | 5) is not None)
    time.sleep(4)

    dmesg = subprocess.run(["dmesg"], capture_output=True, text=True).stdout
    post_ecr = devmem(MSC_L3 + ECR, 32)
    post_lo = devmem(MSC_L3 + ESR_LO, 32)
    post_hi = devmem(MSC_L3 + ESR_HI, 32)
    post_irq = irq_count()
    s.info("post: ECR=%s ESR=%s/%s irq=%d" %
           (post_ecr, post_lo, post_hi, post_irq))

    s.check("MPAM irq registered before injection", pre_irq > 0, str(pre_irq))
    s.info("MPAM irq count after the error: %d (driver disabled MPAM)"
           % post_irq)
    s.check("error irq handler ran",
            "error irq from msc" in dmesg,
            [ln for ln in dmesg.splitlines() if "mpam" in ln][-3:])
    s.check("error code decoded",
            "Undefined_RIS_PART_SEL" in dmesg)
    try:
        esr_low = int(post_lo, 16) if post_lo else None
        ecr_val = int(post_ecr, 16) if post_ecr else None
    except ValueError:
        esr_low = ecr_val = None
    s.check("handler cleared the error", esr_low == 0, str(post_lo))
    s.check("handler disabled the error interrupt", ecr_val == 0,
            str(post_ecr))

    L.umount(suite=s)
    return s.summary()


if __name__ == "__main__":
    sys.exit(main())
