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

import os, sys, subprocess, time
from mpam_lib import mkdir_ctrl_group, put_pid_resctrl, start_benchmark, end_benchmark, read_monitor_val, write_schmata, put_cpu_resctrl

resctrl_path = "/sys/fs/resctrl"

def cat_group_tasks(ctrl_group, mon_group):
    if not mon_group:
        monitor_p = ("%s/%s/tasks" % (resctrl_path, ctrl_group))
    else:
        monitor_p = ("%s/%s/mon_groups/%s/tasks" % (resctrl_path, ctrl_group, mon_group))

    fp = open(monitor_p)
    val = fp.read()
    fp.close()

    val = val.replace("\n", " ")

    print("%s/%s tasks: %s" % (ctrl_group, mon_group, val))
    return val

def run_sleep():
    proc = subprocess.Popen("sleep 10", shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)

    return proc

def run_task_test():

    local_task = os.getpid()

    ctrl_group = "p1"
    mon_group1 = "m1"
    mon_group2 = "m2"

    if mkdir_ctrl_group(ctrl_group, ""):
        return -1

    if put_pid_resctrl(local_task, ctrl_group):
        return -1

    if mkdir_ctrl_group(ctrl_group, mon_group1):
        return -1

    if mkdir_ctrl_group(ctrl_group, mon_group2):
        return -1

    proc1 = run_sleep()
    if not proc1:
        return -1

    if put_pid_resctrl(proc1.pid, ctrl_group, mon_group1):
        return -1

    proc2 = run_sleep()
    if not proc2:
        return -1

    if put_pid_resctrl(proc2.pid, ctrl_group, mon_group2):
        return -1

    # check moving tasks
    task0 = cat_group_tasks(ctrl_group, None)
    if str(proc1.pid) not in task0:
        print("move task %d fail" % proc1.pid)
        return -1

    if str(proc2.pid) not in task0:
        print("move task %d fail" % proc2.pid)
        return -1

    task1 = cat_group_tasks(ctrl_group, mon_group1)
    if str(proc1.pid) not in task1:
        print("move task %d fail" % proc1.pid)
        return -1

    task2 = cat_group_tasks(ctrl_group, mon_group2)
    if str(proc2.pid) not in task2:
        print("move task %d fail" % proc2.pid)
        return -1

    if put_pid_resctrl(proc2.pid, ctrl_group, mon_group1):
        return -1

    task3 = cat_group_tasks(ctrl_group, mon_group1)
    if str(proc2.pid) not in task3:
        print("move task %d fail" % proc2.pid)
        return -1

    if str(proc2.pid) not in task0:
        print("move task %d fail" % proc2.pid)
        return -1

    print("Pass: Check task migration")
    return 0

def get_cpuid_from_numa(numa_id):
    proc = subprocess.Popen("lscpu | grep 'NUMA node%d'" % numa_id,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)

    res = proc.stdout.readline().decode('utf-8')
    cpuid = res.split(' ')[-1].split('-')[0]

    return int(cpuid)

def run_sub_monitor_test():

    local_task = os.getpid()

    ctrl_group = "p1"
    mon_group1 = "m1"
    mon_group2 = "m2"

    numa_id1 = 0
    numa_id2 = 1
    cpuno1 = 0
    cpuno2 = get_cpuid_from_numa(numa_id2)

    benchmark = "bw_mem"
    resource_mb = "MB"
    resource_l3 = "L3"

    monitor_list = {
        "MB" : "mbm_total_bytes",
        "L3" : "llc_occupancy",
    }

    if mkdir_ctrl_group(ctrl_group, ""):
        return -1

    if put_pid_resctrl(local_task, ctrl_group):
        return -1

    if mkdir_ctrl_group(ctrl_group, mon_group1):
        return -1

    if mkdir_ctrl_group(ctrl_group, mon_group2):
        return -1

    # check partition and monitor functions
    if write_schmata(ctrl_group, "MBHDL", cpuno1, 0, numa_id1) < 0:
        return -1

    if write_schmata(ctrl_group, resource_mb, cpuno1, 100, numa_id1) < 0:
        return -1

    if write_schmata(ctrl_group, "MBHDL", cpuno2, 1, numa_id2) < 0:
        return -1

    if write_schmata(ctrl_group, resource_mb, cpuno2, 10, numa_id2) < 0:
        return -1

    if write_schmata(ctrl_group, resource_l3, cpuno2, 1, numa_id2) < 0:
        return -1

    proc1 = start_benchmark(cpuno1, numa_id1, benchmark, resource_mb)
    if not proc1:
        return -1

    if put_pid_resctrl(proc1.pid, ctrl_group, mon_group1):
        return -1

    proc2 = start_benchmark(cpuno2, numa_id2, benchmark, resource_mb)
    if not proc2:
        return -1

    if put_pid_resctrl(proc2.pid, ctrl_group, mon_group2):
        return -1

    time.sleep(3)

    for resource in [resource_mb, resource_l3]:
        val1 = read_monitor_val(cpuno1, resource, ctrl_group,
                                monitor_list[resource], numa_id1)
        val2 = read_monitor_val(cpuno2, resource, ctrl_group,
                                monitor_list[resource], numa_id2)

        if val1 < val2:
            print("%s Partition failed" % resource)

            end_benchmark(proc1, benchmark)
            end_benchmark(proc2, benchmark)
            return -1

    for resource in [resource_mb, resource_l3]:
        val1 = read_monitor_val(cpuno1, resource,
                                "%s/mon_groups/%s" % (ctrl_group, mon_group1),
                                monitor_list[resource], numa_id1)
        val2 = read_monitor_val(cpuno2, resource,
                                "%s/mon_groups/%s" % (ctrl_group, mon_group2),
                                monitor_list[resource], numa_id2)
        if val1 < val2:
            print("%s Monitoring failed" % resource)

            end_benchmark(proc1, benchmark)
            end_benchmark(proc2, benchmark)
            return -1

    end_benchmark(proc1, benchmark)
    end_benchmark(proc2, benchmark)

    print("Pass: Check sub-monitor group")
    return 0
