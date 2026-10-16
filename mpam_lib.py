# Copyright (c) 2025. Huawei Technologies Co.,Ltd.ALL rights reserved.
# This program is licensed under Mulan PSL v2.
# You can use it according to the terms and conditions of the Mulan PSL v2.
#          http://license.coscl.org.cn/MulanPSL2
# THIS PROGRAM IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.

# #############################################
# @Author    :   Zeng Heng
# @Contact   :   zengheng4@huawei.com
# @Date      :   2025/07/12
# @License   :   Mulan PSL v2
# @Desc      :   Test "mpam" command
# #############################################

import os, subprocess, time

resctrl_path = "/sys/fs/resctrl"
cache_topology = "/sys/devices/system/cpu/cpu"

def check_resource_mon(resource, monitor, quiet=False):
    test_info = ("Check %s msc monitor" % resource)
    path = resctrl_path + "/info/" + resource + "_MON"
    features = path + "/mon_features"

    ret = os.path.exists(features)
    if not ret:
        if not quiet:
            print("Fail: %s" % test_info)
        return -1

    with open(features, 'r') as f:
        cnt = f.read()

    if monitor not in cnt:
        if not quiet:
            print("Fail: %s" % test_info)
        return -1

    return 0

def probe_bw_monitor():
    """Resolve which resource carries the bandwidth monitor.

    OLK exposes info/MB_MON and mon_MB_* domains; mainline serves
    mbm_total_bytes under info/L3_MON and mon_L3_* domains. Return the
    resource name whose mon_data dir carries mbm_total_bytes, or None.
    """
    if check_resource_mon("MB", "mbm_total_bytes", quiet=True) == 0:
        return "MB"
    if check_resource_mon("L3", "mbm_total_bytes", quiet=True) == 0:
        return "L3"
    return None

def on_hw():
    """Real MPAM platform where partitioning/priority actually throttles
    traffic. On QEMU the MSC model derives counters from configuration
    and never enforces bandwidth, so bandwidth-comparison verdicts that
    depend on real throttling are skipped there.
    """
    return get_cpu_id() in ["950", "920G"]

def get_resource_dom(resource):
    """First domain id of <resource>: from the root schemata.

    MB-family domains are NUMA-node based on OLK but L3-cache-id based
    on mainline - always take the real id instead of hardcoding.
    """
    try:
        with open(resctrl_path + "/schemata", 'r') as f:
            for line in f:
                # mainline aligns resource names with leading spaces
                if line.strip().startswith(resource + ":"):
                    return int(line.strip().split(":")[1].split("=")[0])
    except (OSError, ValueError):
        pass

    return -1

def read_schemata_val(ctrl_grp, resource, dom):
    """Numeric value of <resource>:<dom> in a group's schemata.

    Handles the multi-domain ';' form and the zero-padded OLK output;
    returns -1 when the resource/domain is not present.
    """
    path = ("%s/%s/schemata" % (resctrl_path, ctrl_grp))

    try:
        with open(path, 'r') as f:
            for line in f:
                if not line.strip().startswith(resource + ":"):
                    continue
                for seg in line.strip().split(":", 1)[1].split(";"):
                    fields = seg.split("=")
                    if fields[0] == str(dom):
                        return int(fields[1])
    except (OSError, ValueError, IndexError):
        pass

    return -1

def find_mon_dom(ctrl_group, resource):
    """Domain id of the first mon_<resource>_* dir under mon_data.

    The mainline driver names mon_L3_* after the monitor component id,
    which may differ from the sysfs cache id (OLK uses the cache id), so
    enumerate the directory instead of computing the id where possible.
    """
    mon_dir = ("%s/%s/mon_data" % (resctrl_path, ctrl_group))
    prefix = ("mon_%s_" % resource)

    try:
        for d in os.listdir(mon_dir):
            if d.startswith(prefix) and d[len(prefix):].isdigit():
                return int(d[len(prefix):])
    except OSError:
        pass

    return -1

def _mkdir_retry(path):
    # resctrl mkdir can transiently fail with EBUSY after CDP
    # mount churn (sequential CDP mounts are an expert-only path);
    # one retry after a second absorbs it.
    if not os.system("mkdir %s" % path):
        return 0
    time.sleep(1)
    return -1 if os.system("mkdir %s" % path) else 0

def mkdir_ctrl_group(ctrl_group, mon_group):
    ctrl_group_p = resctrl_path + "/" + ctrl_group
    mon_group_p = ctrl_group_p + "/mon_groups/" + mon_group

    if os.path.exists(ctrl_group_p):
        if not mon_group:
            print("rmdir %s" % ctrl_group_p)
            os.system("rmdir %s" % ctrl_group_p)

            print("create %s" % ctrl_group_p)
            if _mkdir_retry(ctrl_group_p):
                return -1
    else:
        print("create %s" % ctrl_group_p)
        if _mkdir_retry(ctrl_group_p):
            return -1

    if not mon_group:
        return 0

    print("create %s" % mon_group_p)
    if _mkdir_retry(mon_group_p):
        return -1

    return 0

def rmdir_ctrl_group(ctrl_group, mon_group):
    ctrl_group_p = resctrl_path + "/" + ctrl_group
    mon_group_p = ctrl_group_p + "/mon_groups/" + mon_group

    if mon_group:
        print("remove %s" % mon_group_p)
        if os.system("rmdir %s" % mon_group_p):
            return -1
        return 0

    print("remove %s" % ctrl_group_p)
    if os.system("rmdir %s" % ctrl_group_p):
        return -1

    return 0

def put_pid_resctrl(bm_pid, ctrl_group, mon_group = None):
    if not mon_group:
        ctrl_group_p = ("%s/%s/tasks" % (resctrl_path, ctrl_group))
        print("put pid: %d into %s group" % (bm_pid, ctrl_group))

    else:
        ctrl_group_p = ("%s/%s/mon_groups/%s/tasks" % (resctrl_path, ctrl_group, mon_group))
        print("put pid: %d into %s/%s group" % (bm_pid, ctrl_group, mon_group))

    return os.system("echo %d > %s" % (bm_pid, ctrl_group_p))

def put_cpu_resctrl(cpu_id, ctrl_group, mon_group = None):
    if not mon_group:
        ctrl_group_p = ("%s/%s/cpus_list" % (resctrl_path, ctrl_group))
        print("put cpu: %d into %s group" % (cpu_id, ctrl_group))

    else:
        ctrl_group_p = ("%s/%s/mon_groups/%s/cpus_list" % (resctrl_path, ctrl_group, mon_group))
        print("put cpu: %d into %s/%s group" % (cpu_id, ctrl_group, mon_group))

    return os.system("echo %d > %s" % (cpu_id, ctrl_group_p))

def get_cpu_id():
    command = "lscpu | grep 'BIOS Model name:'"
    process = subprocess.Popen(command, shell=True,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    if process.returncode != 0:
        print(stderr.decode())
        return -1

    output = stdout.decode().strip()
    if not output:
        return -1

    return output.split()[4]

def start_benchmark(cpuno, numa_id, name, resource):
    # On emulated platforms the monitor counters are configuration-derived,
    # not traffic-derived, so the benchmark only needs to keep the test
    # group's task alive - shorten the workload to keep the suite fast.
    fast = not on_hw()

    if name == "bw_mem":
        # 减少工作集与迭代次数便于在FPGA上快速跑完
        if resource == "L2":
            size = "8M" if fast else "256M"
            times = 1 if fast else 10
            procs = 1
            command = "taskset -c %d bw_mem -P %d -N %d %s rd" % (cpuno, procs, times, size)
        else:
            size = "16M" if fast else "64M"
            times = 1
            procs = 8
            command = "numactl -N %d bw_mem -P %d -N %d %s rd" % (numa_id, procs, times, size)
        print("%s" % command)

    elif name == "lat_mem_rd":
        size_KB = get_cache_size(cpuno, resource)
        print("%s size: %s" % (resource, size_KB))
        size_MB = int(size_KB[:-1]) >> (10 - 1)

        command = "numactl -C %d -m %d lat_mem_rd -N 3 -P 1 %dM 512" % (cpuno, numa_id, size_MB)
        print(command)

    elif name == "stress-ng":
        size_KB = get_cache_size(cpuno, resource)
        cpu_list = find_cpu_to_cache_sharelist(cpuno, resource)
        duration = "3s" if fast else "20s"

        print("%s size: %s" % (resource, size_KB))

        if resource == "L2":
            command = "taskset -c %d stress-ng --cache 1 --aggressive -t %s" % (cpuno, duration)
        else:
            command = "numactl -C %s stress-ng --cache 6 --aggressive -t %s" % (cpu_list, duration)
        print(command)

    try:
        proc = subprocess.Popen(command, shell=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
    except FileNotFoundError:
        print("%s not exist" % name)
        return -1

    print("create benchmark pid: %d" % proc.pid)
    return proc

def end_benchmark(proc, name):
    if name == "bw_mem":
        cnt = proc.stderr.readlines()
        res = cnt[0].decode('utf-8')

        result = res.split(' ')

        pool = float(result[0])
        bandwidth = float(result[1])

        print("pid %d pool %f MB bandwidth: %f MB/s" % (proc.pid, pool, bandwidth))

        return bandwidth

    elif name == "lat_mem_rd":
        cnt = proc.stderr.readlines()
        for line in cnt[1:]:
            res = line.decode('utf-8')
            print(res.replace("\n", ""))

    elif name == "stress-ng":
        proc.wait()
        if proc.returncode != 0:
            print(proc.stderr.decode())

    return

def find_cpu_to_cacheid(cpuno, resource):
    if resource[0] != 'L':
        return -1

    cacheid_p = ("%s%d/cache/index%c/id" %
                (cache_topology, cpuno, resource[1]))

    fp = open(cacheid_p)
    cache_id = fp.read()
    fp.close()

    return int(cache_id)

def find_cpu_to_cache_sharelist(cpuno, resource):
    if resource[0] != 'L':
        return -1

    cacheid_p = ("%s%d/cache/index%c/shared_cpu_list" %
                (cache_topology, cpuno, resource[1]))

    fp = open(cacheid_p)
    cpu_list = fp.read()
    fp.close()

    return cpu_list

def read_resource_monitor_val(ctrl_group, resource, id, monitor):
    monitor_p = ("%s/%s/mon_data/mon_%s_%02d/%s" %
                (resctrl_path, ctrl_group, resource, id, monitor))

    fp = open(monitor_p)
    val = fp.read()
    fp.close()

    return int(val)

def monitor_val_path(ctrl_group, resource, dom_id, monitor):
    return ("%s/%s/mon_data/mon_%s_%02d/%s" %
            (resctrl_path, ctrl_group, resource, dom_id, monitor))

def read_monitor_val(cpuno, resource, ctrl_group, monitor, dom_id=-1):
    if resource[0] == 'L':
        dom_id = find_cpu_to_cacheid(cpuno, resource)

    # Prefer the per-cpu domain dir named by the sysfs cache id; mainline
    # names mon_L3_* after the monitor component id, so fall back to the
    # first mon_<resource>_* dir that actually exists.
    if not os.path.exists(monitor_val_path(ctrl_group, resource, dom_id, monitor)):
        glob_dom = find_mon_dom(ctrl_group, resource)
        if glob_dom >= 0:
            dom_id = glob_dom

    val = read_resource_monitor_val(ctrl_group, resource, dom_id, monitor)
    if not val:
        # try again
        val = read_resource_monitor_val(ctrl_group, resource, dom_id, monitor)

    print("read %s %s/%d %s: %d" % (ctrl_group, resource, dom_id, monitor, val))
    return val

def write_schmata(ctrl_grp, resource, cpuno, cnt, dom_id=-1):
    path = ("%s/%s/schemata" % (resctrl_path, ctrl_grp))

    if "MB" in resource:
        # The MB-family domain id is NUMA-node based on OLK but
        # L3-cache-id based on mainline - take it from the schemata.
        res_dom = get_resource_dom(resource)
        if res_dom >= 0:
            dom_id = res_dom
        cnt = ("%s:%d=%d" % (resource, dom_id, cnt))

    elif "PRIO" in resource or "MIN" in resource or "MAX" in resource:
        dom_id = find_cpu_to_cacheid(cpuno, resource)
        cnt = ("%s:%d=%d" % (resource, dom_id, cnt))

    else:
        dom_id = find_cpu_to_cacheid(cpuno, resource)
        cnt = ("%s:%d=%x" % (resource, dom_id, cnt))

    print(path, cnt)

    # os.system() returns a positive wait status on failure, never -1
    return 0 if os.system("echo %s > %s" % (cnt, path)) == 0 else -1

def check_bandwidth_values(values, resource):
    for v in values:
        if not v:
            print("Check %s bandwidth value fail" % resource)
            return -1

    return 0

def check_occupancy_values(cpuno, values, resource):
    size_KB = get_cache_size(cpuno, resource)
    size = int(size_KB[:-1])

    for v in values:
        v = v >> 10
        if v > size:
            print("%d KB larger than %s cache size: %d KB" % (v, resource, size))
            return -1

    return 0

def get_cache_size(cpuno, resource):

    if resource[0] != 'L':
        return -1

    path = ("%s%d/cache/index%c/size" % (cache_topology, cpuno, resource[1]))

    fp = open(path)
    size = fp.read()
    fp.close()

    return size.replace("\n", "")

def get_cbm_mask(resource):
    path = ("%s/info/%s/cbm_mask" % (resctrl_path, resource))

    fp = open(path)
    mask = fp.read()
    fp.close()

    return int(mask, 16)

def umount_resctrl():
    os.system("umount " + resctrl_path)
    return

def mount_resctrl_fs(mount_option):
    test_info = "Check mount resctrl fs"

    if not os.path.isdir(resctrl_path):
        return -1

    if os.listdir(resctrl_path):
        umount_resctrl()

    if mount_option:
        # OLK's -o cdp splits L3 and L2 together; mainline needs the
        # extra cdpl2 option. Try the combined options first so only a
        # single mount cycle happens (sequential CDP remounts are an
        # expert-only path and can disturb closid/rmid state).
        opts = mount_option
        if "cdp" in mount_option and "l2" in mount_option and \
           "cdpl2" not in mount_option:
            opts = mount_option + ",cdpl2"

        ret = os.system("mount -t resctrl resctrl %s -o %s,debug" %
                        (resctrl_path, opts))
        if ret and opts != mount_option:
            ret = os.system("mount -t resctrl resctrl %s -o %s,debug" %
                            (resctrl_path, mount_option))
    else:
        ret = os.system("mount -t resctrl resctrl %s -o debug" % resctrl_path)

    if ret:
        print("Fail: %s" % test_info)
        return -1

    raise_reclaim_threshold()

    print("Pass: %s" % test_info)
    return 0

def raise_reclaim_threshold():
    """Raise max_threshold_occupancy to the kernel's cap.

    Mainline holds a deleted group's RMID in limbo until its occupancy
    reads below the reclaim threshold (real hardware occupancy decays,
    emulation's does not), so the suite's create/remove churn would
    exhaust the halved-under-CDP RMID pool with un-reclaimable entries.
    Try the L3 size first; mainline caps the value at the smallest
    monitored cache instance and reports the cap in last_cmd_status,
    which is then used for the retry.
    """
    import re

    path = resctrl_path + "/info/L3_MON/max_threshold_occupancy"
    if not os.path.exists(path):
        return

    try:
        size_kb = get_cache_size(0, "L3")
        size = int(size_kb[:-1]) << 10
    except (OSError, ValueError):
        return

    if not os.system("echo %d > %s" % (size, path)):
        return

    try:
        with open(resctrl_path + "/info/last_cmd_status") as f:
            status = f.read()

        limit = int(re.search(r"of (\d+) bytes", status).group(1))
    except (OSError, AttributeError, ValueError):
        return

    os.system("echo %d > %s" % (limit, path))
