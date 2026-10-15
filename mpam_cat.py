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
cache_topology = "/sys/devices/system/cpu/cpu"

def get_mask_count(mask):

    count = 0
    while mask > 0:
        mask = mask >> 1
        count = count + 1

    return count

def run_cat_test(resource):
    print("run_cat_test %s begin:" % resource)

    cpuno = 0
    ctrl_grp = "p1"
    monitor_list = {
        "L2" : "l2c_occupancy",
        "L2CODE" : "l2c_occupancy",
        "L2DATA" : "l2c_occupancy",

        "L3" : "llc_occupancy",
        "L3CODE" : "llc_occupancy",
        "L3DATA" : "llc_occupancy",
    }
    benchmark = "stress-ng"

    res = mpam_lib.check_resource_mon(resource[0:2], monitor_list[resource])
    if res < 0:
        return -1

    if res > 0:
        # resource not support, skip the test
        return 0

    mask = mpam_lib.get_cbm_mask(resource)
    print("%s mask: %x" % (resource, mask))

    cache_size = mpam_lib.get_cache_size(cpuno, resource)
    print("%s size: %s" % (resource, cache_size))

    # set root control group mask = 1
    if mpam_lib.write_schmata("", resource, cpuno, 1) < 0:
        return -1

    count = get_mask_count(mask)

    pre_size = 0
    for i in range(0, count):
        if mpam_lib.mkdir_ctrl_group(ctrl_grp, ""):
            return -1

        if mpam_lib.put_pid_resctrl(os.getpid(), ctrl_grp):
            return -1

        if mpam_lib.write_schmata(ctrl_grp, resource, cpuno, mask) < 0:
            return -1

        proc = mpam_lib.start_benchmark(cpuno, 0, benchmark, resource)
        mpam_lib.end_benchmark(proc, benchmark)

        size = mpam_lib.read_monitor_val(cpuno, resource[0:2], ctrl_grp, monitor_list[resource])

        if pre_size and size > pre_size:
            print("Fail: run_cat_test %s" % resource)
            return -1

        mpam_lib.rmdir_ctrl_group(ctrl_grp, "")

        mask = mask >> 1

    print("Pass: run_cat_test %s" % resource)
    return 0
