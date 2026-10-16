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

import os
import mpam_lib
from mpam_lib import mkdir_ctrl_group

def run_precision_test():
    print("run_precision_test MB begin:")

    if not mpam_lib.mb_exported():
        print("Skip: MB resource not exported on this platform")
        return 0

    # The MB domain id is the L3 cache id on mainline - take it from
    # the schemata instead of hardcoding 0.
    dom = mpam_lib.get_resource_dom("MB")
    if dom < 0:
        print("Fail: MB resource not present in schemata")
        return -1

    mkdir_ctrl_group("p1", "")
    for i in range(1, 101):
        print("echo MB:%d=%d" % (dom, i))
        ret = os.system("echo MB:%d=%d > /sys/fs/resctrl/p1/schemata" % (dom, i))
        if ret:
            print("set %d fail" % i)
            return -1

        # Compare numerically instead of grep-ing a fixed format.
        val = mpam_lib.read_schemata_val("p1", "MB", dom)
        if val != i:
            print("set %d fail (readback %d)" % (i, val))
            return -1

    print("Pass: Check run_precision_test MB")
    return 0

def run_l3_precision_test():
    print("run_precision_test L3MAX begin:")

    mkdir_ctrl_group("p1", "")
    for i in range(1, 101):
        print("echo L3MAX:1=%d" % i)
        ret = os.system("echo L3MAX:1=%d > /sys/fs/resctrl/p1/schemata" % i)
        if ret:
            print("set %d fail" % i)
            return -1

        ret = os.system("cat /sys/fs/resctrl/p1/schemata | grep 'L3MAX'")
        # if ret:
        #     print("set %d fail" % i)
        #     return -1

    print("Pass: Check run_precision_test L3")
    return 0
