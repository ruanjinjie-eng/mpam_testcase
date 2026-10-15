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
from mpam_lib import mkdir_ctrl_group, put_cpu_resctrl, start_benchmark, end_benchmark, read_monitor_val, write_schmata

resctrl_path = "/sys/fs/resctrl"

def run_cpu_test():

    ctrl_group1 = "p1"
    ctrl_group2 = "p2"

    cpu0 = 10
    cpu1 = 11

    monitor_list = {
        "L2" : "mbm_core_bytes",
        "MB" : "mbm_total_bytes",
    }

    if mkdir_ctrl_group(ctrl_group1, ""):
        return -1

    if put_cpu_resctrl(cpu0, ctrl_group1):
        return -1

    if mkdir_ctrl_group(ctrl_group2, ""):
        return -1

    if put_cpu_resctrl(cpu1, ctrl_group2):
        return -1

    proc1 = start_benchmark(cpu0, None, "bw_mem", "L2")
    if not proc1:
        return -1

    time.sleep(3)
    res = read_monitor_val(cpu0, "MB", ctrl_group1, monitor_list["MB"], 0)
    res = read_monitor_val(cpu0, "MB", ctrl_group1, monitor_list["MB"], 0)
    if res == 0:
        print("Fail: Check run_cpu_test")
        return -1

    res = read_monitor_val(cpu1, "MB", ctrl_group2, monitor_list["MB"], 0)
    res = read_monitor_val(cpu1, "MB", ctrl_group2, monitor_list["MB"], 0)
    if res != 0:
        print("Fail: Check run_cpu_test")
        return -1

    end_benchmark(proc1, "bw_mem")

    print("Pass: Check run_cpu_test")
    return 0
