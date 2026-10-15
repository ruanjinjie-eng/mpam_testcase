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

import mpam_lib

resctrl_path = "/sys/fs/resctrl"

def get_closid_number():
    path = ("%s/info/MB/num_closids" % (resctrl_path))

    fp = open(path)
    size = fp.read()
    fp.close()

    return int(size)

def get_pmg_number():
    return 4

def get_rmid_group(ctrl_grp, mon_group):

    if mon_group:
        path = ("%s/%s/mon_groups/%s/rmid" % (resctrl_path, ctrl_grp, mon_group))
    else:
        path = ("%s/%s/rmid" % (resctrl_path, ctrl_grp))

    fp = open(path)
    rmid = fp.read()
    fp.close()

    return int(rmid)

def run_mon_limit_test():
    test_info = "Check monitor limit"

    print("run_limit_test begin:")

    if mpam_lib.mount_resctrl_fs(None):
        return -1

    partid = get_closid_number()
    pmg = get_pmg_number()

    # create mon_group under root ctrl group
    print("ctrl_grp root rmid: %d" % get_rmid_group("", ""))

    for j in range(1, 4):
        mon_group = ("m%d" % j)
        if mpam_lib.mkdir_ctrl_group("", mon_group):
            return -1

        print("mon_group root/%s rmid: %d" %
             (mon_group, get_rmid_group("", mon_group)))

    for i in range(1, partid):
        ctrl_grp = ("p%d" % i)

        if mpam_lib.mkdir_ctrl_group(ctrl_grp, ""):
            return -1

        print("ctrl_grp %s rmid: %d" %
             (ctrl_grp, get_rmid_group(ctrl_grp, "")))

        for j in range(1, pmg):
            mon_group = ("m%d" % j)
            if mpam_lib.mkdir_ctrl_group(ctrl_grp, mon_group):
                return -1

            print("mon_group %s/%s rmid: %d" %
                 (ctrl_grp, mon_group, get_rmid_group(ctrl_grp, mon_group)))

    for i in range(4, 900):
        mon_group = ("m%d" % i)
        if mpam_lib.mkdir_ctrl_group("p1", mon_group):
            return -1

    for i in range(1, partid):
        ctrl_grp = ("p%d" % i)

        for j in range(1, pmg):
            mon_group = ("m%d" % j)
            if mpam_lib.rmdir_ctrl_group(ctrl_grp, mon_group):
                return -1

        if mpam_lib.rmdir_ctrl_group(ctrl_grp, ""):
            return -1

    print("Pass: %s" % test_info)
    return 0

def run_mon_1024_test():
    test_info = "Check 1024 monitors limit"

    print("run_limit_test begin:")

    if mpam_lib.mount_resctrl_fs(None):
        return -1

    partid = get_closid_number()
    pmg = get_pmg_number()

    # create mon_group under root ctrl group
    print("ctrl_grp root rmid: %d" % get_rmid_group("", ""))

    for j in range(1, 1024):
        mon_group = ("m%d" % j)
        if mpam_lib.mkdir_ctrl_group("", mon_group):
            return -1

        print("mon_group root/%s rmid: %d" %
             (mon_group, get_rmid_group("", mon_group)))

    print("Pass: %s" % test_info)
    return 0
