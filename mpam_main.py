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

import os, sys, subprocess
import mpam_lib
from mpam_mbm import run_mbm_test
from mpam_mba import run_mba_test
from mpam_cmt import run_cmt_test
from mpam_cat import run_cat_test
from mpam_feat import run_prio_test, run_min_test, run_max_test
from mpam_limit import run_limit_test
from mpam_precision import run_precision_test, run_l3_precision_test
# from mpam_mon_limit import run_mon_limit_test, run_mon_1024_test
from mpam_task import run_task_test, run_sub_monitor_test
from mpam_cpu import run_cpu_test
from mpam_smmu import run_smmu_mon_test, run_smmu_part_test
from mpam_hdl import run_hdl_test

resctrl_path = "/sys/fs/resctrl"

def check_mount_point():
    test_info = "Check resctrl mountpoint exists"

    ret = os.path.exists(resctrl_path)
    if not ret:
        print("Fail: %s" % test_info)
        return -1

    print("Pass: %s" % test_info)
    return 0

def mpam_test_main(argv):
    if check_mount_point():
        return -1

    mount_opt = []

    if "cdp" in argv:
        mount_opt.append("cdp")
        cdp_enable = True
    else:
        cdp_enable = False

    if "L2" in argv:
        mount_opt.append("l2")

    if mpam_lib.mount_resctrl_fs(','.join(mount_opt)):
        return -1

    if "mbm" in argv:
        if "MB" in argv:
            if run_mbm_test("MB"):
                return -1
        if "L2" in argv:
            if run_mbm_test("L2"):
                return -1

    if "mba" in argv:
        if "MB" in argv:
            if run_mba_test("MB"):
                return -1

    if "cmt" in argv:
        if "L2" in argv:
            if run_cmt_test("L2"):
                return -1
        if "L3" in argv:
            if run_cmt_test("L3"):
                return -1

    if "cat" in argv:
        if "L2" in argv:
            if cdp_enable:
                if run_cat_test("L2CODE"):
                    return -1

                if run_cat_test("L2DATA"):
                    return -1
            else:
                if run_cat_test("L2"):
                    return -1

        if "L3" in argv:
            if cdp_enable:
                if run_cat_test("L3CODE"):
                    return -1

                if run_cat_test("L3DATA"):
                    return -1
            else:
                if run_cat_test("L3"):
                    return -1

    if "prio" in argv:
        if "MB" in argv:
            if run_prio_test("MB"):
                return -1
        if "L3" in argv:
            if run_prio_test("L3"):
                return -1

    if "max" in argv:
        if "L3" in argv:
            if mpam_lib.get_cpu_id() in ["950", "920G"]:
                if run_max_test("L3"):
                    return -1

    if "min" in argv:
        if "MB" in argv:
            if run_min_test("MB"):
                return -1
        if "L3" in argv:
            if mpam_lib.get_cpu_id() in ["950", "920G"]:
                if run_min_test("L3"):
                    return -1

    if "hdl" in argv:
        if "MB" in argv:
            if run_hdl_test("MB"):
                return -1

    if "limit" in argv:
        if run_limit_test():
            return -1

        # if run_mon_limit_test():
        #     return -1

        # if run_mon_1024_test():
        #     return -1

    if "precision" in argv:
        if "MB" in argv:
            if run_precision_test():
                return -1
        if "L3" in argv:
            if mpam_lib.get_cpu_id() in ["950", "920G"]:
                if run_l3_precision_test():
                    return -1

    if "task" in argv:
        if run_task_test():
            return -1

    if "cpu" in argv:
        if run_cpu_test():
            return -1

    if "sub_mon" in argv:
        if run_sub_monitor_test():
            return -1

    if "smmu" in argv:
        dev = "eno2"
        remote_ip = "192.168.1.31"

        for arg in argv:
            if arg.startswith("--dev="):
                dev = arg.split("=", 1)[1]

            if arg.startswith("--ip="):
                remote_ip = arg.split("=", 1)[1]

        if "mbm" in argv:
            if run_smmu_mon_test(dev, remote_ip):
                return -1

        if "mba" in argv:
            if run_smmu_part_test(dev, remote_ip):
                return -1

    return 0

if __name__ == "__main__":
    ret = mpam_test_main(sys.argv)
    sys.exit(ret)

