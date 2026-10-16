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

resctrl_path = "/sys/fs/resctrl"

def get_closid_number():
    # The mainline driver does not export info/MB when the topology
    # does not match the L3; fall back to the L3 view of the count.
    for res in ("MB", "L3"):
        path = ("%s/info/%s/num_closids" % (resctrl_path, res))

        if not os.path.exists(path):
            continue

        fp = open(path)
        size = fp.read()
        fp.close()

        return int(size)

    print("Fail: no num_closids found (info/MB, info/L3)")
    return -1

def get_pmg_number():
    return 4

def get_rmid_group(ctrl_grp, mon_group):
    if mon_group:
        path = ("%s/%s/mon_groups/%s/mon_hw_id" % (resctrl_path, ctrl_grp, mon_group))
    else:
        path = ("%s/%s/mon_hw_id" % (resctrl_path, ctrl_grp))

    fp = open(path)
    rmid = fp.read()
    fp.close()

    return int(rmid)

def read_threshold(res):
    try:
        path = ("%s/info/%s_MON/max_threshold_occupancy" % (resctrl_path, res))

        fp = open(path)
        size = fp.read()
        fp.close()

    except FileNotFoundError:
        return -1

    return int(size)

def write_threshold(res, size):
    path = ("%s/info/%s_MON/max_threshold_occupancy" % (resctrl_path, res))

    if not os.system("echo %d > %s" % (size, path)):
        return 0

    # The mainline driver caps the value at the smallest monitored
    # cache instance and reports the cap in last_cmd_status - parse
    # it and retry with that value.
    try:
        import re

        with open(resctrl_path + "/info/last_cmd_status") as f:
            status = f.read()

        limit = int(re.search(r"of (\d+) bytes", status).group(1))
    except (OSError, AttributeError, ValueError):
        return -1

    return os.system("echo %d > %s" % (limit, path))

def disable_threshold(res):
    size_KB = mpam_lib.get_cache_size(0, res)
    size = int(size_KB[:-1]) << 10

    return write_threshold(res, size)

def run_limit_test():
    print("run_limit_test begin:")

    partid = get_closid_number()
    pmg = get_pmg_number()

    size = read_threshold("L3")
    if size > 0:
        ret = disable_threshold("L3")
        if ret:
            return -1

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
            print("Fail: Check run_limit_test")
            return -1

        print("ctrl_grp %s rmid: %d" %
             (ctrl_grp, get_rmid_group(ctrl_grp, "")))

        for j in range(1, pmg):
            mon_group = ("m%d" % j)
            if mpam_lib.mkdir_ctrl_group(ctrl_grp, mon_group):
                print("Fail: Check run_limit_test")
                return -1

            print("mon_group %s/%s rmid: %d" %
                 (ctrl_grp, mon_group, get_rmid_group(ctrl_grp, mon_group)))

    for i in range(1, partid):
        ctrl_grp = ("p%d" % i)

        for j in range(1, pmg):
            mon_group = ("m%d" % j)
            if mpam_lib.rmdir_ctrl_group(ctrl_grp, mon_group):
                return -1

        if mpam_lib.rmdir_ctrl_group(ctrl_grp, ""):
            return -1

    if size > 0:
        ret = write_threshold("L3", size)
        if ret:
            return -1

    print("Pass: Check run_limit_test")
    return 0
