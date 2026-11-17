#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
#
# Boot one QEMU guest per resctrl/MPAM coupling module and collect results.
#
# Each module is a standalone guest script under this directory. A fresh boot
# per module keeps the resctrl mount state (and the deliberately destructive
# CDP / hotplug tests) isolated.

import os
import shutil
import subprocess
import sys

HOME = "/home/r00799764/community"
MPAM = HOME + "/mpam"
TEST_HOME = HOME + "/mpam_qemu_test_v2"
ROOTFS = "/tmp/mpam_suite_rootfs"
INITRD = TEST_HOME + "/initrd/suite-initrd.gz"
BASE_INITRD = TEST_HOME + "/initrd/pytest-initrd.gz"
KERNEL = os.environ.get(
    "MPAM_KERNEL", HOME + "/kexec_fix/build/arm64/arch/arm64/boot/Image")

MODULES = [
    ("mpam_coupling", "plain controls/groups/tasks/monitors/reparent"),
    ("mpam_coupling_limits", "CLOSID/RMID exhaustion and limbo"),
    ("mpam_coupling_cdp", "CDP and CDPL2 mounts"),
    ("mpam_coupling_hotplug", "CPU hotplug / domain lifetime"),
    ("mpam_coupling_topology", "two-socket domains / domain offline"),
]

# Destructive test, needs CONFIG_STRICT_DEVMEM=n; opt in explicitly.
if os.environ.get("MPAM_IRQ") == "1":
    MODULES.append(("mpam_coupling_irq", "MSC error interrupt injection"))
# Allocation-failure sweep, needs CONFIG_FAILSLAB in the kernel.
if os.environ.get("MPAM_FAULT") == "1":
    MODULES.append(("mpam_coupling_fault", "failslab allocation failures"))

INIT = r"""#!/bin/sh
/bin/busybox --install -s /bin 2>/dev/null
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export HOME=/root
export TERM=linux
mount -t proc proc /proc
mount -t sysfs sys /sys
mount -t devtmpfs dev /dev 2>/dev/null
mount -t tmpfs tmp /tmp 2>/dev/null
mount -t debugfs none /sys/kernel/debug 2>/dev/null
mkdir -p /sys/fs/resctrl

MODULE=
GCOV=0
for a in $(cat /proc/cmdline); do
    case "$a" in
        resctrl_suite=*) MODULE="${a#resctrl_suite=}" ;;
        resctrl_gcov=1) GCOV=1 ;;
    esac
done

if [ "$GCOV" = 1 ]; then
    mkdir -p /out
    mount -t 9p -o trans=virtio,version=9p2000.L gcov /out \
        && echo "GCOV-MOUNT-OK" || echo "GCOV-MOUNT-FAIL"
fi

echo "=== resctrl suite: ${MODULE:-<none>} ==="
cd /mpam || exit 1
if [ -n "$MODULE" ]; then
    python3 "$MODULE.py"
    echo "=== ${MODULE} exit=$? ==="
else
    echo "no resctrl_suite= on the kernel command line"
fi

if [ "$GCOV" = 1 ] && [ -d /out ]; then
    dest="/out/$MODULE"
    mkdir -p "$dest"
    n=0
    for f in $(find /sys/kernel/debug/gcov -name '*.gcda'); do
        rel="${f#/sys/kernel/debug/gcov/}"
        mkdir -p "$dest/$(dirname "$rel")"
        cat "$f" > "$dest/$rel" && n=$((n+1))
    done
    echo "GCOV-DONE files=$n"
fi

echo "SUITE DONE"
sync
poweroff -f
"""


def build_initrd():
    if not os.path.isdir(ROOTFS):
        os.makedirs(ROOTFS)
        with open(BASE_INITRD, "rb") as f:
            gunzip = subprocess.Popen(["gzip", "-dc"], stdin=f,
                                      stdout=subprocess.PIPE)
            cpio = subprocess.Popen(["cpio", "-idm", "--quiet"],
                                    stdin=gunzip.stdout, cwd=ROOTFS)
            gunzip.stdout.close()
            if cpio.wait() or gunzip.wait():
                raise SystemExit("failed to extract %s" % BASE_INITRD)
    dst = os.path.join(ROOTFS, "mpam")
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(MPAM):
        if name.endswith(".py"):
            shutil.copy2(os.path.join(MPAM, name), os.path.join(dst, name))
    init = os.path.join(ROOTFS, "init")
    with open(init, "w") as f:
        f.write(INIT)
    os.chmod(init, 0o755)
    # Repack. 17 MB compressed; a couple of seconds.
    with open(INITRD, "wb") as out:
        find = subprocess.Popen(["find", "."], cwd=ROOTFS,
                                stdout=subprocess.PIPE)
        cpio = subprocess.Popen(["cpio", "-o", "-H", "newc", "--quiet"],
                                cwd=ROOTFS, stdin=find.stdout,
                                stdout=subprocess.PIPE)
        gzip = subprocess.Popen(["gzip", "-9"], stdin=cpio.stdout,
                                stdout=out)
        find.stdout.close()
        cpio.stdout.close()
        rc = gzip.wait()
        cpio.wait()
        find.wait()
    if rc:
        raise SystemExit("failed to pack %s" % INITRD)


def run_module(name, desc):
    tag = "suite_" + name.replace("mpam_coupling", "c")[:24]
    log = TEST_HOME + "/logs/%s_run.log" % tag
    env = dict(os.environ)
    append = ("console=ttyAMA0 earlycon=pl011,0x09000000 "
              "rdinit=/init resctrl_suite=%s" % name)
    if os.environ.get("MPAM_GCOV") == "1":
        share = "/tmp/mpam_gcov/" + name
        shutil.rmtree(share, ignore_errors=True)
        os.makedirs(share)
        env["MPAM_VIRTFS"] = share
        append += " resctrl_gcov=1"
    if name == "mpam_coupling_topology":
        env["MPAM_SMP"] = "8,sockets=2,clusters=2,cores=2,threads=1"
    elif name == "mpam_coupling_irq":
        env["MPAM_SMP"] = "2,sockets=1,clusters=1,cores=2,threads=1"
    elif name == "mpam_coupling_limits":
        # The limbo test needs the reported occupancy to drop below the
        # RMID reallocation threshold.  The QEMU CSU model reports the full
        # programmed CPBM occupancy forever (real caches evict), so keep the
        # modelled capacity below the smallest L3 size.
        env["MPAM_MACHINE_EXTRA"] = "mpam-csu-capacity=65536"
    env.update({
        "MPAM_TAG": tag,
        "MPAM_KERNEL": KERNEL,
        "MPAM_INITRD": INITRD,
        "MPAM_APPEND": append,
        "MPAM_DONE": "SUITE DONE",
        "MPAM_TIMEOUT": env.get("MPAM_TIMEOUT", "1200"),
    })
    print("\n=== %s (%s) ===" % (name, desc), flush=True)
    print("kernel: %s" % KERNEL, flush=True)
    subprocess.run([sys.executable, MPAM + "/launch_pytest.py"], env=env)

    fails = []
    result = None
    if os.path.exists(log):
        with open(log, errors="replace") as f:
            for line in f:
                if line.startswith("FAIL:"):
                    fails.append(line.strip())
                elif line.startswith("RESULT:"):
                    result = line.strip()
    print(result or "RESULT: MISSING (log=%s)" % log, flush=True)
    for f in fails:
        print("  " + f, flush=True)
    return fails, result


def main():
    wanted = sys.argv[1:]
    modules = [m for m in MODULES if not wanted or m[0] in wanted]
    if not modules:
        raise SystemExit("no such module: %s" % " ".join(wanted))
    if not os.path.exists(KERNEL):
        raise SystemExit("kernel not found: %s" % KERNEL)

    build_initrd()

    total_fail = 0
    missing = 0
    for name, desc in modules:
        fails, result = run_module(name, desc)
        if result is None:
            missing += 1
        total_fail += len(fails)

    print("\n=== SUMMARY ===", flush=True)
    print("modules: %d, failed checks: %d, missing logs: %d" %
          (len(modules), total_fail, missing), flush=True)
    return 1 if (total_fail or missing) else 0


if __name__ == "__main__":
    sys.exit(main())
