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

def run_mba_test(resource):
    print("run_mba_test %s begin:" % resource)

    monitor_list = {
        "MB" : "mbm_total_bytes",
    }
    ctrl_grp = "p1"
    cpuno = 0
    numa_id = 0
    benchmark = "bw_mem"

    # OLK exposes the bandwidth monitor as MB_MON/mon_MB_*; mainline
    # serves mbm_total_bytes under L3_MON/mon_L3_*.
    mon_res = mpam_lib.probe_bw_monitor()
    if not mon_res:
        print("Fail: no bandwidth monitor (MB_MON / L3_MON mbm_total_bytes)")
        return -1

    if mpam_lib.mkdir_ctrl_group(ctrl_grp, ""):
        return -1

    if mpam_lib.put_pid_resctrl(os.getpid(), ctrl_grp):
        return -1

    # set hardlimit
    if mpam_lib.write_schmata(ctrl_grp, "MBHDL", cpuno, 1, 0) < 0:
        return -1

    mb_res = []
    pre_bw = 0
    for p in range(10, 110, 10):
        if mpam_lib.write_schmata(ctrl_grp, resource, cpuno, p, 0) < 0:
            return -1

        proc = mpam_lib.start_benchmark(cpuno, numa_id, benchmark, resource)
        if not proc:
            return -1

        time.sleep(3)
        mb_res.append(mpam_lib.read_monitor_val(cpuno, mon_res, ctrl_grp, monitor_list[resource], numa_id))

        bw = mpam_lib.end_benchmark(proc, benchmark)

        # if bw < pre_bw:
        #     print("Fail: run_mba_test %s" % resource)
        #     return -1

        pre_bw = bw

    print("Pass: run_mba_test %s" % resource)
    return 0
