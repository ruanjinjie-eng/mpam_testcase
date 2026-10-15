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

import os, sys, subprocess, time
import mpam_lib

def get_dev_buf_info(dev):
    command = "ethtool -i %s | grep bus-info" % dev
    process = subprocess.Popen(command, shell=True,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    if process.returncode != 0:
        print(stderr.decode())
        return -1

    output = stdout.decode().strip()
    if not output:
        return -1

    columns = output.split()
    if len(columns) != 2:
        return -1

    return columns[1]

def get_iommu_group(bus_info):
    command = "lspci -vvv -s %s | grep 'IOMMU group'" % bus_info
    process = subprocess.Popen(command, shell=True,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    if process.returncode != 0:
        print(stderr.decode())
        return -1

    output = stdout.decode().strip()
    if not output:
        return -1

    columns = output.split()
    if len(columns) != 3:
        return -1

    return int(columns[2])

def bind_iommu_to_group(id, ctrl_grp):
    command = "echo 'iommu_group:%d' > /sys/fs/resctrl/%s/tasks" % (id, ctrl_grp)

    result = subprocess.run(command, shell=True, text=True, capture_output=True)

    return result.returncode

def get_dev_ip(dev):
    command = "ifconfig %s | grep inet" % dev
    process = subprocess.Popen(command, shell=True,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    if process.returncode != 0:
        print(stderr.decode())
        return -1

    output = stdout.decode().strip()
    if not output:
        return -1

    return output.split()[1]

def get_dev_numa_id(bus_info):
    command = "lspci -vvv -s %s | grep 'NUMA node:'" % bus_info
    process = subprocess.Popen(command, shell=True,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    if process.returncode != 0:
        print(stderr.decode())
        return -1

    output = stdout.decode().strip()
    if not output:
        return -1

    columns = output.split()
    if len(columns) != 3:
        return -1

    return int(columns[2])

def start_benchmark(ip_addr, dev_ip_addr, remote_ip_addr):
    if os.system("which iperf3") == 1:
        return -1

    subprocess.Popen("iperf3 -s", shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)

    proc = subprocess.Popen("ssh %s iperf3 -c %s -t 10 -R" %
                            (remote_ip_addr, dev_ip_addr),
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)

    return proc

def end_benchmark(proc):
    proc.wait()
    if proc.returncode != 0:
        print(proc.stderr.decode())
        return -1

    return 0

def run_smmu_mon_test(dev, remote_ip):
    ctrl_grp = "p1"
    test_info = "Check SMMU monitoring test"

    bus_info = get_dev_buf_info(dev)
    if bus_info == -1:
        print("Fail to get device's bus information")
        return -1

    id = get_iommu_group(bus_info)
    if id < 0:
        print("Fail to get iommu group's ID belonging to")
        return -1

    if mpam_lib.mkdir_ctrl_group(ctrl_grp, ""):
        return -1

    ret = bind_iommu_to_group(id, ctrl_grp)
    if ret < 0:
        print("Fail to bind iommu group with control group")
        return -1

    dev_ip_addr = get_dev_ip(dev)
    if dev_ip_addr == -1:
        return -1

    numa_id = get_dev_numa_id(bus_info)
    if numa_id < 0:
        return -1

    proc = start_benchmark(dev, dev_ip_addr, remote_ip)
    if proc < 0:
        return -1

    time.sleep(5)

    val = mpam_lib.read_monitor_val(0, "MB", ctrl_grp, "mbm_total_bytes", numa_id)
    if val < 0:
        print("Fail to read device's bandwidth")
        return -1

    end_benchmark(proc)

    print("Pass: %s device %s" % (test_info, dev))
    return 0

def run_smmu_part_test(dev, remote_ip):
    ctrl_grp = "p1"
    resource = "MB"
    test_info = "Check SMMU partition test"

    bus_info = get_dev_buf_info(dev)
    if bus_info == -1:
        print("Fail to get device's bus information")
        return -1

    id = get_iommu_group(bus_info)
    if id < 0:
        print("Fail to get iommu group's ID belonging to")
        return -1

    if mpam_lib.mkdir_ctrl_group(ctrl_grp, ""):
        return -1

    ret = bind_iommu_to_group(id, ctrl_grp)
    if ret < 0:
        print("Fail to bind iommu group with control group")
        return -1

    dev_ip_addr = get_dev_ip(dev)
    if dev_ip_addr == -1:
        return -1

    numa_id = get_dev_numa_id(bus_info)
    if numa_id < 0:
        return -1

    proc = start_benchmark(dev, dev_ip_addr, remote_ip)
    if not proc:
        return -1

    time.sleep(5)

    ret = mpam_lib.write_schmata(ctrl_grp, resource, 0, 100, numa_id)
    if ret < 0:
        return -1

    val1 = mpam_lib.read_monitor_val(0, resource, ctrl_grp, "mbm_total_bytes", numa_id)
    if val1 < 0:
        print("Fail to read device bandwidth")
        return -1

    end_benchmark(proc)

    ret = mpam_lib.write_schmata(ctrl_grp, resource, 0, 1, numa_id)
    if ret < 0:
        return -1

    proc = start_benchmark(dev, dev_ip_addr, remote_ip)
    if not proc:
        return -1

    time.sleep(5)

    val2 = mpam_lib.read_monitor_val(0, resource, ctrl_grp, "mbm_total_bytes", numa_id)
    if val2 < 0:
        print("Fail to read device bandwidth")
        return -1

    end_benchmark(proc)

    if val1 < val2:
        print("Fail to partition IO device bandwidth")
        return -1

    print("Pass: %s device %s" % (test_info, dev))
    return 0
