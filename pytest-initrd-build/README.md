# python3 test initrd — build inputs and steps

The QEMU verification VM needs python3 plus the benchmarks the suite
invokes, inside a minimal initramfs. This directory holds the guest
`init` script and the small static stand-ins; the built initramfs lives
at `../../mpam_qemu_test_v2/initrd/pytest-initrd.gz`.

## Files

| File | Purpose |
|---|---|
| `init` | Guest init: mounts resctrl, prints a resource probe, drives the 22-item suite (list is inlined because busybox sh has no arrays), powers off. |
| `fake_stressng.c` | Not used for builds — the real stress-ng is cross-compiled (see below). Kept for reference. |
| `fake_bwmem.c` | `bw_mem` stand-in: lmbench is not packaged for arm64. Reads the working set for the requested iterations and prints `"<pool MB> <bw MB/s>"` to stderr, matching what `mpam_lib.end_benchmark()` parses. |
| `fake_numactl.c` | numactl shim for single-node VMs: `-C <list>` forwards to busybox `taskset -c`; `-N <node>` / `-m <node>` are no-ops. |

## Build

```sh
# 1. arm64 runtime packages (ports source enabled for arm64)
apt-get download -o APT::Architecture=arm64 \
    python3-minimal libpython3.12-minimal libpython3-stdlib \
    python3.12-minimal libpython3.12-stdlib libc6 zlib1g libffi8 \
    libexpat1 liblzma5 libbz2-1.0 libsqlite3-0 numactl stress-ng
mkdir -p rootfs && for d in *.deb; do dpkg-deb -x "$d" rootfs/; done

# 2. busybox + applet symlinks (the mpam_qemu_test rootfs has it)
cp <path>/initrd/rootfs/bin/busybox rootfs/bin/
ln -sf /usr/lib/ld-linux-aarch64.so.1 rootfs/lib/ld-linux-aarch64.so.1
(cd rootfs && bin/busybox --list | while read c; do
    [ -e "bin/$c" ] || ln -s busybox "bin/$c"; done)

# 3. static stress-ng (config-derived counters make the --cache stressor
#    the only part that matters; STATIC=1 avoids all shared-lib deps)
git clone --depth 1 https://github.com/ColinIanKing/stress-ng.git
make -C stress-ng -j"$(nproc)" CC=aarch64-linux-gnu-gcc STATIC=1
cp stress-ng/stress-ng rootfs/usr/bin/

# 4. the two shims
aarch64-linux-gnu-gcc -static -O2 -o rootfs/usr/bin/bw_mem   fake_bwmem.c
aarch64-linux-gnu-gcc -static -O2 -o rootfs/usr/bin/numactl  fake_numactl.c

# 5. the suite itself + this init
cp ../*.py ../mpam_test_list.sh rootfs/mpam/
cp init rootfs/init && chmod +x rootfs/init

# 6. pack
(cd rootfs && find . | cpio -o -H newc --quiet) | gzip -9 > ../pytest-initrd.gz
```

## Run

`../launch_pytest.py` boots the VM with this initrd against
`qemu_boot_verify` (not `community/qemu` — that tree is being refactored
elsewhere), waits for `# SUITE DONE`, and leaves the console log at
`../../mpam_qemu_test_v2/logs/pytest_run.log`.
