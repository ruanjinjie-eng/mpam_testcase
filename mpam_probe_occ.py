#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
#
# Diagnostic: report the CSU occupancy values the model returns, so a test
# run can tell whether a QEMU property (e.g. csu-capacity-bytes) applied.

import sys

import mpam_suite_lib as L
from mpam_suite_lib import errname


def main():
    s = L.Suite("CSU occupancy probe")
    rc = L.mount("debug", s)
    print("PROBE mount=%s" % errname(rc))
    print("PROBE root llc=%s" % L.mon_read("", "llc_occupancy"))
    print("PROBE mkdir=%s" % errname(L.try_mkdir(L.R + "/g")))
    print("PROBE mkmon=%s" % L.mkmon("g", "m"))
    print("PROBE mon llc=%s" % L.mon_read("g/mon_groups/m", "llc_occupancy"))
    print("PROBE size=%s" % L.read(L.INFO + "/L3_MON/size"))
    print("PROBE threshold=%s" %
          L.read(L.INFO + "/L3_MON/max_threshold_occupancy"))
    L.umount(suite=s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
