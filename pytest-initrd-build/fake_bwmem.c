/* Minimal stand-in for lmbench bw_mem for resctrl test runs under QEMU.
 *
 * QEMU's MPAM MSC model derives monitor counters from the configured
 * partition, not from real traffic, so the benchmark only needs to keep
 * the test group's task alive and reading memory while the MBWU monitor
 * accumulates.  This reads a working set in a loop for the requested
 * number of iterations.
 *
 * Supports just the flags the test suite passes:
 *   bw_mem -P NPROCS -N TIMES SIZE OP        (numactl form)
 *   bw_mem -P NPROCS -N TIMES SIZE OP        (taskset form, cpuno unused)
 * OP is "rd"; SIZE like "64M" or "256M".
 *
 * Output to stderr: "<pool_MB> <bandwidth_MB/s>" matching the format
 * mpam_lib.end_benchmark() parses.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static double parse_size(const char *s)
{
    char *end;
    double v = strtod(s, &end);
    if (*end == 'K' || *end == 'k') v /= 1024.0;
    else if (*end == 'G' || *end == 'g') v *= 1024.0;
    return v;
}

int main(int argc, char **argv)
{
    int procs = 1, times = 1;
    double size_mb = 64.0;
    const char *op = "rd";

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-P") == 0 && i + 1 < argc)
            procs = atoi(argv[++i]);
        else if (strcmp(argv[i], "-N") == 0 && i + 1 < argc)
            times = atoi(argv[++i]);
        else if (argv[i][0] >= '0' && argv[i][0] <= '9') {
            /* SIZE then OP */
            size_mb = parse_size(argv[i]);
            if (i + 1 < argc) op = argv[++i];
        }
    }

    size_t bytes = (size_t)(size_mb * 1024 * 1024);
    if (bytes < 4096) bytes = 4096;
    char *buf = malloc(bytes);
    if (!buf) return 1;
    memset(buf, 0, bytes);

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    volatile char sink = 0;
    for (int t = 0; t < times; t++) {
        for (size_t j = 0; j < bytes; j += 64)
            sink ^= buf[j];
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double secs = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) / 1e9;
    if (secs < 1e-9) secs = 1e-9;
    double total_mb = size_mb * times;
    double bw = total_mb / secs;

    fprintf(stderr, "%.3f %.3f\n", total_mb, bw);
    free(buf);
    return 0;
}
