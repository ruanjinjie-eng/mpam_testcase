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

import os, time
import mpam_lib

resctrl_path = "/sys/fs/resctrl"

def run_mbm_test(resource):
    print("run_mbm_test %s begin:" % resource)

    cpuno = 0
    numa_id = 0
    monitor_list = {
        "L2" : "mbm_core_bytes",
        "MB" : "mbm_total_bytes",
    }
    ctrl_grp = "p1"
    benchmark = "bw_mem"

    # The mainline driver serves mbm_total_bytes under L3_MON/mon_L3_*,
    # not as a separate MB monitor resource.
    mon_res = "L3" if resource == "MB" else resource
    if resource == "MB" and not mpam_lib.mb_exported():
        print("Skip: MB resource not exported on this platform")
        return 0
    if mpam_lib.check_resource_mon(mon_res, monitor_list[resource]):
        return -1

    if mpam_lib.mkdir_ctrl_group(ctrl_grp, ""):
        return -1

    if mpam_lib.put_pid_resctrl(os.getpid(), ctrl_grp):
        return -1

    proc = mpam_lib.start_benchmark(cpuno, numa_id, benchmark, resource)
    if proc == -1:
        return -1

    res = []
    time.sleep(2)
    for i in range(0, 5):
        res.append(mpam_lib.read_monitor_val(cpuno, mon_res, ctrl_grp, monitor_list[resource], numa_id))

    mpam_lib.end_benchmark(proc, benchmark)

    if mpam_lib.check_bandwidth_values(res, resource) < 0:
        print("Fail: Check run_mbm_test %s" % resource)
        return -1

    print("Pass: Check run_mbm_test %s" % resource)
    return 0
