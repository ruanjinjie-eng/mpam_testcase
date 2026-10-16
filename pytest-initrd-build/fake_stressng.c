/* Minimal stand-in for stress-ng --cache for resctrl test runs under QEMU.
 *
 * QEMU's MPAM MSC model derives monitor counters from the configured
 * partition (CSU = capacity x CPBM fraction, MBWU = nominal_bw x time),
 * so the benchmark only needs to keep the test group's task alive while
 * the monitor accumulates.  This program spins on a cache-sized buffer
 * for the requested duration so the flow matches the real tool.
 *
 * Supports just the flags the test suite passes:
 *   stress-ng --cache N --aggressive -t TIMEs
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    int cache_workers = 1;
    double secs = 20.0;
    volatile char sink = 0;
    char *buf;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--cache") == 0 && i + 1 < argc)
            cache_workers = atoi(argv[++i]);
        else if (strcmp(argv[i], "-t") == 0 && i + 1 < argc) {
            char *end;
            secs = strtod(argv[++i], &end);
            if (end[0] == 's' || end[0] == 'S')
                secs = strtod(argv[i], &end);
        }
        /* --aggressive and others: ignored */
    }

    buf = malloc(256 * 1024);  /* one L2 way-set worth */
    if (!buf)
        return 1;
    memset(buf, 0x55, 256 * 1024);

    struct timespec start, now;
    clock_gettime(CLOCK_MONOTONIC, &start);
    do {
        for (int j = 0; j < 256 * 1024; j += 64)
            sink ^= buf[j];
        clock_gettime(CLOCK_MONOTONIC, &now);
    } while ((now.tv_sec - start.tv_sec) +
             (now.tv_nsec - start.tv_nsec) / 1e9 < secs);

    free(buf);
    return 0;
}
