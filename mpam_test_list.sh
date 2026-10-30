#!/bin/bash

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

commands=(
    "python3 mpam_main.py L3 cmt"
    "python3 mpam_main.py L3 cat"
    "python3 mpam_main.py L3 cmt cdp"
    "python3 mpam_main.py L3 cat cdp"
    "python3 mpam_main.py L3 max"
    "python3 mpam_main.py L3 min"
    "python3 mpam_main.py L3 prio"

    "python3 mpam_main.py MB mbm"
    "python3 mpam_main.py MB mba"
    "python3 mpam_main.py MB min"
    "python3 mpam_main.py MB prio"
    "python3 mpam_main.py MB hdl"

    "python3 mpam_main.py L2 mbm"
    "python3 mpam_main.py L2 cmt"
    "python3 mpam_main.py L2 cat"
    "python3 mpam_main.py L2 mbm cdp"
    "python3 mpam_main.py L2 cmt cdp"
    "python3 mpam_main.py L2 cat cdp"
    "python3 mpam_main.py L2 hotplug"

    "python3 mpam_main.py smmu mbm"
    "python3 mpam_main.py smmu mba"

    "python3 mpam_main.py limit"
    "python3 mpam_main.py MB precision"
    "python3 mpam_main.py L3 precision"
    "python3 mpam_main.py task"
    "python3 mpam_main.py cpu"
    "python3 mpam_main.py sub_mon"
)

array_length=${#commands[@]}

for ((i=0; i<array_length; i++)); do
    cmd=${commands[i]}
    echo "Executing [$((i+1))/$array_length]: $cmd"
    eval "$cmd"
    exit_code=$?

    if [ $exit_code -eq 0 ]; then
        echo "PASS [$((i+1))/$array_length]: $cmd"
    else
        echo "FAIL [$((i+1))/$array_length]: $cmd"
    fi
done

