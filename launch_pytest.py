import json, os, shutil, socket, subprocess, sys, time

HOME = "/home/r00799764/community"
DIR = HOME + "/mpam_qemu_test_v2/logs"
QEMU = HOME + "/qemu_boot_verify/build/qemu-system-aarch64"  # NOT community/qemu (other session refactors it)
KERNEL = HOME + "/linux_old1/build/arm64/arch/arm64/boot/Image"
INITRD = HOME + "/mpam_qemu_test_v2/initrd/pytest-initrd.gz"
CODE = DIR + "/AAVMF_CODE_pytest.fd"
VARS = DIR + "/AAVMF_VARS_pytest.fd"
QMP = DIR + "/pytest_qmp.sock"
LOG = DIR + "/pytest_run.log"

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

args = [
    QEMU, "-M", "virt,mpam=on,gic-version=3",
    "-cpu", "max", "-m", "4G",
    "-smp", "8,sockets=1,clusters=2,cores=4,threads=1",
    "-numa", "node,memdev=m0,cpus=0-7",
    "-object", "memory-backend-ram,size=4G,id=m0",
    "-drive", f"if=pflash,format=raw,unit=0,file={CODE},readonly=on",
    "-drive", f"if=pflash,format=raw,unit=1,file={VARS}",
    "-kernel", KERNEL, "-initrd", INITRD,
    "-append", "console=ttyAMA0 earlycon=pl011,0x09000000 rdinit=/init",
    "-nographic", "-no-reboot", "-preconfig",
    "-qmp", f"unix:{QMP},server,nowait",
]
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
send({"execute":"qom-set","arguments":{"path":"/machine","property":"smp-cache","value":[
    {"cache":"l1d","topology":"core"},{"cache":"l1i","topology":"core"},
    {"cache":"l2","topology":"cluster"},{"cache":"l3","topology":"socket"},
]}})
print("smp-cache:", recv(), flush=True)
send({"execute":"x-exit-preconfig"})
try: recv()
except: pass

# Wait for suite to finish (poweroff) or timeout
deadline = time.time() + 2400
while time.time() < deadline:
    if proc.poll() is not None:
        break
    time.sleep(10)
    try:
        with open(LOG,"rb") as lf:
            data = lf.read()
        if b"SUITE DONE" in data:
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
