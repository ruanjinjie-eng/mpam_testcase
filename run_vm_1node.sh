#!/bin/bash
# Boot the MPAM test VM in the FPGA-matching topology:
#   8 cores / 2 clusters / 1 L3 / **1 NUMA node** (FPGA: 8core 2cluster 1node)
#
# The 1-node part matters: the mainline arm_mpam driver refuses to export
# the MB resource when num_possible_nodes() > 1 (traffic_matches_l3()), so
# a 2-node VM can never run the MB-family tests (mpam mba/min/prio/hdl/
# precision/limit).
#
# Usage:
#   ./run_vm_1node.sh                      # default kernel below
#   KERNEL=/path/Image DISK=/path/rootfs.img ./run_vm_1node.sh
#
# EXTRA_ARGS is appended verbatim (add your disk/console/etc. here).
set -eu

MPAM_HOME="${MPAM_HOME:-/home/r00799764/community}"
QEMU_BIN="${QEMU_BIN:-$MPAM_HOME/qemu/build/qemu-system-aarch64}"
KERNEL="${KERNEL:-$MPAM_HOME/linux_old1/build/arm64/arch/arm64/boot/Image}"
MEM="${MEM:-4G}"
DIR="$MPAM_HOME/mpam_qemu_test_v2/logs"

[ -x "$QEMU_BIN" ] || { echo "QEMU not found: $QEMU_BIN" >&2; exit 1; }
[ -f "$KERNEL" ]   || { echo "Image not found: $KERNEL" >&2; exit 1; }
mkdir -p "$DIR"

# Fresh UEFI vars so each run starts from a clean machine state
cp /usr/share/qemu-efi-aarch64/QEMU_EFI.fd "$DIR/AAVMF_CODE_1node.fd"
cp /usr/share/AAVMF/AAVMF_VARS.fd "$DIR/AAVMF_VARS_1node.fd"
truncate -s 64M "$DIR/AAVMF_CODE_1node.fd" "$DIR/AAVMF_VARS_1node.fd"

# 1 socket x 2 clusters x 4 cores = 8 CPUs, all in NUMA node 0:
#   L2 MSC per cluster (2), L3 MSC per socket (1), mem MSC per node (1).
# shellcheck disable=SC2086
"$QEMU_BIN" \
    -M virt,mpam=on,gic-version=3 \
    -cpu max -m "$MEM" \
    -smp 8,sockets=1,clusters=2,cores=4,threads=1 \
    -numa node,memdev=m0,cpus=0-7 \
    -object memory-backend-ram,size="$MEM",id=m0 \
    -drive if=pflash,format=raw,unit=0,file="$DIR/AAVMF_CODE_1node.fd",readonly=on \
    -drive if=pflash,format=raw,unit=1,file="$DIR/AAVMF_VARS_1node.fd" \
    -kernel "$KERNEL" \
    ${EXTRA_ARGS:--nographic} \
    -preconfig \
    -qmp unix:"$DIR/one_node_qmp.sock",server,nowait &
QEMU_PID=$!

# -preconfig: publish the cache topology so PPTT carries L2=cluster /
# L3=socket cache nodes with the ids the MPAM ACPI table points at.
python3 - "$DIR/one_node_qmp.sock" <<'EOF'
import json, socket, sys, time

sock = sys.argv[1]
for _ in range(60):
    try:
        q = socket.socket(socket.AF_UNIX)
        q.connect(sock)
        break
    except OSError:
        time.sleep(0.5)
else:
    sys.exit("qmp socket never appeared")

f = q.makefile("rwb")

def send(obj):
    f.write(json.dumps(obj).encode() + b"\n"); f.flush()

def recv():
    while True:
        line = f.readline()
        if not line:
            raise RuntimeError("qmp eof")
        obj = json.loads(line)
        if "event" not in obj:
            return obj

recv()
send({"execute": "qmp_capabilities"})
recv()
send({"execute": "qom-set", "arguments": {
    "path": "/machine", "property": "smp-cache",
    "value": [
        {"cache": "l1d", "topology": "core"},
        {"cache": "l1i", "topology": "core"},
        {"cache": "l2", "topology": "cluster"},
        {"cache": "l3", "topology": "socket"},
    ]}})
print("smp-cache qom-set:", recv())
send({"execute": "x-exit-preconfig"})
EOF

wait $QEMU_PID
