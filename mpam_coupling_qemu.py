#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
#
# QEMU MPAM model feature checks.  The machine extras and topology are
# chosen by run_qemu_features.py; the feature name is on the kernel command
# line as qemu_feature=<name>.

import os
import subprocess
import sys
import time

import mpam_suite_lib as L
from mpam_suite_lib import errname, read

# L3 cache MSC base for the 2-core / 1-cluster / 1-socket topology used here.
MSC = 0x0B00A000
IIDR = 0x18
MBWUMON_IDR = 0x90
ECR = 0xF0
ESR_LO = 0xF8
PART_SEL = 0x100
MON_SEL = 0x800
CSU_FLT = 0x810
CSU_CTL = 0x818
MSMON_CSU = 0x840
ERR_MSI_MPAM = 0xDC
ERR_MSI_ADDR_L = 0xE0
ERR_MSI_ADDR_H = 0xE4
ERR_MSI_DATA = 0xE8


def cmdline():
    try:
        with open("/proc/cmdline") as f:
            return f.read().split()
    except OSError:
        return []


def cmdarg(name, default=None):
    for a in cmdline():
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def devmem(addr, width=None, value=None):
    args = ["busybox", "devmem", "0x%x" % addr]
    if width is not None:
        args.append("%d" % width)
    if value is not None:
        args.append("0x%x" % value)
    out = subprocess.run(args, capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else None


def dmesg():
    return subprocess.run(["dmesg"], capture_output=True, text=True).stdout


def section(s):
    print("\n### %s" % s, flush=True)


def main():
    feature = cmdarg("qemu_feature")
    s = L.Suite("resctrl/MPAM QEMU feature (%s)" % feature)
    rc = L.mount("debug", s)
    if rc:
        s.info("mount failed: %s" % errname(rc))

    if feature == "iidr":
        section("MPAMF_IIDR")
        v = devmem(MSC + IIDR, 32)
        s.check("IIDR readable", v is not None, str(v))
        if v:
            iidr = int(v, 16)
            impl = int(cmdarg("qemu_iidr_impl", "0"), 0)
            prod = int(cmdarg("qemu_iidr_prod", "0"), 0)
            var = int(cmdarg("qemu_iidr_var", "0"), 0)
            rev = int(cmdarg("qemu_iidr_rev", "0"), 0)
            s.check_eq("IIDR implementer", iidr & 0xfff, impl)
            s.check_eq("IIDR product", (iidr >> 20) & 0xfff, prod)
            s.check_eq("IIDR variant", (iidr >> 16) & 0xf, var)
            s.check_eq("IIDR revision", (iidr >> 12) & 0xf, rev)
    elif feature == "mbwu":
        section("MPAMF_MBWUMON_IDR LWD/SCALE")
        v = devmem(MSC + MBWUMON_IDR, 32)
        s.check("MBWUMON_IDR readable", v is not None, str(v))
        if v:
            reg = int(v, 16)
            lwd = int(cmdarg("qemu_lwd", "-1"), 0)
            scale = int(cmdarg("qemu_scale", "0"), 0)
            s.check_eq("LWD field", (reg >> 29) & 1, lwd)
            s.check_eq("SCALE field", (reg >> 16) & 0x1f, scale)
            # Long counter readings still work through resctrl.
            s.check("llc_occupancy readable",
                    (L.mon_read("", "llc_occupancy") or "").isdigit(),
                    L.mon_read("", "llc_occupancy"))
            s.check("mbm_total_bytes readable",
                    (L.mon_read("", "mbm_total_bytes") or "").isdigit(),
                    L.mon_read("", "mbm_total_bytes"))
    elif feature == "nrdy":
        section("NRDY polling")
        # Drive CSU monitor 0 directly: the driver's read path needs the
        # firmware "arm,not-ready-us" property, which QEMU does not expose.
        devmem(MSC + MON_SEL, 32, 0)          # MON_SEL=0, RIS=0
        devmem(MSC + CSU_FLT, 32, 0)          # PARTID=0, PMG=0
        devmem(MSC + CSU_CTL, 32, (1 << 16) | (1 << 17) | (1 << 31))
        v = devmem(MSC + MSMON_CSU, 32)
        s.check("MSMON_CSU readable", v is not None, str(v))
        if v:
            s.check("NRDY set right after configuration",
                    int(v, 16) & (1 << 31), v)
        time.sleep(0.6)
        v = devmem(MSC + MSMON_CSU, 32)
        if v:
            s.check("NRDY clears after the configured delay",
                    not (int(v, 16) & (1 << 31)), v)
    elif feature in ("ppi", "shared"):
        section("interrupt wiring: %s" % feature)
        irqs = read("/proc/interrupts")
        mpam_lines = [ln for ln in irqs.splitlines() if "mpam" in ln]
        s.check("MPAM interrupts registered", bool(mpam_lines),
                mpam_lines[:2])
        if feature == "ppi":
            # ACPI maps the GSIV to a dynamically allocated Linux virq, so
            # check the GIC hardware interrupt number instead (PPI 16..31).
            ppi = []
            for ln in mpam_lines:
                toks = ln.split()
                if "GICv3" in toks:
                    try:
                        hwirq = int(toks[toks.index("GICv3") + 1])
                    except (IndexError, ValueError):
                        continue
                    if 16 <= hwirq <= 31:
                        ppi.append(ln)
            s.check("MPAM irqs are PPIs", len(ppi) > 0, mpam_lines[:2])
        else:
            hwirqs = set()
            for ln in mpam_lines:
                toks = ln.split()
                if "GICv3" in toks:
                    try:
                        hwirqs.add(int(toks[toks.index("GICv3") + 1]))
                    except (IndexError, ValueError):
                        pass
            s.check("all MSCs share one SPI", len(hwirqs) == 1,
                    sorted(hwirqs))

        devmem(MSC + PART_SEL, 32, (15 << 24) | 5)
        time.sleep(4)
        d = dmesg()
        s.check("shared/PPI handler ran", "error irq from msc" in d,
                [ln for ln in d.splitlines() if "mpam" in ln][-3:])
        s.check("error decoded", "Undefined_RIS_PART_SEL" in d)
    elif feature == "msi":
        section("error MSI")
        data = 0x12345678
        addr = int(cmdarg("qemu_msi_addr", "0x48000000"), 0)
        devmem(MSC + ERR_MSI_ADDR_L, 32, addr & 0xffffffff)
        devmem(MSC + ERR_MSI_ADDR_H, 32, addr >> 32)
        devmem(MSC + ERR_MSI_DATA, 32, data)
        devmem(MSC + ERR_MSI_MPAM, 32, 1)
        devmem(MSC + ECR, 32, 1)         # INTEN
        devmem(MSC + PART_SEL, 32, (15 << 24) | 5)
        time.sleep(3)
        got = devmem(addr, 32)
        s.check_eq("MSI data written to the target address", got,
                   "0x%08x" % data)
    else:
        s.fail("unknown qemu_feature=%r" % feature)

    L.umount(suite=s)
    return s.summary()


if __name__ == "__main__":
    sys.exit(main())
