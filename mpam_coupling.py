#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
#
# resctrl/MPAM coupling coverage: controls, groups, tasks, monitors and
# monitor-group reparenting on the plain (non-CDP) mount.

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


def spawn_sleeper():
    p = subprocess.Popen(["sleep", "600"])
    time.sleep(0.2)
    return p


def stop(p):
    if not p:
        return
    try:
        p.send_signal(signal.SIGKILL)
        p.wait(timeout=2)
    except Exception:
        pass


def check_info(s):
    section("info surface")
    resources = os.listdir(L.INFO)
    for r in ("L2", "L3", "MB", "L3_MON"):
        s.check("info/%s present" % r, r in resources,
                "have=%s" % resources)
    s.check_eq("L3 num_closids", read_int(L.INFO + "/L3/num_closids"), 32)
    s.check_eq("L2 num_closids", read_int(L.INFO + "/L2/num_closids"), 32)
    s.check_eq("MB num_closids", read_int(L.INFO + "/MB/num_closids"), 32)
    num_rmids = read_int(L.INFO + "/L3_MON/num_rmids")
    s.check("L3 num_rmids is positive", num_rmids > 0, str(num_rmids))
    s.check("num_rmids is a whole number of CLOSIDs",
            num_rmids % read_int(L.INFO + "/L3/num_closids") == 0,
            "num_rmids=%d" % num_rmids)
    feats = read(L.INFO + "/L3_MON/mon_features").split()
    s.check("mon_features has llc_occupancy", "llc_occupancy" in feats,
            str(feats))
    s.check("mon_features has mbm_total_bytes", "mbm_total_bytes" in feats,
            str(feats))
    s.check("mbm_assign_mode reports mbm_event",
            "mbm_event" in read(L.INFO + "/L3_MON/mbm_assign_mode"))
    s.check_eq("L3 cbm_mask", read(L.INFO + "/L3/cbm_mask"), "ffffffff")
    s.check_eq("L3 min_cbm_bits", read_int(L.INFO + "/L3/min_cbm_bits"), 1)
    s.check_eq("L3 sparse_masks", read_int(L.INFO + "/L3/sparse_masks"), 1)
    s.check("L3 shareable_bits", read(L.INFO + "/L3/shareable_bits") != "")
    s.check("L2 has two domains",
            len(L.schemata_domains().get("L2", [])) == 2,
            str(L.schemata_domains()))
    s.check("L3 has one domain",
            len(L.schemata_domains().get("L3", [])) == 1,
            str(L.schemata_domains()))
    s.check("MB shares the L3 domain",
            L.schemata_domains().get("MB") == L.schemata_domains().get("L3"),
            str(L.schemata_domains()))

    s.check_eq("MB bandwidth_gran",
               read_int(L.INFO + "/MB/bandwidth_gran"), 1)
    s.check_eq("MB delay_linear", read_int(L.INFO + "/MB/delay_linear"), 1)
    s.check_eq("MB min_bandwidth", read_int(L.INFO + "/MB/min_bandwidth"), 0)
    s.check_eq("L2 cbm_mask", read(L.INFO + "/L2/cbm_mask"), "ffffffff")
    s.check("available_mbm_cntrs reports a domain",
            "=" in read(L.INFO + "/L3_MON/available_mbm_cntrs"))
    s.check("num_mbm_cntrs reports a domain",
            "=" in read(L.INFO + "/L3_MON/num_mbm_cntrs"))

    # Read every info file, exercising the resctrl info show paths.
    for root, _, files in os.walk(L.INFO):
        for name in files:
            path = os.path.join(root, name)
            s.check("info file readable: %s" % path[len(R) + 1:],
                    read(path, None) is not None)

    # resctrl can only be mounted once.
    rc = subprocess.call(["mount", "-t", "resctrl", "resctrl", R],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    s.check("second mount fails", rc != 0, "rc=%d" % rc)


def check_schemata(s):
    section("schemata controls")
    l3 = L.schemata_domains()["L3"][0]
    l2 = L.schemata_domains()["L2"][0]
    mb = L.schemata_domains()["MB"][0]
    width = L.cbm_len("L3")
    full = (1 << width) - 1
    half = int("55555555" if width == 32 else
               ("5" * (width // 4)), 16)

    s.check_eq("mkdir p1", try_mkdir(R + "/p1"), 0)
    s.check_eq("L3 sparse bitmap write", write_schemata("p1",
               "L3:%d=%x\n" % (l3, half)), 0)
    s.check_eq("L3 sparse bitmap readback",
               L.schemata_value("p1", "L3", l3), half)
    s.check_eq("L2 bitmap write", write_schemata("p1",
               "L2:%d=%x\n" % (l2, half)), 0)
    s.check_eq("L2 bitmap readback (written domain)",
               L.schemata_value("p1", "L2", l2), half)
    s.check_eq("L2 untouched domain keeps default",
               L.schemata_value("p1", "L2", L.schemata_domains()["L2"][1]),
               full)
    s.check_eq("MB percentage write", write_schemata("p1",
               "MB:%d=25\n" % mb), 0)
    s.check_eq("MB percentage readback", L.schemata_value("p1", "MB", mb), 25)

    # size file mirrors the CBM in bytes.
    size = L.cache_size(3)
    try:
        p1size = int(read(R + "/p1/size").splitlines()[2].split("=")[1])
    except (IndexError, ValueError):
        p1size = -1
    s.check_eq("size reflects CBM", p1size, size * bin(half).count("1") // width,
               "got=%d cache=%d" % (p1size, size))
    s.check("bit_usage readable", read(L.INFO + "/L3/bit_usage") != "")

    # Boundaries and multi-domain forms.
    s.check_eq("MB zero accepted", write_schemata("p1", "MB:%d=0\n" % mb), 0)
    s.check_eq("MB zero readback", L.schemata_value("p1", "MB", mb), 0)
    s.check_eq("MB 100 accepted", write_schemata("p1", "MB:%d=100\n" % mb), 0)
    s.check_eq("MB 100 readback", L.schemata_value("p1", "MB", mb), 100)
    s.check_eq("non-contiguous CBM accepted",
               write_schemata("p1", "L3:%d=80000001\n" % l3), 0)
    s.check_eq("non-contiguous CBM readback",
               L.schemata_value("p1", "L3", l3), 0x80000001)
    s.check_eq("uppercase hex accepted",
               write_schemata("p1", "L3:%d=AAAAAAAA\n" % l3), 0)
    s.check_eq("uppercase hex readback",
               L.schemata_value("p1", "L3", l3), 0xaaaaaaaa)
    s.check_eq("trailing spaces accepted",
               write_schemata("p1", "L3:%d=%x   \n" % (l3, half)), 0)
    l2s = L.schemata_domains()["L2"]
    s.check_eq("both L2 domains in one line", write_schemata("p1",
               "L2:%d=%x;%d=%x\n" % (l2s[0], 0x33333333,
                                     l2s[1], 0xcccccccc)), 0)
    s.check_eq("L2 domain 0 readback", L.schemata_value("p1", "L2", l2s[0]),
               0x33333333)
    s.check_eq("L2 domain 1 readback", L.schemata_value("p1", "L2", l2s[1]),
               0xcccccccc)
    rc = write_schemata("p1", "L2:%d=11111111;999=22222222\n" % l2s[0])
    s.check_eq("bad domain rejects whole write", rc, errno.EINVAL)
    s.check_eq("valid domain not applied on failure",
               L.schemata_value("p1", "L2", l2s[0]), 0x33333333)

    # Invalid inputs.
    cases = [
        ("zero mask", "L3:%d=0\n" % l3, errno.EINVAL),
        ("mask too wide", "L3:%d=1%08x\n" % (l3, full), errno.EINVAL),
        ("duplicate domain", "L3:%d=%x;%d=%x\n" % (l3, half, l3, half),
         errno.EINVAL),
        ("unknown domain", "L3:999=%x\n" % full, errno.EINVAL),
        ("unknown resource", "BOGUS:0=1\n", errno.EINVAL),
        ("missing colon", "L3 %d=%x\n" % (l3, full), errno.EINVAL),
        ("missing value", "L3:\n", errno.EINVAL),
        ("missing newline", "L3:%d=%x" % (l3, full), errno.EINVAL),
        ("blank line", "L3:%d=%x\n\n" % (l3, full), errno.EINVAL),
        ("MB out of range", "MB:%d=101\n" % mb, errno.EINVAL),
        ("MB hex rejected", "MB:%d=0x10\n" % mb, errno.EINVAL),
        ("MB negative", "MB:%d=-1\n" % mb, errno.EINVAL),
    ]
    for name, text, want in cases:
        rc = write_schemata("p1", text)
        s.check_eq("invalid schemata: %s -> EINVAL" % name, rc, want,
                   "rc=%s last=%s" % (errname(rc), L.last_cmd()))

    # A failed multi-resource write must not apply the valid part.
    write_schemata("p1", "L3:%d=%x\n" % (l3, half))
    rc = write_schemata("p1", "L2:%d=%x\nBOGUS:0=1\n" % (l2, full))
    s.check_eq("partial schemata write rejected", rc, errno.EINVAL)
    s.check_eq("partial write left prior config",
               L.schemata_value("p1", "L3", l3), half)


def check_groups(s):
    section("group lifecycle")
    s.check_eq("duplicate ctrl group -> EEXIST", try_mkdir(R + "/p1"),
               errno.EEXIST)
    s.check_eq("ctrlgroups cannot nest -> EPERM", try_mkdir(R + "/p1/sub"),
               errno.EPERM)
    s.check_eq("mon group create", L.mkmon("p1", "m1"), 0)
    s.check_eq("mon group named mon_groups rejected",
               L.mkmon("p1", "mon_groups"), errno.EPERM)
    s.check_eq("duplicate mon group -> EEXIST", L.mkmon("p1", "m1"),
               errno.EEXIST)

    cid, mid = L.hw_ids("p1")
    _, mid1 = L.hw_ids("p1/mon_groups/m1")
    s.check("ctrl_hw_id is unique and nonzero", cid > 0, "closid=%d" % cid)
    # Monitor groups have no CLOSID of their own; mon_hw_id is the RMID/PMG
    # they inherit from the parent. Only ctrl groups expose ctrl_hw_id.
    s.check_eq("mon group has no ctrl_hw_id",
               read_int(R + "/p1/mon_groups/m1/ctrl_hw_id"), -1)
    s.check("mon_hw_id in PMG range", 0 <= mid1 <= L.pmg_max(),
            "rmid=%d pmg_max=%d" % (mid1, L.pmg_max()))

    s.check_eq("mkdir p2", try_mkdir(R + "/p2"), 0)
    s.check("p2 has a different CLOSID", L.hw_ids("p2")[0] != cid,
            "p1=%d p2=%d" % (cid, L.hw_ids("p2")[0]))

    # rmdir gives tasks and child mon groups back.
    sleeper = spawn_sleeper()
    s.check_eq("task to p2", try_write(R + "/p2/tasks",
               "%d\n" % sleeper.pid), 0)
    s.check_eq("rmdir ctrl group with a task", try_rmdir(R + "/p2"), 0)
    s.check("task moved back to root on rmdir",
            str(sleeper.pid) in read(R + "/tasks").split())
    stop(sleeper)

    s.check_eq("mode unknown -> EINVAL", try_write(R + "/p1/mode", "bogus\n"),
               errno.EINVAL)
    s.check_eq("mode shareable", try_write(R + "/p1/mode", "shareable\n"), 0)
    s.check_eq("mode exclusive with overlap -> EINVAL",
               try_write(R + "/p1/mode", "exclusive\n"), errno.EINVAL)
    s.check_eq("mode pseudo-locked unsupported -> EINVAL",
               try_write(R + "/p1/mode", "pseudo-locked\n"), errno.EINVAL)

    # Cascade removal: a mon group gives its tasks and CPUs back to its
    # parent, a ctrl group gives both back to the root group.
    task = spawn_sleeper()
    s.check_eq("mkdir c1", try_mkdir(R + "/c1"), 0)
    s.check_eq("mkdir c1/cm", L.mkmon("c1", "cm"), 0)
    s.check_eq("assign CPU4 to c1", try_write(R + "/c1/cpus", "10\n"), 0)
    s.check_eq("assign CPU4 to c1/cm",
               try_write(R + "/c1/mon_groups/cm/cpus", "10\n"), 0)
    s.check_eq("task to c1", try_write(R + "/c1/tasks",
               "%d\n" % task.pid), 0)
    s.check_eq("task to c1/cm", try_write(R + "/c1/mon_groups/cm/tasks",
               "%d\n" % task.pid), 0)
    s.check_eq("rmdir mon group with task and CPU",
               try_rmdir(R + "/c1/mon_groups/cm"), 0)
    s.check("mon rmdir returns task to parent",
            str(task.pid) in read(R + "/c1/tasks").split())
    s.check_eq("mon rmdir leaves CPU with parent",
               read(R + "/c1/cpus_list"), "4")
    s.check_eq("rmdir ctrl group", try_rmdir(R + "/c1"), 0)
    s.check("ctrl rmdir returns task to root",
            str(task.pid) in read(R + "/tasks").split())
    stop(task)

    # A ctrl group with a live mon group child is removed recursively.
    task = spawn_sleeper()
    s.check_eq("mkdir c2", try_mkdir(R + "/c2"), 0)
    s.check_eq("mkdir c2/cm", L.mkmon("c2", "cm"), 0)
    s.check_eq("task to c2", try_write(R + "/c2/tasks",
               "%d\n" % task.pid), 0)
    s.check_eq("task to c2/cm", try_write(R + "/c2/mon_groups/cm/tasks",
               "%d\n" % task.pid), 0)
    s.check_eq("rmdir ctrl group with a mon group child",
               try_rmdir(R + "/c2"), 0)
    s.check("cascade rmdir returns task to root",
            str(task.pid) in read(R + "/tasks").split())
    stop(task)

    # Moving a CPU between mon groups, and changing the parent's CPU mask,
    # both update the child masks.
    s.check_eq("mkdir c3", try_mkdir(R + "/c3"), 0)
    s.check_eq("assign CPU4-5 to c3", try_write(R + "/c3/cpus", "30\n"), 0)
    s.check_eq("mkdir c3/ma", L.mkmon("c3", "ma"), 0)
    s.check_eq("CPU4 to c3/ma", try_write(R + "/c3/mon_groups/ma/cpus",
               "10\n"), 0)
    if L.pmg_max() >= 2:
        s.check_eq("mkdir c3/mb", L.mkmon("c3", "mb"), 0)
        s.check_eq("CPU4 moves to c3/mb", try_write(R +
                   "/c3/mon_groups/mb/cpus", "10\n"), 0)
        s.check_eq("c3/ma lost CPU4",
                   read(R + "/c3/mon_groups/ma/cpus_list"), "")
        s.check_eq("c3/mb has CPU4",
                   read(R + "/c3/mon_groups/mb/cpus_list"), "4")
        child = "mb"
    else:
        s.info("only one mon group fits per CLOSID "
               "(pmg_max=%d); skip sibling CPU move" % L.pmg_max())
        child = "ma"
    s.check_eq("shrink parent CPU mask", try_write(R + "/c3/cpus", "20\n"), 0)
    s.check_eq("child CPU mask cleared by parent change",
               read(R + "/c3/mon_groups/%s/cpus_list" % child), "")
    s.check_eq("rmdir c3", try_rmdir(R + "/c3"), 0)


def check_group_files(s):
    section("group file surface")
    for grp in ("p1", "p1/mon_groups/m1"):
        base = R + "/" + grp
        for name in sorted(os.listdir(base)):
            path = base + "/" + name
            if os.path.isfile(path):
                s.check("group file readable: %s/%s" % (grp, name),
                        read(path, None) is not None)

    # These files only exist when the architecture exposes the feature; on
    # MPAM io_alloc and the MBA software controller are unsupported.
    for name, value in (("io_alloc", "1\n"),
                        ("io_alloc_cbm", "0\n"),
                        ("mba_MBps_event", "mbm_total_bytes\n")):
        path = R + "/p1/" + name
        if os.path.exists(path):
            s.check("%s read" % name, read(path, None) is not None)
            s.info("%s write rc=%s" % (name, errname(try_write(path, value))))
        else:
            s.info("%s not present on this platform" % name)
    proc = "/proc/self/cpu_resctrl_groups"
    if os.path.exists(proc):
        s.check("proc cpu_resctrl_groups readable",
                read(proc, None) is not None)
    else:
        s.info("%s not present" % proc)


def check_tasks(s):
    section("tasks and cpus")
    s.check_eq("tasks: unknown pid -> ESRCH", try_write(R + "/p1/tasks",
               "999999\n"), errno.ESRCH)
    s.check_eq("tasks: negative pid -> EINVAL", try_write(R + "/p1/tasks",
               "-1\n"), errno.EINVAL)
    s.check_eq("tasks: garbage pid -> EINVAL", try_write(R + "/p1/tasks",
               "abc\n"), errno.EINVAL)
    s.check_eq("tasks: empty line accepted", try_write(R + "/p1/tasks", "\n"), 0)

    sleeper = spawn_sleeper()
    s.check_eq("task to ctrl group", try_write(R + "/p1/tasks",
               "%d\n" % sleeper.pid), 0)
    s.check("ctrl group lists task",
            str(sleeper.pid) in read(R + "/p1/tasks").split())
    s.check_eq("task to mon group", try_write(R + "/p1/mon_groups/m1/tasks",
               "%d\n" % sleeper.pid), 0)
    s.check("mon group lists task",
            str(sleeper.pid) in read(R + "/p1/mon_groups/m1/tasks").split())

    # A task that is not in the parent control group cannot enter its mon
    # group.
    other = spawn_sleeper()
    s.check_eq("foreign task cannot enter mon group",
               try_write(R + "/p1/mon_groups/m1/tasks", "%d\n" % other.pid),
               errno.EINVAL)
    stop(other)

    # Moving the only CPU of a mon group back to the parent.
    s.check_eq("cpus: hex mask", try_write(R + "/p1/cpus", "8\n"), 0)
    s.check_eq("cpus: CPU3 assigned", read(R + "/p1/cpus_list"), "3")
    s.check("root lost CPU3", "3" not in read(R + "/cpus_list").split(","),
            read(R + "/cpus_list"))
    s.check_eq("mon group cannot take a CPU outside its parent",
               try_write(R + "/p1/mon_groups/m1/cpus", "1\n"), errno.EINVAL)
    s.check_eq("mon group takes a CPU from parent",
               try_write(R + "/p1/mon_groups/m1/cpus", "8\n"), 0)
    s.check_eq("mon group cpus_list", read(R + "/p1/mon_groups/m1/cpus_list"),
               "3")
    s.check_eq("cpus_list: list syntax", try_write(R + "/p1/cpus_list",
               "0-1\n"), 0)
    s.check_eq("cpus_list readback", read(R + "/p1/cpus_list"), "0-1")
    s.check_eq("cpus_list: bad syntax -> EINVAL",
               try_write(R + "/p1/cpus_list", "abc\n"), errno.EINVAL)
    s.check_eq("default group cannot drop CPUs",
               try_write(R + "/cpus", "7c\n"), errno.EINVAL,
               L.last_cmd())

    # Moving the current task exercises the on-CPU path that updates the
    # running task's PARTID/PMG immediately.
    s.check_eq("move current task to p1", try_write(R + "/p1/tasks", "0\n"), 0)
    s.check("p1 lists the current task",
            str(os.getpid()) in read(R + "/p1/tasks").split())
    s.check_eq("move current task to mon group",
               try_write(R + "/p1/mon_groups/m1/tasks", "0\n"), 0)
    if os.path.exists("/proc/self/cpu_resctrl_groups"):
        s.check("proc file readable while in a mon group",
                read("/proc/self/cpu_resctrl_groups", None) is not None)
    s.check_eq("move current task back to root",
               try_write(R + "/tasks", "0\n"), 0)
    stop(sleeper)


def check_monitors(s):
    section("monitors and counter assignment")
    feats = read(L.INFO + "/L3_MON/mon_features").split()
    s.check("root llc_occupancy readable",
            (L.mon_read("", "llc_occupancy") or "").isdigit(),
            L.mon_read("", "llc_occupancy"))
    s.check("root mbm_total_bytes readable",
            (L.mon_read("", "mbm_total_bytes") or "").isdigit(),
            L.mon_read("", "mbm_total_bytes"))
    s.check("mon group has mon_data", L.mon_data_dir("p1/mon_groups/m1")
            is not None)

    s.check("assign_on_mkdir default is 1",
            read_int(L.INFO + "/L3_MON/mbm_assign_on_mkdir") == 1)
    s.check("mbm_L3_assignments readback",
            "mbm_total_bytes" in read(R + "/p1/mbm_L3_assignments"))
    s.check("root counter assigned on mkdir",
            "=" in read(R + "/mbm_L3_assignments"))

    # Fixed assignment mode cannot be switched.
    s.check_eq("mbm_assign_mode default -> EINVAL",
               try_write(L.INFO + "/L3_MON/mbm_assign_mode", "default\n"),
               errno.EINVAL)
    s.check_eq("mbm_assign_mode bogus -> EINVAL",
               try_write(L.INFO + "/L3_MON/mbm_assign_mode", "bogus\n"),
               errno.EINVAL)
    s.check_eq("mbm_assign_on_mkdir bad input -> EINVAL",
               try_write(L.INFO + "/L3_MON/mbm_assign_on_mkdir", "junk\n"),
               errno.EINVAL)

    # Childless group: explicit unassign must make the read "Unassigned".
    s.check_eq("mkdir u1", try_mkdir(R + "/u1"), 0)
    s.check("u1 mbm assigned on mkdir",
            (L.mon_read("u1", "mbm_total_bytes") or "").isdigit(),
            L.mon_read("u1", "mbm_total_bytes"))
    s.check_eq("u1 unassign", try_write(R + "/u1/mbm_L3_assignments",
               "mbm_total_bytes:*=_\n"), 0)
    s.check_eq("u1 mbm read after unassign", L.mon_read("u1",
               "mbm_total_bytes"), "Unassigned")
    s.check_eq("u1 llc still readable after mbm unassign",
               (L.mon_read("u1", "llc_occupancy") or "").isdigit(), True,
               L.mon_read("u1", "llc_occupancy"))
    s.check_eq("u1 invalid event -> ENOENT", try_write(R +
               "/u1/mbm_L3_assignments", "bogus:*=e\n"), errno.ENOENT)
    s.check_eq("u1 invalid domain -> EINVAL", try_write(R +
               "/u1/mbm_L3_assignments", "mbm_total_bytes:999=e\n"),
               errno.EINVAL)
    s.check_eq("u1 missing newline -> EINVAL", try_write(R +
               "/u1/mbm_L3_assignments", "mbm_total_bytes:*=e"),
               errno.EINVAL)

    # Counter exhaustion with assign_on_mkdir: group creation still succeeds
    # but the counter is not assigned.
    s.check_eq("disable assign_on_mkdir", try_write(L.INFO +
               "/L3_MON/mbm_assign_on_mkdir", "0\n"), 0)
    s.check_eq("mkdir u2", try_mkdir(R + "/u2"), 0)
    s.check_eq("u2 has no counter", L.mon_read("u2", "mbm_total_bytes"),
               "Unassigned")
    s.check_eq("manual assign u2", try_write(R + "/u2/mbm_L3_assignments",
               "mbm_total_bytes:*=e\n"), 0)
    s.check("u2 mbm after manual assign",
            (L.mon_read("u2", "mbm_total_bytes") or "").isdigit(),
            L.mon_read("u2", "mbm_total_bytes"))

    # Per-domain assignment form.
    u2_mon = L.mon_data_dir("u2")
    dom = int(u2_mon.rsplit("_", 1)[1])
    s.check_eq("u2 unassign one domain", try_write(R +
               "/u2/mbm_L3_assignments", "mbm_total_bytes:%d=_\n" % dom), 0)
    s.check_eq("u2 mbm unassigned per domain",
               L.mon_read("u2", "mbm_total_bytes"), "Unassigned")
    s.check_eq("u2 re-assign one domain", try_write(R +
               "/u2/mbm_L3_assignments", "mbm_total_bytes:%d=e\n" % dom), 0)

    # Every monitor file is readable.
    for grp in ("", "p1", "p1/mon_groups/m1"):
        md = L.mon_data_dir(grp)
        if not md:
            continue
        for name in os.listdir(md):
            s.check("monitor file readable: %s/%s" % (grp, name),
                    read(md + "/" + name, None) is not None)

    s.check_eq("restore assign_on_mkdir", try_write(L.INFO +
               "/L3_MON/mbm_assign_on_mkdir", "1\n"), 0)

    # A counter is consumed on mkdir while assignment is enabled.
    try:
        avail_before = int(read(L.INFO +
                                "/L3_MON/available_mbm_cntrs").split("=")[1])
    except (IndexError, ValueError):
        avail_before = -1
    s.check_eq("mkdir u3", try_mkdir(R + "/u3"), 0)
    try:
        avail_after = int(read(L.INFO +
                               "/L3_MON/available_mbm_cntrs").split("=")[1])
    except (IndexError, ValueError):
        avail_after = -1
    s.check_eq("mkdir consumes one MBM counter", avail_after,
               avail_before - 1,
               "before=%d after=%d" % (avail_before, avail_after))
    s.check_eq("u3 unassign returns the counter",
               try_write(R + "/u3/mbm_L3_assignments",
                         "mbm_total_bytes:*=_\n"), 0)

    # Event filter configuration is exposed but not configurable on MPAM.
    ev = L.INFO + "/L3_MON/event_configs/mbm_total_bytes/event_filter"
    s.check("event_filter lists transactions", "local_reads" in read(ev), read(ev))
    s.check("BMEC config file hidden",
            not os.path.exists(L.INFO + "/L3_MON/mbm_total_bytes_config")
            or try_write(L.INFO + "/L3_MON/mbm_total_bytes_config",
                         "x\n") != 0)

    # max_threshold_occupancy validation.
    limit = L.cache_size(3)
    old = read(L.INFO + "/L3_MON/max_threshold_occupancy")
    s.check_eq("max_threshold bad input -> EINVAL", try_write(L.INFO +
               "/L3_MON/max_threshold_occupancy", "junk\n"), errno.EINVAL)
    s.check_eq("max_threshold above L3 size -> EINVAL", try_write(L.INFO +
               "/L3_MON/max_threshold_occupancy", "%d\n" % (limit * 2)),
               errno.EINVAL)
    s.check_eq("max_threshold zero accepted", try_write(L.INFO +
               "/L3_MON/max_threshold_occupancy", "0\n"), 0)
    if old:
        try_write(L.INFO + "/L3_MON/max_threshold_occupancy", old + "\n")

    # Concurrent readers must not fail or hang.
    import threading
    d = L.mon_data_dir("")
    path = d + "/llc_occupancy"
    bad = []
    stop_at = time.time() + 2

    def reader():
        while time.time() < stop_at:
            v = read(path, None)
            if v is None or (v not in ("Unavailable", "Error", "Unassigned")
                             and not v.isdigit()):
                bad.append(v)

    ths = [threading.Thread(target=reader) for _ in range(16)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    s.check("16 concurrent llc_occupancy readers", not bad, str(bad[:4]))


def check_rename_rules(s):
    # A mon group that owns CPUs cannot be moved to another control group.
    s.check_eq("mkdir cpu-dst", try_mkdir(R + "/cpudst"), 0)
    s.check_eq("mkdir cpu-src", try_mkdir(R + "/cpusrc"), 0)
    s.check_eq("mkdir cpu0", L.mkmon("cpudst", "cpu0"), 0)
    # cpus is a hex mask: CPU4 is bit 4 (0x10). The CPU must belong to the
    # parent control group before a monitor group may take it.
    s.check_eq("assign CPU4 to cpu-dst control group",
               try_write(R + "/cpudst/cpus", "10\n"), 0)
    s.check_eq("assign CPU to mon group", try_write(R +
               "/cpudst/mon_groups/cpu0/cpus", "10\n"), 0)
    try:
        os.rename(R + "/cpudst/mon_groups/cpu0",
                  R + "/cpusrc/mon_groups/cpu0")
        rc = 0
    except OSError as e:
        rc = e.errno
    s.check_eq("CPU-monitoring mon group cannot be reparented", rc,
               errno.EPERM, errname(rc))

    # Control groups are not renameable.
    try:
        os.rename(R + "/src", R + "/src2")
        rc = 0
    except OSError as e:
        rc = e.errno
    s.check_eq("control group cannot be renamed", rc, errno.EPERM,
               errname(rc))


def check_reparent(s):
    section("monitor group reparent")
    # No counters on mkdir: assign counters only where a check needs them.
    try_write(L.INFO + "/L3_MON/mbm_assign_on_mkdir", "0\n")

    pmg = L.pmg_max()
    if pmg < 1:
        s.info("pmg_max=%d too small for reparent tests" % pmg)
        check_rename_rules(s)
        try_write(L.INFO + "/L3_MON/mbm_assign_on_mkdir", "1\n")
        return

    # --- Scenario 1: destination CLOSID has no free RMID ---------------
    s.check_eq("mkdir dst", try_mkdir(R + "/dst"), 0)
    s.check_eq("mkdir src", try_mkdir(R + "/src"), 0)
    dst_ids = []
    src_ids = []
    for i in range(1, pmg + 1):
        if L.mkmon("dst", "d%d" % i) == 0:
            dst_ids.append((L.hw_ids("dst/mon_groups/d%d" % i)[1],
                            "dst/mon_groups/d%d" % i))
        if L.mkmon("src", "s%d" % i) == 0:
            src_ids.append((L.hw_ids("src/mon_groups/s%d" % i)[1],
                            "src/mon_groups/s%d" % i))
    s.check_eq("fill destination RMID pool", len(dst_ids), pmg)
    s.check_eq("fill source RMID pool", len(src_ids), pmg)

    dst_pmg = {p: path for p, path in dst_ids}
    pair = None
    for p, path in src_ids:
        if p in dst_pmg:
            pair = (path, dst_pmg[p], p)
            break

    if pair:
        src_path, dst_path, old_pmg = pair
        sleeper = spawn_sleeper()
        s.check_eq("task to src ctrl group", try_write(R + "/src/tasks",
                   "%d\n" % sleeper.pid), 0)
        s.check_eq("task to src mon group",
                   try_write(R + "/%s/tasks" % src_path,
                             "%d\n" % sleeper.pid), 0)
        s.check_eq("assign counter to destination group",
                   try_write(R + "/%s/mbm_L3_assignments" % dst_path,
                             "mbm_total_bytes:*=e\n"), 0)
        s.check_eq("assign counter to source group",
                   try_write(R + "/%s/mbm_L3_assignments" % src_path,
                             "mbm_total_bytes:*=e\n"), 0)
        s.check("source mbm before rename",
                (L.mon_read(src_path, "mbm_total_bytes") or "").isdigit(),
                L.mon_read(src_path, "mbm_total_bytes"))

        src_old = "%s/%s" % (R, src_path)
        new_base = os.path.basename(src_path)
        dst_new = "%s/dst/mon_groups/%s" % (R, new_base)
        try:
            os.rename(src_old, dst_new)
            rc = 0
        except OSError as e:
            rc = e.errno

        if rc == 0:
            # Pre-fix behaviour: the rename ignores per-CLOSID RMIDs.
            s.info("rename succeeded with a full destination RMID pool")
            s.check("reparented group still lists its task",
                    str(sleeper.pid) in read(dst_new + "/tasks").split())
            new_pmg = L.hw_ids("dst/mon_groups/%s" % new_base)[1]
            s.check_eq("reparented group keeps its PMG", new_pmg, old_pmg)
            s.check("reparent does not collide with an existing PMG",
                    new_pmg != L.hw_ids(dst_path)[1],
                    "both groups use PMG %d" % new_pmg)
            try_write(R + "/%s/mbm_L3_assignments" % dst_path,
                      "mbm_total_bytes:*=_\n")
            after = L.mon_read("dst/mon_groups/%s" % new_base,
                               "mbm_total_bytes")
            s.check("reparented monitor independent of destination counter",
                    after != "Unassigned",
                    "read=%s after unassigning %s" % (after, dst_path))
        else:
            s.check("rename rejected when destination is out of RMIDs",
                    rc in (errno.ENOSPC, errno.EBUSY),
                    "rc=%s last=%s" % (errname(rc), L.last_cmd()))
            s.check("source group still exists after the rejected rename",
                    os.path.isdir(src_old))
            s.check("task still in the source group",
                    str(sleeper.pid) in read(src_old + "/tasks").split())
            s.check_eq("destination mon group count unchanged",
                       len(os.listdir(R + "/dst/mon_groups")), pmg)
        stop(sleeper)
    else:
        s.info("no colliding PMG with pmg_max=%d" % pmg)

    # --- Scenario 2: destination has a free RMID ----------------------
    s.check_eq("mkdir dst2", try_mkdir(R + "/dst2"), 0)
    s.check_eq("mkdir src2", try_mkdir(R + "/src2"), 0)
    s.check_eq("mkdir src2/m", L.mkmon("src2", "m"), 0)
    task = spawn_sleeper()
    s.check_eq("task to src2", try_write(R + "/src2/tasks",
               "%d\n" % task.pid), 0)
    s.check_eq("task to src2/m", try_write(R + "/src2/mon_groups/m/tasks",
               "%d\n" % task.pid), 0)
    s.check_eq("counter to src2/m", try_write(R +
               "/src2/mon_groups/m/mbm_L3_assignments",
               "mbm_total_bytes:*=e\n"), 0)
    s.check_eq("counter to dst2", try_write(R +
               "/dst2/mbm_L3_assignments", "mbm_total_bytes:*=e\n"), 0)

    dst2_ctrl_pmg = L.hw_ids("dst2")[1]
    try:
        os.rename(R + "/src2/mon_groups/m", R + "/dst2/mon_groups/m")
        rc = 0
    except OSError as e:
        rc = e.errno
    s.check_eq("reparent with a free destination RMID", rc, 0,
               "rc=%s last=%s" % (errname(rc), L.last_cmd()))
    if rc == 0:
        s.check("reparented group still lists its task",
                str(task.pid) in read(R + "/dst2/mon_groups/m/tasks").split())
        s.check("task left the old control group",
                str(task.pid) not in read(R + "/src2/tasks").split())
        new_pmg = L.hw_ids("dst2/mon_groups/m")[1]
        s.check("reparent uses a distinct destination PMG",
                new_pmg != dst2_ctrl_pmg,
                "new=%d dst ctrl=%d" % (new_pmg, dst2_ctrl_pmg))
        s.check_eq("mbm restarts unassigned after reparent",
                   L.mon_read("dst2/mon_groups/m", "mbm_total_bytes"),
                   "Unassigned")
        try_write(R + "/dst2/mon_groups/m/mbm_L3_assignments",
                  "mbm_total_bytes:*=e\n")
        s.check("mbm assignable after reparent",
                (L.mon_read("dst2/mon_groups/m", "mbm_total_bytes")
                 or "").isdigit(),
                L.mon_read("dst2/mon_groups/m", "mbm_total_bytes"))

        try_write(R + "/dst2/mbm_L3_assignments", "mbm_total_bytes:*=_\n")
        after = L.mon_read("dst2/mon_groups/m", "mbm_total_bytes")
        s.check("reparented monitor independent of parent counter",
                after != "Unassigned", "read=%s" % after)
        try_write(R + "/dst2/mbm_L3_assignments", "mbm_total_bytes:*=e\n")
        dst_before = L.mon_read("dst2", "mbm_total_bytes")
        s.check("parent monitor usable before rmdir",
                (dst_before or "").isdigit(), dst_before)

        old_pmg = L.hw_ids("dst2/mon_groups/m")[1]
        try:
            os.rename(R + "/dst2/mon_groups/m", R + "/dst2/mon_groups/mx")
            rc = 0
        except OSError as e:
            rc = e.errno
        s.check_eq("rename within the same control group", rc, 0,
                   errname(rc))
        if rc == 0:
            s.check_eq("same-parent rename keeps the RMID",
                       L.hw_ids("dst2/mon_groups/mx")[1], old_pmg)
            s.check("same-parent rename keeps the task",
                    str(task.pid) in
                    read(R + "/dst2/mon_groups/mx/tasks").split())
            s.check("same-parent rename keeps the counter",
                    (L.mon_read("dst2/mon_groups/mx", "mbm_total_bytes")
                     or "").isdigit(),
                    L.mon_read("dst2/mon_groups/mx", "mbm_total_bytes"))
            try_rmdir(R + "/dst2/mon_groups/mx")

        dst_after = L.mon_read("dst2", "mbm_total_bytes")
        s.check("parent monitor survives rmdir of reparented group",
                (dst_after or "").isdigit(),
                "read=%s before=%s" % (dst_after, dst_before))
    stop(task)

    check_rename_rules(s)
    try_write(L.INFO + "/L3_MON/mbm_assign_on_mkdir", "1\n")

def check_remount(s):
    section("unmount with live groups")
    task = spawn_sleeper()
    s.check_eq("mkdir rm1", try_mkdir(R + "/rm1"), 0)
    s.check_eq("mkdir rm1/m", L.mkmon("rm1", "m"), 0)
    s.check_eq("task to rm1", try_write(R + "/rm1/tasks",
               "%d\n" % task.pid), 0)
    s.check_eq("task to rm1/m", try_write(R + "/rm1/mon_groups/m/tasks",
               "%d\n" % task.pid), 0)
    val = L.mon_read("rm1/mon_groups/m", "mbm_total_bytes")
    if not (val or "").isdigit():
        # Counters may be exhausted by earlier sections; free one first so
        # the unmount path is exercised with a live assignment where possible.
        try_write(R + "/dst2/mbm_L3_assignments", "mbm_total_bytes:*=_\n")
        try_write(R + "/rm1/mon_groups/m/mbm_L3_assignments",
                  "mbm_total_bytes:*=e\n")
        val = L.mon_read("rm1/mon_groups/m", "mbm_total_bytes")
    if (val or "").isdigit():
        s.ok("counter before unmount (%s)" % val)
    else:
        s.info("no MBM counter available before unmount (%s)" % val)

    L.umount(suite=s)
    s.check("resctrl unmounted", not L.mounted())
    rc = L.mount("debug", s)
    s.check_eq("remount after live groups", rc, 0, errname(rc))
    s.check("old resource groups removed", not os.path.exists(R + "/rm1"))
    s.check("task returned to the root group after unmount",
            str(task.pid) in read(R + "/tasks").split())
    l3 = L.schemata_domains()["L3"][0]
    full = (1 << L.cbm_len("L3")) - 1
    s.check_eq("schemata reset after remount",
               L.schemata_value("", "L3", l3), full)
    stop(task)


def main():
    s = L.Suite("resctrl/MPAM coupling (plain)")
    rc = L.mount("debug", s)
    if rc:
        s.fail("mount resctrl -o debug", errname(rc))
        return s.summary()
    s.ok("mount resctrl -o debug")

    check_info(s)
    check_schemata(s)
    check_groups(s)
    check_group_files(s)
    check_tasks(s)
    check_monitors(s)
    check_reparent(s)
    check_remount(s)

    L.umount(suite=s)
    return s.summary()


if __name__ == "__main__":
    sys.exit(main())
