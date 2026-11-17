#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
#
# resctrl/MPAM coupling on a two-socket topology: multiple L3 monitor
# domains, per-domain files, and CPU hotplug taking a whole domain offline.

import errno
import os
import sys
import time

import mpam_suite_lib as L
from mpam_suite_lib import errname, read, read_int, try_mkdir, try_rmdir, \
    try_write

R = L.R
CPU = "/sys/devices/system/cpu"


def section(s):
    print("\n### %s" % s, flush=True)


def l3_mon_dirs():
    try:
        return [d for d in os.listdir(R + "/mon_data")
                if d.startswith("mon_L3_")]
    except OSError:
        return []


def online(cpu, value):
    return try_write("%s/cpu%d/online" % (CPU, cpu), "%d\n" % value)


def main():
    s = L.Suite("resctrl/MPAM coupling (topology)")
    rc = L.mount("debug", s)
    if rc:
        s.fail("mount resctrl -o debug", errname(rc))
        return s.summary()
    s.ok("mount resctrl -o debug")

    section("two-socket domains")
    doms = L.schemata_domains()
    s.check_eq("L3 has two domains", len(doms.get("L3", [])), 2)
    s.check_eq("L2 has four domains", len(doms.get("L2", [])), 4)
    s.check_eq("mon_data has two L3 domains", len(l3_mon_dirs()), 2)
    num_closids = read_int(L.INFO + "/L3/num_closids")
    num_rmids = read_int(L.INFO + "/L3_MON/num_rmids")
    s.check_eq("L3 num_closids", num_closids, 32)
    s.check("num_rmids covers every CLOSID",
            num_rmids >= num_closids and num_rmids % num_closids == 0,
            "num_rmids=%d num_closids=%d" % (num_rmids, num_closids))
    if "MB" in doms:
        s.info("MB schema exported with %d domain(s)" % len(doms["MB"]))
    else:
        s.info("MB schema not exported (multiple L3 domains)")

    # Per-domain monitor files on each L3 domain.
    for d in l3_mon_dirs():
        for ev in ("llc_occupancy", "mbm_total_bytes"):
            s.check("root %s/%s readable" % (d, ev),
                    read("%s/mon_data/%s/%s" % (R, d, ev), None) is not None)

    section("group and mon group across domains")
    s.check_eq("mkdir p1", try_mkdir(R + "/p1"), 0)
    s.check_eq("assign CPU4 to p1", try_write(R + "/p1/cpus", "10\n"), 0)
    s.check_eq("mkdir p1/m1", L.mkmon("p1", "m1"), 0)
    s.check_eq("assign CPU4 to p1/m1",
               try_write(R + "/p1/mon_groups/m1/cpus", "10\n"), 0)
    m1_dirs = [d for d in os.listdir(R + "/p1/mon_data")]
    s.check_eq("mon group has two domains", len(m1_dirs), 2)
    for d in m1_dirs:
        s.check("mon group %s/llc_occupancy readable" % d,
                read("%s/p1/mon_data/%s/llc_occupancy" % (R, d),
                     None) is not None)

    # Put an RMID in limbo so that taking the domain offline has to release
    # the per-domain busy bit.  With a small PMG count there is no room for
    # another mon group: free m1 instead.
    if L.mkmon("p1", "limbo") == 0:
        s.check_eq("rmdir p1/limbo",
                   try_rmdir(R + "/p1/mon_groups/limbo"), 0)
    else:
        s.info("no spare RMID for a second mon group; freeing m1 instead")
        s.check_eq("rmdir p1/m1",
                   try_rmdir(R + "/p1/mon_groups/m1"), 0)

    section("offline the second socket")
    for cpu in (4, 5, 6, 7):
        online(cpu, 0)
    time.sleep(1)
    s.check_eq("online CPUs are 0-3", read(CPU + "/online"), "0-3")
    s.check_eq("L3 domain removed", len(L.schemata_domains().get("L3", [])), 1)
    s.check_eq("L2 domains removed", len(L.schemata_domains().get("L2", [])), 2)
    s.check_eq("mon domain removed", len(l3_mon_dirs()), 1)
    s.check_eq("p1 lost the offline CPU", read(R + "/p1/cpus_list"), "")
    for d in l3_mon_dirs():
        s.check("surviving domain %s readable" % d,
                read("%s/mon_data/%s/llc_occupancy" % (R, d), None) is not None)

    for cpu in (4, 5, 6, 7):
        online(cpu, 1)
    time.sleep(1)
    s.check_eq("online CPUs restored", read(CPU + "/online"), "0-7")
    s.check_eq("L3 domain restored", len(L.schemata_domains().get("L3", [])), 2)
    s.check_eq("L2 domains restored", len(L.schemata_domains().get("L2", [])), 4)
    s.check_eq("mon domain restored", len(l3_mon_dirs()), 2)
    s.check_eq("online CPUs returned to root", read(R + "/cpus_list"), "0-7")
    s.check_eq("p1 did not regain the offline CPU",
               read(R + "/p1/cpus_list"), "")

    section("offline CPUs cannot be assigned")
    s.check_eq("offline CPU6", online(6, 0), 0)
    time.sleep(1)
    s.check_eq("assign offline CPU -> EINVAL",
               try_write(R + "/p1/cpus", "40\n"), errno.EINVAL, L.last_cmd())
    s.check_eq("online CPU6", online(6, 1), 0)
    time.sleep(1)

    L.umount(suite=s)
    return s.summary()


if __name__ == "__main__":
    sys.exit(main())
