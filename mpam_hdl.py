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

def run_hdl_test(resource):
    print("run_hdl_test %s begin:" % resource)

    monitor_list = {
        "MB" : "mbm_total_bytes",
    }
    ctrl_grp = "p1"
    cpuno = 0
    numa_id = 0
    benchmark = "bw_mem"
    percent = 10

    # The mainline driver serves mbm_total_bytes under L3_MON, not as
    # a separate MB monitor resource.
    if not mpam_lib.mb_exported():
        print("Skip: MB resource not exported on this platform")
        return 0

    if mpam_lib.check_resource_mon("L3", monitor_list["MB"]):
        return -1

    if mpam_lib.mkdir_ctrl_group(ctrl_grp, ""):
        return -1

    if mpam_lib.put_pid_resctrl(os.getpid(), ctrl_grp):
        return -1

    # clear hardlimit
    if mpam_lib.write_schmata(ctrl_grp, "MBHDL", cpuno, 0, 0) < 0:
        return -1

    if mpam_lib.write_schmata(ctrl_grp, resource, cpuno, percent, 0) < 0:
        return -1

    proc = mpam_lib.start_benchmark(cpuno, numa_id, benchmark, resource)
    if not proc:
        return -1

    bw = mpam_lib.end_benchmark(proc, benchmark)

    # set hardlimit
    if mpam_lib.write_schmata(ctrl_grp, "MBHDL", cpuno, 1, 0) < 0:
        return -1

    if mpam_lib.write_schmata(ctrl_grp, resource, cpuno, percent, 0) < 0:
        return -1

    proc = mpam_lib.start_benchmark(cpuno, numa_id, benchmark, resource)
    if not proc:
        return -1

    bw_hdl = mpam_lib.end_benchmark(proc, benchmark)

    if bw < bw_hdl:
        print("Fail: run_hdl_test %s" % resource)
        return -1

    print("Pass: run_hdl_test %s" % resource)
    return 0
