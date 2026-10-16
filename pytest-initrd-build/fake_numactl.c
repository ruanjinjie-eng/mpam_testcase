/* Minimal numactl stand-in for single-NUMA-node resctrl test VMs.
 *
 * On a 1-NUMA-node guest the NUMA memory binding (-N/-m) is a no-op,
 * and only the CPU affinity (-C) matters, which maps to taskset -c.
 * This forwards -C <cpulist> to busybox taskset and runs the rest
 * of the command line directly.
 *
 * Supported forms the test suite uses:
 *   numactl -C <cpulist>  <cmd...>   -> taskset -c <cpulist> <cmd...>
 *   numactl -N <node>     <cmd...>   -> <cmd...>
 *   numactl -C <cpu> -m <node> <cmd> -> taskset -c <cpu> <cmd...>
 */
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    char *cpu_list = NULL;
    int i = 1;

    while (i < argc && argv[i][0] == '-') {
        if (strcmp(argv[i], "-C") == 0 && i + 1 < argc) {
            cpu_list = argv[++i];
            i++;
        } else if (strcmp(argv[i], "-N") == 0 && i + 2 < argc) {
            i += 2;  /* skip -N <node> */
        } else if (strcmp(argv[i], "-m") == 0 && i + 1 < argc) {
            i++; i++;  /* skip -m <node> */
        } else {
            i++;
        }
    }

    if (i >= argc) {
        fprintf(stderr, "numactl: no command given\n");
        return 1;
    }

    if (cpu_list) {
        /* Forward to busybox taskset: taskset -c <list> <cmd...> */
        char *newargv[argc - i + 3];
        int j = 0;
        newargv[j++] = "taskset";
        newargv[j++] = "-c";
        newargv[j++] = cpu_list;
        for (; i < argc; i++)
            newargv[j++] = argv[i];
        newargv[j] = NULL;
        execvp("taskset", newargv);
        perror("execvp taskset");
        return 127;
    }

    /* No CPU pinning: run directly */
    execvp(argv[i], &argv[i]);
    perror("execvp");
    return 127;
}
