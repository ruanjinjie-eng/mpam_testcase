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

def run_cmt_test(resource):
    print("run_cmt_test %s begin:" % resource)

    monitor_list = {
        "L2" : "l2c_occupancy",
        "L3" : "llc_occupancy",
    }
    ctrl_grp = "p1"
    cpuno = 0
    numa_id = 0
    benchmark = "stress-ng"

    res = mpam_lib.check_resource_mon(resource, monitor_list[resource])
    if res < 0:
        return -1

    if res > 0:
        # resource not support, skip the test
        return 0

    if mpam_lib.mkdir_ctrl_group(ctrl_grp, ""):
        return -1

    if mpam_lib.put_pid_resctrl(os.getpid(), ctrl_grp):
        return -1

    proc = mpam_lib.start_benchmark(cpuno, numa_id, benchmark, resource)
    if not proc:
        return -1

    mpam_lib.end_benchmark(proc, benchmark)

    res = []
    for i in range(0, 5):
        time.sleep(1)
        res.append(mpam_lib.read_monitor_val(cpuno, resource, ctrl_grp, monitor_list[resource]))

    for level in ["L0", "L2", "L3"]:
        print("%s size: %s" % (level, mpam_lib.get_cache_size(cpuno, level)))

    if mpam_lib.check_occupancy_values(cpuno, res, resource) < 0:
        print("Fail: Check run_cmt_test %s" % resource)
        return -1

    print("Pass: Check run_cmt_test %s" % resource)
    return 0
