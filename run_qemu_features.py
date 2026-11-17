#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
#
# Boot the guest once per QEMU MPAM model feature and check it.
# Requires a kernel with CONFIG_STRICT_DEVMEM=n (devmem).

import os
import shutil
import subprocess
import sys

import run_coupling_suite as suite

HOME = "/home/r00799764/community"
QEMU = HOME + "/qemu/build/qemu-system-aarch64"
KERNEL = os.environ.get(
    "MPAM_FEAT_KERNEL",
    HOME + "/kexec_fix/build/arm64-gcov/arch/arm64/boot/Image")

SMP2 = "2,sockets=1,clusters=1,cores=2,threads=1"
SMP8 = "8,sockets=1,clusters=2,cores=4,threads=1"

FEATURES = [
    ("iidr", SMP2,
     "mpam-iidr-implementer=0x36b,mpam-iidr-product=0x241",
     "qemu_iidr_impl=0x36b qemu_iidr_prod=0x241 "
     "qemu_iidr_var=0 qemu_iidr_rev=0"),
    ("mbwu", SMP2, "mpam-mbwu-lwd=1,mpam-mbwu-scale=3",
     "qemu_lwd=1 qemu_scale=3"),
    ("nrdy", SMP2, "mpam-nrdy-usec=200000", ""),
    ("ppi", SMP2, "mpam-ppi=on", ""),
    ("shared", SMP2, "mpam-shared-irq=on", ""),
    ("msi", SMP2, "mpam-err-msi=on", "qemu_msi_addr=0x48000000"),
]


def main():
    wanted = sys.argv[1:]
    feats = [f for f in FEATURES if not wanted or f[0] in wanted]
    if not feats:
        raise SystemExit("no such feature")
    suite.build_initrd()

    failed = 0
    for name, smp, machine, cargs in feats:
        tag = "feat_" + name
        env = dict(os.environ)
        append = ("console=ttyAMA0 earlycon=pl011,0x09000000 "
                  "rdinit=/init resctrl_suite=mpam_coupling_qemu "
                  "qemu_feature=%s %s" % (name, cargs))
        if os.environ.get("MPAM_GCOV") == "1":
            share = "/tmp/mpam_gcov/" + tag
            shutil.rmtree(share, ignore_errors=True)
            os.makedirs(share)
            env["MPAM_VIRTFS"] = share
            append += " resctrl_gcov=1"
        env.update({
            "MPAM_TAG": tag,
            "MPAM_QEMU": QEMU,
            "MPAM_KERNEL": KERNEL,
            "MPAM_INITRD": suite.INITRD,
            "MPAM_SMP": smp,
            "MPAM_MACHINE_EXTRA": machine,
            "MPAM_APPEND": append,
            "MPAM_DONE": "SUITE DONE",
            "MPAM_TIMEOUT": "600",
        })
        print("\n=== QEMU feature: %s ===" % name, flush=True)
        subprocess.run([sys.executable, HOME + "/mpam/launch_pytest.py"],
                       env=env)
        log = HOME + "/mpam_qemu_test_v2/logs/%s_run.log" % tag
        result = None
        fails = []
        if os.path.exists(log):
            with open(log, errors="replace") as f:
                for line in f:
                    if line.startswith("RESULT:"):
                        result = line.strip()
                    elif line.startswith("FAIL:"):
                        fails.append(line.strip())
        print(result or "RESULT: MISSING (%s)" % log, flush=True)
        for f in fails:
            print("  " + f, flush=True)
        failed += len(fails) + (0 if result else 1)

    print("\n=== SUMMARY: %d feature failures ===" % failed, flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
