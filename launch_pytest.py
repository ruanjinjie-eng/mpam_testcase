import json, os, shutil, socket, subprocess, sys, time

HOME = "/home/r00799764/community"
DIR = HOME + "/mpam_qemu_test_v2/logs"
# Overridable so this script can target another kernel/tree or run a probe
# initrd without sharing the default log/socket paths with other sessions.
TAG = os.environ.get("MPAM_TAG", "pytest")
QEMU = os.environ.get("MPAM_QEMU",
                     HOME + "/qemu_boot_verify/build/qemu-system-aarch64")  # NOT community/qemu (other session refactors it)
KERNEL = os.environ.get("MPAM_KERNEL",
                        HOME + "/linux_old1/build/arm64/arch/arm64/boot/Image")
INITRD = os.environ.get("MPAM_INITRD",
                        HOME + "/mpam_qemu_test_v2/initrd/pytest-initrd.gz")
APPEND = os.environ.get("MPAM_APPEND",
                        "console=ttyAMA0 earlycon=pl011,0x09000000 rdinit=/init")
TIMEOUT = int(os.environ.get("MPAM_TIMEOUT", "2400"))
SMP = os.environ.get("MPAM_SMP",
                     "8,sockets=1,clusters=2,cores=4,threads=1")
SMP_CACHE = json.loads(os.environ.get(
    "MPAM_SMP_CACHE",
    '[{"cache":"l1d","topology":"core"},{"cache":"l1i","topology":"core"},'
    '{"cache":"l2","topology":"cluster"},{"cache":"l3","topology":"socket"}]'))
NR_CPUS = int(SMP.split(",")[0])
NUMA_CPUS = "0-%d" % (NR_CPUS - 1)
CODE = DIR + "/AAVMF_CODE_%s.fd" % TAG
VARS = DIR + "/AAVMF_VARS_%s.fd" % TAG
QMP = DIR + "/%s_qmp.sock" % TAG
LOG = DIR + "/%s_run.log" % TAG

# Ensure the UEFI flash images exist, 64MiB-padded as virt flash0/1 require.
os.makedirs(DIR, exist_ok=True)
for path, src in ((CODE, "/usr/share/qemu-efi-aarch64/QEMU_EFI.fd"),
                  (VARS, "/usr/share/AAVMF/AAVMF_VARS.fd")):
    if not os.path.exists(path) or os.path.getsize(path) != 64 * 1024 * 1024:
        shutil.copy(src, path)
        with open(path, "r+b") as f:
            f.truncate(64 * 1024 * 1024)

for f in (QMP,):
    if os.path.exists(f): os.unlink(f)

MACHINE = "virt,mpam=on,gic-version=3"
MACHINE_EXTRA = os.environ.get("MPAM_MACHINE_EXTRA")
if MACHINE_EXTRA:
    MACHINE += "," + MACHINE_EXTRA

args = [
    QEMU, "-M", MACHINE,
    "-cpu", "max", "-m", "4G",
    "-smp", SMP,
    "-numa", "node,memdev=m0,cpus=%s" % NUMA_CPUS,
    "-object", "memory-backend-ram,size=4G,id=m0",
    "-drive", f"if=pflash,format=raw,unit=0,file={CODE},readonly=on",
    "-drive", f"if=pflash,format=raw,unit=1,file={VARS}",
    "-kernel", KERNEL, "-initrd", INITRD,
    "-append", APPEND,
    "-nographic", "-no-reboot", "-preconfig",
    "-qmp", f"unix:{QMP},server,nowait",
]
# Optional host share, used to copy gcov data out of the guest.
VIRTFS = os.environ.get("MPAM_VIRTFS")
if VIRTFS:
    args += ["-virtfs",
             "local,path=%s,mount_tag=gcov,security_model=none,"
             "multidevs=remap" % VIRTFS]
EXTRA = os.environ.get("MPAM_QEMU_EXTRA")
if EXTRA:
    args += EXTRA.split()
print(f"launching QEMU, log={LOG}", flush=True)
logf = open(LOG, "wb")
proc = subprocess.Popen(args, stdout=logf, stderr=subprocess.STDOUT)

# wait for qmp socket
for _ in range(60):
    try:
        q = socket.socket(socket.AF_UNIX); q.connect(QMP); break
    except OSError:
        time.sleep(0.5)
else:
    print("qmp socket never appeared", flush=True); sys.exit(2)

f = q.makefile("rwb")
def send(o): f.write(json.dumps(o).encode()+b"\n"); f.flush()
def recv():
    while True:
        line = f.readline()
        if not line: raise RuntimeError("qmp eof")
        o = json.loads(line)
        if "event" not in o: return o

recv(); send({"execute":"qmp_capabilities"}); recv()
send({"execute":"qom-set","arguments":{"path":"/machine","property":"smp-cache",
                                       "value":SMP_CACHE}})
print("smp-cache:", recv(), flush=True)
send({"execute":"x-exit-preconfig"})
try: recv()
except: pass

# Wait for suite to finish (poweroff) or timeout
DONE = os.environ.get("MPAM_DONE", "SUITE DONE").encode()
deadline = time.time() + TIMEOUT
while time.time() < deadline:
    if proc.poll() is not None:
        break
    time.sleep(10)
    try:
        with open(LOG,"rb") as lf:
            data = lf.read()
        if DONE in data:
            time.sleep(5)
            break
    except: pass

if proc.poll() is None:
    print("timeout, killing", flush=True)
    proc.terminate()
    try: proc.wait(timeout=10)
    except: proc.kill()
proc.wait()
print("QEMU exited", proc.returncode, flush=True)
