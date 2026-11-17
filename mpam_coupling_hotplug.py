#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
#
# resctrl/MPAM coupling: CPU hotplug and domain lifetime.

import errno
import sys
import time

import mpam_suite_lib as L
from mpam_suite_lib import errname, read, try_mkdir, try_write

R = L.R
CPU = "/sys/devices/system/cpu"


def section(s):
    print("\n### %s" % s, flush=True)


def cpu_set(path):
    """Parse a cpus_list file ('0-3,5') into a set of ints."""
    out = set()
    for part in read(path).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            try:
                out.update(range(int(lo), int(hi) + 1))
            except ValueError:
                pass
        else:
            try:
                out.add(int(part))
            except ValueError:
                pass
    return out


def online(cpu, value):
    return try_write("%s/cpu%d/online" % (CPU, cpu), "%d\n" % value)


def dom_count(resource):
    return len(L.schemata_domains().get(resource, []))


def main():
    s = L.Suite("resctrl/MPAM coupling (hotplug)")
    rc = L.mount("debug", s)
    if rc:
        s.fail("mount resctrl -o debug", errname(rc))
        return s.summary()
    s.ok("mount resctrl -o debug")

    section("initial domains")
    s.check_eq("L2 has two domains", dom_count("L2"), 2)
    s.check_eq("L3 has one domain", dom_count("L3"), 1)
    s.check_eq("mon_data has one L3 domain",
               len([d for d in __import__("os").listdir(R + "/mon_data")
                    if d.startswith("mon_L3_")]), 1)

    section("CPU ownership and offline/online")
    s.check_eq("mkdir p1", try_mkdir(R + "/p1"), 0)
    s.check_eq("assign CPU3 to p1", try_write(R + "/p1/cpus", "8\n"), 0)
    s.check_eq("p1 owns CPU3", cpu_set(R + "/p1/cpus_list"), {3})
    s.check("root does not own CPU3", 3 not in cpu_set(R + "/cpus_list"),
            read(R + "/cpus_list"))

    s.check_eq("offline CPU3", online(3, 0), 0)
    time.sleep(1)
    s.check_eq("offline CPU leaves p1", cpu_set(R + "/p1/cpus_list"), set())
    s.check("root still excludes CPU3", 3 not in cpu_set(R + "/cpus_list"),
            read(R + "/cpus_list"))

    s.check_eq("online CPU3", online(3, 1), 0)
    time.sleep(1)
    s.check("online CPU returns to root", 3 in cpu_set(R + "/cpus_list"),
            read(R + "/cpus_list"))
    s.check_eq("p1 did not regain CPU3", cpu_set(R + "/p1/cpus_list"), set())

    section("offline a whole cache domain")
    s.check_eq("re-assign CPU3 to p1", try_write(R + "/p1/cpus", "8\n"), 0)
    for cpu in (4, 5, 6, 7):
        online(cpu, 0)
    time.sleep(1)
    s.check_eq("online CPUs are 0-3", read("/sys/devices/system/cpu/online"),
               "0-3")
    s.check_eq("L2 domain removed with its CPUs", dom_count("L2"), 1)
    s.check("L3 monitor still readable",
            (L.mon_read("", "llc_occupancy") or "").isdigit(),
            L.mon_read("", "llc_occupancy"))
    s.check_eq("p1 keeps its online CPU", cpu_set(R + "/p1/cpus_list"), {3})

    for cpu in (4, 5, 6, 7):
        online(cpu, 1)
    time.sleep(1)
    s.check_eq("online CPUs restored", read("/sys/devices/system/cpu/online"),
               "0-7")
    s.check_eq("L2 domain restored", dom_count("L2"), 2)

    section("offline CPUs cannot be assigned")
    s.check_eq("offline CPU5", online(5, 0), 0)
    time.sleep(1)
    s.check_eq("assign offline CPU -> EINVAL",
               try_write(R + "/p1/cpus", "20\n"), errno.EINVAL,
               L.last_cmd())
    s.check_eq("online CPU5", online(5, 1), 0)
    time.sleep(1)
    s.check_eq("assign CPU5 after online", try_write(R + "/p1/cpus", "28\n"), 0)
    s.check_eq("p1 cpus_list after online", cpu_set(R + "/p1/cpus_list"),
               {3, 5})

    L.umount(suite=s)
    return s.summary()


if __name__ == "__main__":
    sys.exit(main())
