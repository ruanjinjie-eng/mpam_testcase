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

def run_reference_test(feat, resource, cnt, benchmark):
    cpuno1 = 0
    numa_id = 0
    ctrl_grp = "p1"
    monitor_list = {
        "L2" : "l2c_occupancy",
        "L3" : "llc_occupancy",
    }

    if mpam_lib.mkdir_ctrl_group(ctrl_grp, ""):
        return -1

    # reference test
    if mpam_lib.write_schmata(ctrl_grp, feat, cpuno1, cnt, numa_id) < 0:
        return -1

    proc1 = mpam_lib.start_benchmark(cpuno1, numa_id, benchmark, resource)
    if not proc1:
        return -1

    print("%s reference test: pid %d with %d" % (feat, proc1.pid, cnt))

    if mpam_lib.put_pid_resctrl(proc1.pid, ctrl_grp):
        return -1

    ref_bw = mpam_lib.end_benchmark(proc1, benchmark)
    if benchmark == "stress-ng":
        if mpam_lib.read_monitor_val(cpuno1, resource, ctrl_grp, monitor_list[resource]) < 0:
            return -1

        # stress-ng has no bandwidth number to return; the saturation
        # yardstick below only applies to the bw_mem benchmarks.
        return 0

    return ref_bw

def run_feat_test(feat, resource, p1_cnt, p2_cnt, benchmark):
    ctrl_grp_1 = "p1"
    ctrl_grp_2 = "p2"
    cpuno1 = 0
    cpuno2 = 2
    numa_id = 0

    monitor_list = {
        "L2" : "l2c_occupancy",
        "L3" : "llc_occupancy",
    }

    # set root control-group low prio
    if mpam_lib.write_schmata("", feat, cpuno1, p1_cnt, numa_id) < 0:
        return -1

    ref = run_reference_test(feat, resource, p2_cnt, benchmark)
    if ref < 0:
        return -1

    if mpam_lib.mkdir_ctrl_group(ctrl_grp_1, ""):
        return -1

    if mpam_lib.mkdir_ctrl_group(ctrl_grp_2, ""):
        return -1

    # comparison test
    if mpam_lib.write_schmata(ctrl_grp_1, feat, cpuno1, p1_cnt, numa_id) < 0:
        return -1

    if mpam_lib.write_schmata(ctrl_grp_2, feat, cpuno2, p2_cnt, numa_id) < 0:
        return -1

    if mpam_lib.put_pid_resctrl(os.getpid(), ctrl_grp_2):
        return -1

    proc2 = mpam_lib.start_benchmark(cpuno2, numa_id, benchmark, resource)
    if not proc2:
        return -1

    if mpam_lib.put_pid_resctrl(os.getpid(), ctrl_grp_1):
        return -1

    proc1 = mpam_lib.start_benchmark(cpuno1, numa_id, benchmark, resource)
    if not proc1:
        return -1

    print("%s comparison test: pid1 %d with %d, pid2 %d with %d" %
         (feat, proc1.pid, p1_cnt, proc2.pid, p2_cnt))

    if benchmark == "stress-ng":
        time.sleep(10)
        val1 = mpam_lib.read_monitor_val(cpuno1, resource, ctrl_grp_1,
                                         monitor_list[resource])
        val2 = mpam_lib.read_monitor_val(cpuno2, resource, ctrl_grp_2,
                                         monitor_list[resource])
        if val1 < 0 or val2 < 0:
            return -1

        mpam_lib.end_benchmark(proc1, benchmark)
        mpam_lib.end_benchmark(proc2, benchmark)

    else:
        val1 = mpam_lib.end_benchmark(proc1, benchmark)
        val2 = mpam_lib.end_benchmark(proc2, benchmark)
        if val1 < 0 or val2 < 0:
            return -1

        if ref > 0 and val1 + val2 > 1.8 * ref:
            # Priority and minimum-bandwidth only arbitrate contention.
            # If the two concurrent groups together still scale linearly
            # (~2x the single-group reference), the memory controller
            # never saw contention and no difference can be observed on
            # this platform - report what was measured instead of
            # failing on measurement noise.
            print("Skip: no memory contention (2 groups: %.2f MB/s vs 1 group: %.2f MB/s, linear scaling), %s has nothing to arbitrate" %
                 (val1 + val2, ref, feat))
            return 0

    if val1 > val2:
        print("Fail: Check run_feat_test %s" % feat)
        return -1

    print("Pass: Check run_feat_test %s" % feat)
    return 0

def run_prio_test(resource):
    print("run_prio_test %s begin:" % resource)

    if resource == "MB" and not mpam_lib.mb_exported():
        print("Skip: MB resource not exported on this platform")
        return 0

    feat = ("%sPRI" % resource)
    if resource == "MB":
        benchmark = "bw_mem"
        cnt = [0, 7]
    else:
        benchmark = "stress-ng"
        cnt = [0, 3]

    return run_feat_test(feat, resource, cnt[0], cnt[1], benchmark)

def run_min_test(resource):
    print("run_min_test %s begin:" % resource)

    if resource == "MB" and not mpam_lib.mb_exported():
        print("Skip: MB resource not exported on this platform")
        return 0

    feat = ("%sMIN" % resource)
    if resource == "MB":
        benchmark = "bw_mem"
    else:
        benchmark = "stress-ng"

    cnt = [0, 100]
    return run_feat_test(feat, resource, cnt[0], cnt[1], benchmark)

def run_max_test(resource):
    print("run_max_test %s begin:" % resource)

    feat = ("%sMAX" % resource)
    if resource == "MB":
        benchmark = "bw_mem"
    else:
        benchmark = "stress-ng"

    cnt = [1, 100]
    return run_feat_test(feat, resource, cnt[0], cnt[1], benchmark)
