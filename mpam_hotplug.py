# Copyright (c) 2025. Huawei Technologies Co.,Ltd.ALL rights reserved.
# This program is licensed under Mulan PSL v2.
# You can use it according to the terms and conditions of the Mulan PSL v2.
#          http://license.coscl.org.cn/MulanPSL2
# THIS PROGRAM IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.

# #############################################
# @Desc      : CPU hotplug on a monitor domain
#
# When the last CPU of a monitor domain goes offline the domain is
# destroyed, and it is set up from scratch when a CPU comes back.  The
# counters of the groups that already exist must be given back on the new
# domain, and every group must get the counter ID it uses in the other
# domains.  Otherwise the events on that domain read "Unassigned" and two
# groups can end up sharing one hardware counter.
# #############################################

import os, time
import mpam_lib

resctrl_path = "/sys/fs/resctrl"

def _read_file(path):
    with open(path, 'r') as f:
        return f.read().strip()

def _write_file(path, val):
    with open(path, 'w') as f:
        f.write(val)

def _parse_cpu_list(text):
    cpus = []

    for part in text.split(','):
        part = part.strip()
        if '-' in part:
            first, last = part.split('-')
            cpus.extend(range(int(first), int(last) + 1))
        elif part:
            cpus.append(int(part))

    return cpus

def _cpu_online(cpu):
    path = "/sys/devices/system/cpu/cpu%d/online" % cpu

    # cpu0 has no online file and is always online.
    if not os.path.exists(path):
        return True

    return _read_file(path) == "1"

def _wait_cpu_state(cpus, online, timeout=15):
    end = time.time() + timeout

    while time.time() < end:
        if all(_cpu_online(cpu) == online for cpu in cpus):
            return 0
        time.sleep(0.2)

    return -1

def _set_cpu_online(cpu, online):
    _write_file("/sys/devices/system/cpu/cpu%d/online" % cpu,
                "1" if online else "0")

def _mon_doms(ctrl_grp, resource):
    """Domain ids of the mon_<resource>_* directories of @ctrl_grp."""
    mon_dir = "%s/%s/mon_data" % (resctrl_path, ctrl_grp)
    prefix = "mon_%s_" % resource

    return sorted(int(d[len(prefix):]) for d in os.listdir(mon_dir)
                  if d.startswith(prefix) and d[len(prefix):].isdigit())

def _read_val(ctrl_grp, resource, dom, monitor):
    """Read @monitor in @dom, -1 if it can't be read.

    A counter that is not assigned reads as "Unassigned", which makes the
    int() conversion fail.
    """
    try:
        val = mpam_lib.read_resource_monitor_val(ctrl_grp, resource, dom, monitor)
        if not val:
            val = mpam_lib.read_resource_monitor_val(ctrl_grp, resource, dom, monitor)
        return val
    except (OSError, ValueError) as e:
        print("Fail: read %s in domain %d: %s" % (monitor, dom, e))
        return -1

def _growing_dom(ctrl_grp, resource, monitor):
    """Return the domain whose @monitor value is increasing, or -1."""
    doms = _mon_doms(ctrl_grp, resource)
    first = {dom: _read_val(ctrl_grp, resource, dom, monitor) for dom in doms}
    time.sleep(1)
    second = {dom: _read_val(ctrl_grp, resource, dom, monitor) for dom in doms}

    best = -1
    best_delta = 0
    for dom in doms:
        if first[dom] < 0 or second[dom] < 0:
            continue
        if second[dom] - first[dom] > best_delta:
            best_delta = second[dom] - first[dom]
            best = dom

    return best

def _available_cntrs(resource):
    path = "%s/info/%s_MON/available_mbm_cntrs" % (resctrl_path, resource)

    if not os.path.exists(path):
        return None

    cntrs = {}
    for seg in _read_file(path).split(';'):
        dom, cnt = seg.split('=')
        cntrs[int(dom)] = int(cnt)

    return cntrs

def _start_bench_in_group(ctrl_grp, cpu, seconds=8):
    """Run a cache benchmark on @cpu for @ctrl_grp, return its PID."""
    pid = os.fork()

    if pid:
        return pid

    try:
        mpam_lib.put_pid_resctrl(os.getpid(), ctrl_grp)
        devnull = os.open("/dev/null", os.O_RDWR)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        os.execvp("taskset",
                  ["taskset", "-c", str(cpu), "stress-ng", "--cache", "1",
                   "--aggressive", "-t", "%ds" % seconds])
    except Exception as e:
        print("Fail: start benchmark on cpu%d: %s" % (cpu, e))

    os._exit(1)

def _stop_bench(pid):
    try:
        os.kill(pid, 9)
    except OSError:
        pass
    os.waitpid(pid, 0)

def run_hotplug_test(resource="L2"):
    print("run_hotplug_test %s begin:" % resource)

    monitor = "mbm_core_bytes" if resource == "L2" else "mbm_total_bytes"

    if mpam_lib.check_resource_mon(resource, monitor):
        return -1

    ncpu = os.cpu_count()
    if ncpu < 2:
        print("Fail: need at least two CPUs")
        return -1

    # Use the CPUs sharing the L2 of the last CPU as the domain to take
    # offline, and keep the test process away from them.
    target = ncpu - 1
    dom_cpus = _parse_cpu_list(mpam_lib.find_cpu_to_cache_sharelist(target, resource))
    keep = [cpu for cpu in range(ncpu) if cpu not in dom_cpus]
    if not keep:
        print("Fail: no CPU outside the %s domain to run the test on" % resource)
        return -1

    os.sched_setaffinity(0, keep)

    ctrl_grp = "p_hotplug"
    if mpam_lib.mkdir_ctrl_group(ctrl_grp, ""):
        return -1

    if mpam_lib.put_pid_resctrl(os.getpid(), ctrl_grp):
        return -1

    bench = _start_bench_in_group(ctrl_grp, target)
    dom = _growing_dom(ctrl_grp, resource, monitor)
    before = _read_val(ctrl_grp, resource, dom, monitor) if dom >= 0 else -1
    time.sleep(1)
    before2 = _read_val(ctrl_grp, resource, dom, monitor) if dom >= 0 else -1
    _stop_bench(bench)

    if dom < 0 or before < 0 or before2 <= before:
        print("Fail: %s does not advance before hotplug" % monitor)
        return -1
    print("Pass: %s advances before hotplug, domain %d" % (monitor, dom))

    avail_before = _available_cntrs(resource)

    # Take the whole domain offline so that it is destroyed, then bring
    # one CPU back.
    for cpu in dom_cpus:
        _set_cpu_online(cpu, False)
    if _wait_cpu_state(dom_cpus, False):
        print("Fail: CPUs %s did not go offline" % dom_cpus)
        return -1

    _set_cpu_online(target, True)
    if _wait_cpu_state([target], True):
        print("Fail: cpu%d did not come online" % target)
        return -1

    if dom not in _mon_doms(ctrl_grp, resource):
        print("Fail: monitor domain %d was not recreated" % dom)
        return -1

    avail_after = _available_cntrs(resource)
    if avail_before is not None and avail_after != avail_before:
        print("Fail: counters not given back after hotplug: %s -> %s" %
              (avail_before, avail_after))
        return -1
    print("Pass: counters given back after hotplug: %s" % avail_after)

    bench = _start_bench_in_group(ctrl_grp, target)
    time.sleep(2)
    after = _read_val(ctrl_grp, resource, dom, monitor)
    time.sleep(1)
    after2 = _read_val(ctrl_grp, resource, dom, monitor)
    _stop_bench(bench)

    if after < 0 or after2 <= after:
        print("Fail: %s does not advance after hotplug" % monitor)
        return -1
    print("Pass: %s advances after hotplug" % monitor)

    # A second domain CPU and a second group: each group must keep its own
    # counter.  If they share one, reading the other group restarts the
    # count and the second read does not grow.
    other = None
    for cpu in dom_cpus:
        if cpu != target:
            other = cpu
            break

    if other is not None:
        _set_cpu_online(other, True)
        if _wait_cpu_state([other], True):
            print("Fail: cpu%d did not come online" % other)
            return -1

        ctrl_grp2 = "p_hotplug2"
        if mpam_lib.mkdir_ctrl_group(ctrl_grp2, ""):
            return -1

        bench1 = _start_bench_in_group(ctrl_grp, target)
        bench2 = _start_bench_in_group(ctrl_grp2, other)
        time.sleep(2)

        grp1_first = _read_val(ctrl_grp, resource, dom, monitor)
        grp2_first = _read_val(ctrl_grp2, resource, dom, monitor)
        time.sleep(1)
        grp1_second = _read_val(ctrl_grp, resource, dom, monitor)
        grp2_second = _read_val(ctrl_grp2, resource, dom, monitor)

        _stop_bench(bench1)
        _stop_bench(bench2)

        if grp1_first < 0 or grp2_first < 0 or \
           grp1_second <= grp1_first or grp2_second <= grp2_first:
            print("Fail: groups do not keep separate %s counters" % monitor)
            return -1
        print("Pass: groups keep separate %s counters" % monitor)

    # Leave the machine as it was found: all CPUs online, no test groups.
    for cpu in dom_cpus:
        if not _cpu_online(cpu):
            _set_cpu_online(cpu, True)
    _wait_cpu_state(dom_cpus, True)

    try:
        _write_file("%s/tasks" % resctrl_path, str(os.getpid()))
    except OSError:
        pass
    mpam_lib.rmdir_ctrl_group("p_hotplug2", "")
    mpam_lib.rmdir_ctrl_group(ctrl_grp, "")

    print("Pass: run_hotplug_test %s" % resource)
    return 0
