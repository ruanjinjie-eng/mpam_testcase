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

def check_resource_mon(resource, monitor):
    test_info = ("Check %s msc monitor" % resource)
    path = resctrl_path + "/info/" + resource + "_MON"
    features = path + "/mon_features"

    ret = os.path.exists(features)
    if not ret:
        print("Fail: %s" % test_info)
        return -1

    with open(features, 'r') as f:
        cnt = f.read()

    if monitor not in cnt:
        print("Fail: %s" % test_info)
        return -1

    return 0

def mkdir_ctrl_group(ctrl_group, mon_group):
    ctrl_group_p = resctrl_path + "/" + ctrl_group
    mon_group_p = ctrl_group_p + "/mon_groups/" + mon_group

    if os.path.exists(ctrl_group_p):
        if not mon_group:
            print("rmdir %s" % ctrl_group_p)
            os.system("rmdir %s" % ctrl_group_p)

            print("create %s" % ctrl_group_p)
            if os.system("mkdir %s" % ctrl_group_p):
                return -1
    else:
        print("create %s" % ctrl_group_p)
        if os.system("mkdir %s" % ctrl_group_p):
            return -1

    if not mon_group:
        return 0

    print("create %s" % mon_group_p)
    if os.system("mkdir %s" % mon_group_p):
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
    if name == "bw_mem":
        if resource == "L2":
            size = "4096M"
            times = 100
            command = "taskset -c %d bw_mem -P 1 -N %d %s rd" % (cpuno, times, size)
        else:
            size = "512M"
            times = 1
            command = "numactl -N %d bw_mem -P 16 -N %d %s rd" % (numa_id, times, size)
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

        print("%s size: %s" % (resource, size_KB))

        if resource == "L2":
            command = "taskset -c %d stress-ng --cache 1 --aggressive -t 20s" % cpuno
        else:
            command = "numactl -C %s stress-ng --cache 6 --aggressive -t 20s" % cpu_list
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

def read_monitor_val(cpuno, resource, ctrl_group, monitor, dom_id=-1):
    if resource[0] == 'L':
        dom_id = find_cpu_to_cacheid(cpuno, resource)

    val = read_resource_monitor_val(ctrl_group, resource, dom_id, monitor)
    if not val:
        # try again
        val = read_resource_monitor_val(ctrl_group, resource, dom_id, monitor)

    print("read %s %s/%d %s: %d" % (ctrl_group, resource, dom_id, monitor, val))
    return val

def write_schmata(ctrl_grp, resource, cpuno, cnt, dom_id=-1):
    path = ("%s/%s/schemata" % (resctrl_path, ctrl_grp))

    if "MB" in resource:
        cnt = ("%s:%d=%d" % (resource, dom_id, cnt))

    elif "PRIO" in resource or "MIN" in resource or "MAX" in resource:
        dom_id = find_cpu_to_cacheid(cpuno, resource)
        cnt = ("%s:%d=%d" % (resource, dom_id, cnt))

    else:
        dom_id = find_cpu_to_cacheid(cpuno, resource)
        cnt = ("%s:%d=%x" % (resource, dom_id, cnt))

    print(path, cnt)
    return os.system("echo %s > %s" % (cnt, path))

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
        ret = os.system("mount -t resctrl resctrl %s -o %s,debug" %
                        (resctrl_path, mount_option))
    else:
        ret = os.system("mount -t resctrl resctrl %s -o debug" % resctrl_path)

    if ret:
        print("Fail: %s" % test_info)
        return -1

    print("Pass: %s" % test_info)
    return 0
