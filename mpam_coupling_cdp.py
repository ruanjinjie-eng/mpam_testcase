#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
#
# resctrl/MPAM coupling: CDP (L3) and CDPL2 mount variants.
#
# MPAM cannot enable CDP per cache level: MPAM0_EL1 carries data and
# instruction PARTIDs for all traffic. The driver therefore treats a CDP
# mount as global and clones the non-CDP resource's configuration across
# both PARTIDs.

import errno
import os
import signal
import subprocess
import sys
import time

import mpam_suite_lib as L
from mpam_suite_lib import errname, read, read_int, try_mkdir, try_rmdir, \
    try_write, write_schemata

R = L.R


def section(s):
    print("\n### %s" % s, flush=True)


def mount_rc(opts):
    subprocess.call(["umount", R], stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
    os.makedirs(R, exist_ok=True)
    return subprocess.call(["mount", "-t", "resctrl", "resctrl", R,
                            "-o", opts], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)


def group_limit(s, tag):
    n = 0
    while n < 40:
        rc = try_mkdir("%s/%s%d" % (R, tag, n))
        if rc:
            break
        n += 1
    return n, rc


def spawn_sleeper():
    p = subprocess.Popen(["sleep", "600"])
    time.sleep(0.2)
    return p


def stop(p):
    try:
        p.send_signal(signal.SIGKILL)
        p.wait(timeout=2)
    except Exception:
        pass


def plain_ids():
    """Return the plain-mount (num_rmids, num_closids) for L3."""
    if mount_rc("debug"):
        return None, None
    rmids = read_int(L.INFO + "/L3_MON/num_rmids")
    closids = read_int(L.INFO + "/L3/num_closids")
    subprocess.call(["umount", R], stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
    return rmids, closids


def check_common(s, kind, exp_rmids, exp_closids):
    """Checks shared by the -o cdp and -o cdpl2 mounts."""
    resources = os.listdir(L.INFO)
    s.check("%s: L3_MON present" % kind, "L3_MON" in resources, str(resources))
    s.check("%s: MB hidden while CDP is on" % kind, "MB" not in resources,
            str(resources))
    s.check_eq("%s: num_rmids halved" % kind,
               read_int(L.INFO + "/L3_MON/num_rmids"), exp_rmids)
    cntrs = read(L.INFO + "/L3_MON/num_mbm_cntrs")
    s.check("%s: MBM counters halved" % kind, cntrs.endswith("=4"), cntrs)

    # Every CLOSID consumes a code/data PARTID pair, regardless of which
    # level requested CDP, so the CLOSID count is halved too.
    created, rc = group_limit(s, "g")
    s.check_eq("%s: control groups until exhaustion" % kind, created,
               exp_closids - 1,
               "created=%d last=%s" % (created, L.last_cmd()))
    s.check_eq("%s: exhaustion errno is ENOSPC" % kind, rc, errno.ENOSPC,
               errname(rc))


def check_cdp(s, exp_rmids, exp_closids):
    section("mount -o cdp")
    rc = mount_rc("debug,cdp")
    s.check_eq("mount -o cdp", rc, 0, errname(rc))
    if rc:
        return

    resources = os.listdir(L.INFO)
    for r in ("L2", "L3CODE", "L3DATA"):
        s.check("cdp: info/%s present" % r, r in resources, str(resources))
    s.check_eq("cdp: L3CODE num_closids",
               read_int(L.INFO + "/L3CODE/num_closids"), exp_closids)
    s.check_eq("cdp: L3DATA num_closids",
               read_int(L.INFO + "/L3DATA/num_closids"), exp_closids)
    # Per-schema reporting vs the system-wide CLOSID minimum is generic
    # resctrl behaviour (x86 reports the same); record it, don't fail.
    s.info("cdp: L2 num_closids reports %s while the system allows %d"
           % (read(L.INFO + "/L2/num_closids"), exp_closids))

    doms = L.schemata_domains()
    s.check("cdp: schemata has L3CODE/L3DATA/L2 and no MB",
            all(k in doms for k in ("L3CODE", "L3DATA", "L2")) and
            "MB" not in doms, str(doms))
    l3 = doms["L3CODE"][0]
    l2 = doms["L2"][0]
    s.check_eq("cdp: L3CODE write", write_schemata("", "L3CODE:%d=55555555\n"
                                                   % l3), 0)
    s.check_eq("cdp: L3DATA write", write_schemata("", "L3DATA:%d=aaaaaaaa\n"
                                                   % l3), 0)
    s.check_eq("cdp: L3CODE readback",
               L.schemata_value("", "L3CODE", l3), 0x55555555)
    s.check_eq("cdp: L3DATA readback",
               L.schemata_value("", "L3DATA", l3), 0xaaaaaaaa)
    s.check_eq("cdp: plain L3 name rejected",
               write_schemata("", "L3:%d=ffffffff\n" % l3), errno.EINVAL)
    s.check_eq("cdp: MB write rejected",
               write_schemata("", "MB:%d=50\n" % l3), errno.EINVAL)
    s.check_eq("cdp: L2 write", write_schemata("", "L2:%d=ffffffff\n" % l2), 0)

    check_common(s, "cdp", exp_rmids, exp_closids)

    # Keep only one group: the others already consumed every MBM counter.
    for i in range(1, exp_closids - 1):
        try_rmdir("%s/g%d" % (R, i))

    # Task labelling and monitoring under CDP.
    pos = max(0, read_int(R + "/g0/ctrl_hw_id"))
    s.check("cdp: CLOSID within the halved range", 0 <= pos < exp_closids,
            "closid=%d" % pos)
    s.check_eq("cdp: mon group create", L.mkmon("g0", "m"), 0)
    sleeper = spawn_sleeper()
    s.check_eq("cdp: task to control group",
               try_write(R + "/g0/tasks", "%d\n" % sleeper.pid), 0)
    s.check_eq("cdp: task to mon group",
               try_write(R + "/g0/mon_groups/m/tasks", "%d\n" % sleeper.pid),
               0)
    s.check("cdp: llc_occupancy readable",
            (L.mon_read("g0/mon_groups/m", "llc_occupancy") or "").isdigit(),
            L.mon_read("g0/mon_groups/m", "llc_occupancy"))
    s.check("cdp: mbm_total_bytes readable",
            (L.mon_read("g0/mon_groups/m", "mbm_total_bytes")
             or "").isdigit(),
            L.mon_read("g0/mon_groups/m", "mbm_total_bytes"))
    stop(sleeper)

    # A CDP mount with groups and dirty RMIDs must remount cleanly.
    s.info("cdp: unmount/remount with live groups")
    L.umount(drain=False, suite=s)
    rc = mount_rc("debug,cdp")
    s.check_eq("cdp: remount after unclean unmount", rc, 0, errname(rc))
    if rc == 0:
        s.check("cdp: remounted schemata valid",
                "L3CODE" in L.schemata_domains(), str(L.schemata_domains()))


def check_cdpl2(s, exp_rmids, exp_closids):
    section("mount -o cdpl2")
    rc = mount_rc("debug,cdpl2")
    s.check_eq("mount -o cdpl2", rc, 0, errname(rc))
    if rc:
        return

    resources = os.listdir(L.INFO)
    for r in ("L2CODE", "L2DATA", "L3"):
        s.check("cdpl2: info/%s present" % r, r in resources, str(resources))
    s.check_eq("cdpl2: L2CODE num_closids",
               read_int(L.INFO + "/L2CODE/num_closids"), exp_closids)
    s.check_eq("cdpl2: L2DATA num_closids",
               read_int(L.INFO + "/L2DATA/num_closids"), exp_closids)
    s.info("cdpl2: L3 num_closids reports %s while the system allows %d"
           % (read(L.INFO + "/L3/num_closids"), exp_closids))

    doms = L.schemata_domains()
    s.check("cdpl2: schemata has L2CODE/L2DATA/L3 and no MB",
            all(k in doms for k in ("L2CODE", "L2DATA", "L3")) and
            "MB" not in doms, str(doms))
    l3 = doms["L3"][0]
    l2 = doms["L2CODE"][0]
    s.check_eq("cdpl2: L2CODE write",
               write_schemata("", "L2CODE:%d=55555555\n" % l2), 0)
    s.check_eq("cdpl2: L2DATA write",
               write_schemata("", "L2DATA:%d=aaaaaaaa\n" % l2), 0)
    s.check_eq("cdpl2: L2CODE readback",
               L.schemata_value("", "L2CODE", l2), 0x55555555)
    s.check_eq("cdpl2: L2DATA readback",
               L.schemata_value("", "L2DATA", l2), 0xaaaaaaaa)
    s.check_eq("cdpl2: L3 write", write_schemata("", "L3:%d=ffffffff\n" % l3),
               0)
    s.check_eq("cdpl2: plain L2 name rejected",
               write_schemata("", "L2:%d=ffffffff\n" % l2), errno.EINVAL)

    check_common(s, "cdpl2", exp_rmids, exp_closids)


def check_both(s, exp_closids):
    section("mount -o cdp,cdpl2")
    rc = mount_rc("debug,cdp,cdpl2")
    s.check_eq("mount -o cdp,cdpl2", rc, 0, errname(rc))
    if rc:
        return
    doms = L.schemata_domains()
    s.check("cdp+cdpl2: all cache schemas are CODE/DATA",
            set(doms) == {"L3CODE", "L3DATA", "L2CODE", "L2DATA"}, str(doms))
    created, rc = group_limit(s, "b")
    s.check_eq("cdp+cdpl2: control groups until exhaustion", created,
               exp_closids - 1,
               "created=%d last=%s" % (created, L.last_cmd()))


def check_bad_mounts(s):
    section("bad mount options")
    rc = mount_rc("debug,mba_MBps")
    s.check("mba_MBps rejected (assignable counters)", rc != 0, "rc=%d" % rc)
    rc = mount_rc("debug,bogusopt")
    s.check("unknown mount option rejected", rc != 0, "rc=%d" % rc)


def main():
    s = L.Suite("resctrl/MPAM coupling (CDP)")
    base_rmids, base_closids = plain_ids()
    if not base_rmids or not base_closids:
        s.fail("plain mount for CDP baselines", "rmids=%s closids=%s" %
               (base_rmids, base_closids))
        return s.summary()
    exp_rmids = base_rmids // 2
    exp_closids = base_closids // 2
    s.info("plain baseline: num_rmids=%d num_closids=%d" %
           (base_rmids, base_closids))

    check_cdp(s, exp_rmids, exp_closids)
    check_cdpl2(s, exp_rmids, exp_closids)
    check_both(s, exp_closids)
    check_bad_mounts(s)

    # Leave the guest in a plain debug mount.
    L.mount("debug", s)
    L.umount(suite=s)
    return s.summary()


if __name__ == "__main__":
    sys.exit(main())
