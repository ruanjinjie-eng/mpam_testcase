#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
#
# resctrl/MPAM coupling limits: CLOSID exhaustion and per-CLOSID RMID
# exhaustion, including the retryable -EBUSY report for a temporary shortage.

import errno
import sys
import time

import mpam_suite_lib as L
from mpam_suite_lib import errname, read_int, try_mkdir, try_rmdir, \
    try_write

R = L.R


def section(s):
    print("\n### %s" % s, flush=True)


def count_ctrl_groups(s):
    n = 0
    while n < 64:
        rc = try_mkdir("%s/g%d" % (R, n))
        if rc:
            return n, rc
        n += 1
    return n, 0


def check_closid_limit(s):
    section("CLOSID exhaustion")
    num_closids = read_int(L.INFO + "/L3/num_closids")
    num_rmids = read_int(L.INFO + "/L3_MON/num_rmids")
    s.check("num_closids reported", num_closids > 0, str(num_closids))

    created, rc = count_ctrl_groups(s)
    # Root owns RESCTRL_RESERVED_CLOSID.
    s.check_eq("control groups until exhaustion", created, num_closids - 1,
               "created=%d num_closids=%d" % (created, num_closids))
    s.check_eq("exhaustion errno is ENOSPC", rc, errno.ENOSPC, errname(rc))
    s.check("last_cmd_status says CLOSIDs", "CLOSID" in L.last_cmd(),
            L.last_cmd())

    # Freeing a group makes the CLOSID re-usable.
    s.check_eq("free one control group",
               try_rmdir("%s/g0" % R), 0)
    s.check_eq("CLOSID re-used", try_mkdir(R + "/reuse"), 0)
    s.check("reused group has a valid CLOSID", L.hw_ids("reuse")[0] > 0,
            str(L.hw_ids("reuse")))

    # Keep the RMID index space in mind for the next section.
    s.info("num_rmids=%d num_closids=%d pmg_max=%d" %
           (num_rmids, num_closids,
            num_rmids // num_closids - 1))


def wait_alloc(parent, name, timeout=20):
    """Create parent+mon, retrying while limbo RMIDs drain."""
    deadline = time.time() + timeout
    rc = errno.EBUSY
    while time.time() < deadline:
        rc = try_mkdir("%s/%s" % (R, parent))
        if rc and rc != errno.EEXIST:
            time.sleep(1)
            continue
        rc = L.mkmon(parent, name)
        if rc == 0:
            return 0
        time.sleep(1)
    return rc


def check_rmid_limit(s):
    section("per-CLOSID RMID exhaustion")
    num_closids = read_int(L.INFO + "/L3/num_closids")
    num_rmids = read_int(L.INFO + "/L3_MON/num_rmids")
    pmg_max = num_rmids // num_closids - 1
    s.check("PMG count is discoverable", pmg_max >= 0,
            "num_rmids=%d num_closids=%d" % (num_rmids, num_closids))

    # Let the RMIDs from the CLOSID test drain first: with a small PMG count
    # a single dirty RMID already blocks a new monitor group in its CLOSID.
    limit = L.cache_size(3)
    s.info("L3 size=%d initial max_threshold_occupancy=%s" %
           (limit, L.read(L.INFO + "/L3_MON/max_threshold_occupancy")))
    if limit:
        try_write(L.INFO + "/L3_MON/max_threshold_occupancy", "%d\n" % limit)
    rc = wait_alloc("rmid", "m0")
    s.check_eq("mon group allocated after limbo drains", rc, 0,
               "rc=%s last=%s" % (errname(rc), L.last_cmd()))

    # Keep the limbo entries dirty for the EBUSY check below. QEMU reports
    # a non-zero occupancy for every RMID, so a zero threshold prevents the
    # handler from ever releasing them.
    try_write(L.INFO + "/L3_MON/max_threshold_occupancy", "0\n")

    created = 0 if rc else 1
    while created < pmg_max + 8:
        rc = L.mkmon("rmid", "m%d" % created)
        if rc:
            break
        created += 1
    # The control group itself consumes one RMID of this CLOSID.
    s.check_eq("mon groups until per-CLOSID exhaustion", created, pmg_max,
               "created=%d pmg_max=%d" % (created, pmg_max))
    s.check_eq("exhaustion errno is ENOSPC", rc, errno.ENOSPC, errname(rc))
    s.check("last_cmd_status says RMIDs", "RMID" in L.last_cmd(), L.last_cmd())

    # Free them all: the RMIDs go to limbo. This CLOSID has no free RMID but
    # the shared free list still holds other CLOSIDs' RMIDs, so the shortage
    # is temporary and must be reported as -EBUSY, not -ENOSPC.
    for i in range(created):
        try_rmdir("%s/rmid/mon_groups/m%d" % (R, i))
    rc = L.mkmon("rmid", "after")
    s.check_eq("temporary per-CLOSID shortage reports EBUSY", rc,
               errno.EBUSY,
               "rc=%s last=%s" % (errname(rc), L.last_cmd()))

    # Another CLOSID is unaffected.
    s.check_eq("mkdir second parent", try_mkdir(R + "/rmid2"), 0)
    rc = L.mkmon("rmid2", "other")
    s.check_eq("other CLOSID still allocates", rc, 0,
               "rc=%s last=%s" % (errname(rc), L.last_cmd()))

    # Raising max_threshold_occupancy lets the limbo worker release the
    # entries, after which this CLOSID allocates again.
    s.check_eq("raise max_threshold_occupancy", try_write(L.INFO +
               "/L3_MON/max_threshold_occupancy", "%d\n" % limit), 0)
    rc = wait_alloc("rmid", "late")
    s.check_eq("allocation succeeds after limbo drains", rc, 0,
               "rc=%s last=%s" % (errname(rc), L.last_cmd()))

    # A defunct group's RMID is returned when the group is removed.
    if rc == 0:
        s.check_eq("rmdir drained mon group",
                   try_rmdir(R + "/rmid/mon_groups/late"), 0)
    s.check_eq("mkdir short-lived mon group", wait_alloc("rmid", "short"), 0,
               "last=%s" % L.last_cmd())
    s.check_eq("rmdir short-lived mon group",
               try_rmdir(R + "/rmid/mon_groups/short"), 0)
    s.check_eq("RMID reusable after rmdir", wait_alloc("rmid", "reuse"), 0,
               "last=%s" % L.last_cmd())


def main():
    s = L.Suite("resctrl/MPAM coupling (limits)")
    rc = L.mount("debug", s)
    if rc:
        s.fail("mount resctrl -o debug", errname(rc))
        return s.summary()
    s.ok("mount resctrl -o debug")

    # CLOSID exhaustion first: it needs the cleanest CLOSID map.
    check_closid_limit(s)

    # A fresh mount avoids the 31 groups above consuming RMIDs.
    rc = L.mount("debug", s)
    if rc:
        s.fail("remount for RMID tests", errname(rc))
        return s.summary()
    check_rmid_limit(s)

    L.umount(suite=s)
    return s.summary()


if __name__ == "__main__":
    sys.exit(main())
