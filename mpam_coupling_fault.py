#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
#
# resctrl/MPAM coupling: allocation-failure paths via failslab.
#
# Sweeps the failure position across the allocations of one syscall
# (interval=N, times=1, probability=100) and checks that each failure is
# reported cleanly, leaves no partial state, and does not warn.

import ctypes
import errno
import os
import subprocess
import sys

import mpam_suite_lib as L
from mpam_suite_lib import errname, read, try_mkdir, try_rmdir, try_write

R = L.R
FI = "/sys/kernel/debug/failslab"
MAKE_IT_FAIL = "/proc/self/make-it-fail"

LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.mount.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                       ctypes.c_ulong, ctypes.c_char_p]
LIBC.mount.restype = ctypes.c_int


def section(s):
    print("\n### %s" % s, flush=True)


FDS = {}


def fi_available():
    return os.path.exists(FI + "/probability") and os.path.exists(MAKE_IT_FAIL)


def fi_open():
    for name in ("probability", "interval", "times", "task-filter",
                 "ignore-gfp-wait", "verbose"):
        FDS[name] = os.open(FI + "/" + name, os.O_WRONLY)
    FDS["make"] = os.open(MAKE_IT_FAIL, os.O_WRONLY)


def fi_close():
    for fd in FDS.values():
        try:
            os.close(fd)
        except OSError:
            pass
    FDS.clear()


def fi_write(name, value):
    # debugfs fault attributes are not seekable; their write handlers ignore
    # the file position, so keep the pre-opened fd and just write.
    os.write(FDS[name], value.encode())


def fi_reset():
    fi_write("probability", "0\n")
    fi_write("times", "0\n")
    fi_write("interval", "1\n")
    fi_write("task-filter", "N\n")
    # failslab ignores GFP_DIRECT_RECLAIM allocations by default; almost all
    # resctrl allocations use GFP_KERNEL, so include them.
    fi_write("ignore-gfp-wait", "N\n")
    # Keep the console quiet; the test checks for real warnings instead.
    fi_write("verbose", "0\n")
    fi_write("make", "0\n")


def fi_arm(interval):
    fi_reset()
    fi_write("interval", "%d\n" % interval)
    fi_write("task-filter", "Y\n")
    fi_write("make", "1\n")
    fi_write("times", "-1\n")
    fi_write("probability", "100\n")


def fi_disarm():
    # Drop probability first so the pre-opened fd writes cannot themselves
    # be failed by the still-armed injection.
    fi_write("probability", "0\n")
    fi_write("times", "0\n")
    fi_write("task-filter", "N\n")
    fi_write("make", "0\n")


def dmesg_new(before):
    out = subprocess.run(["dmesg"], capture_output=True, text=True)
    lines = out.stdout.splitlines()
    new = lines[before:]
    return [ln for ln in new
            if "WARNING:" in ln or "BUG:" in ln or "list_add" in ln or
            "corruption" in ln or "Call trace" in ln]


def sweep_read(s):
    section("monitor read allocation failures")
    path = L.mon_data_dir("") + "/llc_occupancy"
    fd = os.open(path, os.O_RDONLY)
    probe = os.pread(fd, 256, 0).decode().strip()
    s.check("monitor read works before injection", probe.isdigit(), probe)
    bad = []
    values = []
    for k in range(1, 17):
        fi_arm(k)
        try:
            v = os.pread(fd, 256, 0).decode().strip()
        except OSError as e:
            # The read syscall failed cleanly with an errno; no partial value.
            v = errname(e.errno)
        fi_disarm()
        values.append(v)
        if v not in ("Unavailable", "Error", "Unassigned") and \
           not v.isdigit() and not v.startswith("E"):
            bad.append("k=%d v=%r" % (k, v))
    os.close(fd)
    s.check("monitor read failures are reported cleanly", not bad, str(bad))
    s.check("failslab reached an allocation failure in the read path",
            any(not (v or "").isdigit() for v in values), str(values))
    s.check("monitor read recovers after disarm",
            (read(path, None) or "").isdigit(), read(path, None))


def sweep_mkdir(s):
    section("control/monitor group mkdir allocation failures")
    ok = []
    for k in range(1, 10):
        fi_arm(k)
        rc = try_mkdir(R + "/f%d" % k)
        fi_disarm()
        ok.append("%d:%s" % (k, errname(rc) if rc else "ok"))
        if rc == 0:
            try_rmdir(R + "/f%d" % k)
    s.info("ctrl mkdir sweep: %s" % ", ".join(ok))
    s.check_eq("ctrl mkdir works after disarm", try_mkdir(R + "/fok"), 0)
    s.check_eq("mkdir fok/m", L.mkmon("fok", "m"), 0)

    # Use a fresh control group per attempt: with a small PMG count an
    # existing control group may have no free RMID for a monitor group,
    # which would mask the allocation-failure path being tested.
    ok = []
    for k in range(1, 10):
        parent = "mp%d" % k
        if try_mkdir("%s/%s" % (R, parent)):
            continue
        fi_arm(k)
        rc = L.mkmon(parent, "m")
        fi_disarm()
        ok.append("%d:%s" % (k, errname(rc) if rc else "ok"))
        try_rmdir("%s/%s" % (R, parent))
    s.info("mon mkdir sweep: %s" % ", ".join(ok))
    rc = try_mkdir(R + "/fok2")
    s.check_eq("mon mkdir works after disarm", rc, 0)
    if rc == 0:
        s.check_eq("mon mkdir after disarm creates the group",
                   L.mkmon("fok2", "m"), 0)


def sweep_tasks_cpus(s):
    section("tasks/cpus write allocation failures")
    ok = []
    for k in range(1, 6):
        fi_arm(k)
        rc = try_write(R + "/fok/cpus", "10\n")
        fi_disarm()
        ok.append("%d:%s" % (k, errname(rc) if rc else "ok"))
        if rc == 0:
            try_write(R + "/fok/cpus", "0\n")
    s.info("cpus write sweep: %s" % ", ".join(ok))
    s.check_eq("cpus write works after disarm",
               try_write(R + "/fok/cpus", "10\n"), 0)
    s.check_eq("reset cpus", try_write(R + "/fok/cpus", "0\n"), 0)


def sweep_rename(s):
    section("monitor group rename allocation failures")
    # A fresh source/destination pair per attempt: reparenting allocates an
    # RMID in the destination CLOSID, and with a small PMG count moving the
    # group back would need an RMID that is still in limbo.
    ok = []
    for k in range(1, 8):
        srcp = "rsrc%d" % k
        dstp = "rdst%d" % k
        if try_mkdir("%s/%s" % (R, srcp)):
            continue
        if try_mkdir("%s/%s" % (R, dstp)):
            try_rmdir("%s/%s" % (R, srcp))
            continue
        if L.mkmon(srcp, "rm"):
            try_rmdir("%s/%s" % (R, srcp))
            try_rmdir("%s/%s" % (R, dstp))
            continue
        src = "%s/%s/mon_groups/rm" % (R, srcp)
        dst = "%s/%s/mon_groups/rm" % (R, dstp)
        fi_arm(k)
        try:
            os.rename(src, dst)
            rc = 0
        except OSError as e:
            rc = e.errno
        fi_disarm()
        ok.append("%d:%s" % (k, errname(rc) if rc else "ok"))
        if rc != 0:
            s.check("failed rename left the source in place",
                    os.path.isdir(src))
        try_rmdir("%s/%s" % (R, srcp))
        try_rmdir("%s/%s" % (R, dstp))
    s.info("rename sweep: %s" % ", ".join(ok))
    fi_disarm()
    try_mkdir(R + "/rdst")
    try_mkdir(R + "/rsrc")
    L.mkmon("rsrc", "rm")
    src = R + "/rsrc/mon_groups/rm"
    dst = R + "/rdst/mon_groups/rm"
    try:
        os.rename(src, dst)
        rc = 0
    except OSError as e:
        rc = e.errno
    s.check_eq("rename works after disarm", rc, 0, errname(rc))


def sweep_mount(s):
    section("mount allocation failures")
    L.umount(drain=True, suite=s)
    results = []
    target = R.encode()
    source = b"resctrl"
    fstype = b"resctrl"
    data = b"debug"
    for k in range(1, 15):
        fi_arm(k)
        # Call mount(2) directly: spawning a subprocess while injection is
        # armed can fail in the parent's fork/exec path instead.
        rc = LIBC.mount(source, target, fstype, 0, data)
        fi_disarm()
        results.append("%d:%s" % (k, "ok" if rc == 0 else "fail"))
        if rc == 0:
            L.umount(drain=False, suite=s)
        elif L.mounted():
            s.fail("mount reported failure but resctrl is mounted")
            L.umount(drain=False, suite=s)
    s.info("mount sweep: %s" % ", ".join(results))
    rc = L.mount("debug", s)
    s.check_eq("mount works after disarm", rc, 0, errname(rc))


def main():
    s = L.Suite("resctrl/MPAM coupling (fault injection)")
    if not fi_available():
        s.info("failslab not available (kernel without CONFIG_FAILSLAB); "
               "skipping")
        return s.summary()

    fi_open()
    before = len(subprocess.run(["dmesg"], capture_output=True,
                                text=True).stdout.splitlines())
    fi_reset()

    rc = L.mount("debug", s)
    if rc:
        s.fail("mount resctrl -o debug", errname(rc))
        return s.summary()
    s.ok("mount resctrl -o debug")

    sweep_read(s)
    sweep_mkdir(s)
    sweep_tasks_cpus(s)
    sweep_rename(s)
    sweep_mount(s)

    fi_disarm()
    fi_close()
    warn = dmesg_new(before)
    s.check("fault injection produced no kernel warnings", not warn,
            str(warn[:4]))

    L.umount(suite=s)
    return s.summary()


if __name__ == "__main__":
    sys.exit(main())
