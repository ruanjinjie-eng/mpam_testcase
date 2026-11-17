# SPDX-License-Identifier: GPL-2.0
# Copyright (c) 2026. Huawei Technologies Co.,Ltd.ALL rights reserved.
#
# Helpers for the resctrl/MPAM coupling tests.
#
# The suite deliberately drives the resctrl ABI instead of the MPAM MMIO
# registers: every check exercises a fs/resctrl code path that ends in a
# resctrl_arch_* callback implemented by drivers/resctrl/mpam_resctrl.c.

import errno
import os
import subprocess
import time

R = "/sys/fs/resctrl"
INFO = R + "/info"


class Suite:
    def __init__(self, name):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.failures = []

    def ok(self, msg):
        self.passed += 1
        print("PASS: %s" % msg, flush=True)

    def fail(self, msg, detail=""):
        self.failed += 1
        text = msg if not detail else "%s [%s]" % (msg, detail)
        self.failures.append(text)
        print("FAIL: %s" % text, flush=True)

    def check(self, msg, cond, detail=""):
        if cond:
            self.ok(msg)
        else:
            self.fail(msg, detail)
        return cond

    def check_eq(self, msg, got, want, detail=""):
        return self.check(msg, got == want,
                          detail or "got=%r want=%r" % (got, want))

    def info(self, msg):
        print("INFO: %s" % msg, flush=True)

    def summary(self):
        print("RESULT: %s: %d passed, %d failed" %
              (self.name, self.passed, self.failed), flush=True)
        if self.failures:
            print("FAILED CHECKS:", flush=True)
            for f in self.failures:
                print("  - %s" % f, flush=True)
        print("SUITE DONE", flush=True)
        return 1 if self.failed else 0


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def read_int(path, default=-1):
    try:
        return int(read(path))
    except ValueError:
        return default


def try_write(path, data):
    """Write @data, returning 0 or the errno."""
    try:
        with open(path, "w") as f:
            f.write(data)
        return 0
    except OSError as e:
        return e.errno


def try_mkdir(path):
    try:
        os.mkdir(path)
        return 0
    except OSError as e:
        return e.errno


def try_rmdir(path):
    try:
        os.rmdir(path)
        return 0
    except OSError as e:
        return e.errno


def errname(num):
    try:
        return errno.errorcode[num]
    except KeyError:
        return str(num)


def mounted():
    try:
        with open("/proc/mounts") as f:
            return any(line.split()[1] == R and line.split()[2] == "resctrl"
                       for line in f)
    except OSError:
        return False


def cache_size(level):
    """Largest cache of @level in bytes, 0 if unknown."""
    biggest = 0
    base = "/sys/devices/system/cpu"
    for cpu in os.listdir(base):
        if not cpu.startswith("cpu") or not cpu[3:].isdigit():
            continue
        path = "%s/%s/cache" % (base, cpu)
        if not os.path.isdir(path):
            continue
        for idx in os.listdir(path):
            d = path + "/" + idx
            if read_int(d + "/level") != level:
                continue
            size = read(d + "/size")
            num, unit = size[:-1], size[-1:]
            try:
                val = int(num)
            except ValueError:
                continue
            if unit == "K":
                val *= 1024
            elif unit == "M":
                val *= 1024 * 1024
            biggest = max(biggest, val)
    return biggest


def drain_limbo(suite=None):
    """
    QEMU's CSU model reports a non-zero occupancy for every RMID, so with the
    default max_threshold_occupancy the limbo worker never frees an RMID.
    Raise the threshold to the L3 size before unmounting so the next mount
    starts with a usable free list.
    """
    path = INFO + "/L3_MON/max_threshold_occupancy"
    limit = cache_size(3)
    if limit and os.path.exists(path):
        rc = try_write(path, "%d\n" % limit)
        if rc and suite:
            suite.info("drain: writing max_threshold_occupancy failed %s" %
                       errname(rc))
    time.sleep(2)


def umount(drain=True, suite=None):
    if not mounted():
        return
    if drain:
        drain_limbo(suite)
    rc = subprocess.call(["umount", R],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    if rc and suite:
        suite.info("umount failed rc=%d" % rc)


def mount(opts="debug", suite=None, drain=True):
    """(Re)mount resctrl with @opts, returning 0 or the errno."""
    umount(drain=drain, suite=suite)
    os.makedirs(R, exist_ok=True)
    args = ["mount", "-t", "resctrl", "resctrl", R]
    if opts:
        args += ["-o", opts]
    rc = subprocess.call(args, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    if rc:
        return errno.EINVAL
    if drain:
        # The limbo handler is restarted at mount and runs once a second.
        time.sleep(2)
    return 0


def schemata_domains(grp=""):
    """Return {resource: [domain ids]} from a group's schemata."""
    out = {}
    text = read("%s/%s/schemata" % (R, grp) if grp else R + "/schemata")
    for line in text.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        doms = []
        for seg in rest.split(";"):
            if "=" in seg:
                try:
                    doms.append(int(seg.split("=")[0]))
                except ValueError:
                    pass
        out[name.strip()] = doms
    return out


def schemata_value(grp, resource, dom):
    text = read("%s/%s/schemata" % (R, grp) if grp else R + "/schemata")
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith(resource + ":"):
            continue
        for seg in line.split(":", 1)[1].split(";"):
            if "=" not in seg:
                continue
            idx, val = seg.split("=", 1)
            if int(idx) == dom:
                try:
                    return int(val, 16 if resource.startswith(("L2", "L3"))
                               else 10)
                except ValueError:
                    return -1
    return -1


def hw_ids(grp):
    """(ctrl_hw_id, mon_hw_id); requires the debug mount option."""
    return (read_int("%s/%s/ctrl_hw_id" % (R, grp)),
            read_int("%s/%s/mon_hw_id" % (R, grp)))


def mon_data_dir(grp):
    base = "%s/%s/mon_data" % (R, grp) if grp else R + "/mon_data"
    try:
        dirs = [d for d in os.listdir(base) if d.startswith("mon_")]
    except OSError:
        return None
    return base + "/" + dirs[0] if dirs else None


def mon_read(grp, event):
    d = mon_data_dir(grp)
    if not d:
        return None
    return read(d + "/" + event, None)


def mkctrl(name):
    return try_mkdir("%s/%s" % (R, name))


def mkmon(ctrl, name):
    return try_mkdir("%s/%s/mon_groups/%s" % (R, ctrl, name))


def rmgrp(path):
    return try_rmdir(path)


def wait_num(path, timeout=8):
    """Wait until a mon_data file reports a number; return value or None."""
    end = time.time() + timeout
    while time.time() < end:
        v = read(path, "")
        if v.isdigit():
            return int(v)
        time.sleep(0.2)
    return None


def last_cmd():
    return read(INFO + "/last_cmd_status")


def write_schemata(grp, text):
    return try_write("%s/%s/schemata" % (R, grp) if grp else R + "/schemata",
                     text)


def pmg_max():
    """PMG_max implied by the advertised RMID/CLOSID counts, -1 if unknown."""
    num_closids = read_int(INFO + "/L3/num_closids")
    num_rmids = read_int(INFO + "/L3_MON/num_rmids")
    if num_closids <= 0 or num_rmids <= 0:
        return -1
    return num_rmids // num_closids - 1


def cbm_len(resource="L3"):
    mask = read("%s/%s/cbm_mask" % (INFO, resource))
    try:
        return len(bin(int(mask, 16))) - 2
    except ValueError:
        return 32
