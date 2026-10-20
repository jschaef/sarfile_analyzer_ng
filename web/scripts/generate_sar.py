#!/usr/bin/env python3
"""Generate a synthetic `sar -A` text report for tests and benchmarks.

The output is NOT real data. It only mimics the classic sysstat text layout
closely enough that code/parse_into_polars.parse_sar_file (and therefore the
FastAPI upload in api/) accepts it:

- first line: "Linux <release> (<host>) <YYYY-MM-DD> _<arch>_ (<n> CPU)"
- one block per activity, introduced by an empty line and a header line that
  starts with a HH:MM:SS timestamp
- multi-device activities (CPU, DEV, IFACE) repeat the header per interval,
  single-row activities print the header once, like real sar does
- "Average:" lines, which the parser skips

Values are deterministic (seeded) and shaped like a day of load (sine wave plus
noise), so charts look plausible. Only the Python standard library is used.

Examples:
    # small fixture used by the e2e test (checked in)
    python3 web/scripts/generate_sar.py --cpus 4 --samples 96 \
        --interval 900 --restart -o web/e2e/fixtures/sar_small.txt

    # large fixture for web/PERF.md (~1M rows in the CPU section, NOT checked in)
    python3 web/scripts/generate_sar.py --cpus 352 --samples 2833 \
        --interval 30 --minimal -o /tmp/sar_large.txt
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import random
import sys
from typing import Callable, TextIO

CPU_COLUMNS = [
    "%usr", "%nice", "%sys", "%iowait", "%steal",
    "%irq", "%soft", "%guest", "%gnice", "%idle",
]


class Generator:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.rng = random.Random(args.seed)
        start = dt.datetime.combine(args.date, dt.time(0, 0, 0))
        self.times = [
            start + dt.timedelta(seconds=args.interval * i)
            for i in range(args.samples)
        ]
        # Times must stay on the same day - the parser glues HH:MM:SS onto
        # the single date from the first line.
        if self.times[-1].date() != args.date:
            sys.exit("samples * interval must stay within one day (< 86400s)")

    # -- helpers -----------------------------------------------------------
    def load(self, index: int, phase: float = 0.0) -> float:
        """Daily load curve in [0, 1]: quiet at night, peak in the afternoon."""
        day_fraction = self.times[index].hour / 24 + self.times[index].minute / 1440
        base = 0.5 - 0.5 * math.cos(2 * math.pi * (day_fraction - 0.1 + phase))
        return min(1.0, max(0.0, base + self.rng.uniform(-0.08, 0.08)))

    @staticmethod
    def stamp(moment: dt.datetime) -> str:
        return moment.strftime("%H:%M:%S")

    @staticmethod
    def row(stamp: str, values: list[str], width: int = 10) -> str:
        return stamp + "".join(v.rjust(width) for v in values)

    @staticmethod
    def f2(value: float) -> str:
        return f"{value:.2f}"

    # -- sections ----------------------------------------------------------
    def cpu_values(self, index: int, cpu: int | None) -> list[float]:
        level = self.load(index, phase=0.0 if cpu is None else (cpu % 7) / 50)
        usr = 60 * level + self.rng.uniform(0, 4)
        sys_ = 15 * level + self.rng.uniform(0, 2)
        iowait = 5 * level * self.rng.random()
        soft = 1.5 * level
        irq = 0.3 * level
        nice = 0.0
        steal = 0.0
        guest = 0.0
        gnice = 0.0
        idle = max(0.0, 100 - (usr + sys_ + iowait + soft + irq))
        return [usr, nice, sys_, iowait, steal, irq, soft, guest, gnice, idle]

    def write_cpu(self, out: TextIO) -> None:
        devices: list[int | None] = [None, *range(self.args.cpus)]
        averages = {d: [0.0] * len(CPU_COLUMNS) for d in devices}
        for index, moment in enumerate(self.times):
            stamp = self.stamp(moment)
            out.write("\n")
            out.write(self.row(stamp, ["CPU", *CPU_COLUMNS]) + "\n")
            lines = []
            for device in devices:
                values = self.cpu_values(index, device)
                acc = averages[device]
                for i, value in enumerate(values):
                    acc[i] += value
                name = "all" if device is None else str(device)
                lines.append(self.row(stamp, [name, *map(self.f2, values)]))
            out.write("\n".join(lines) + "\n")
        out.write("\n")
        out.write(self.row("Average:", ["CPU", *CPU_COLUMNS]) + "\n")
        for device, acc in averages.items():
            name = "all" if device is None else str(device)
            out.write(self.row("Average:", [name, *(self.f2(v / len(self.times)) for v in acc)]) + "\n")

    def write_single(
        self, out: TextIO, columns: list[str], values: Callable[[int], list[str]]
    ) -> None:
        """One header, one row per interval (load, memory, swap, ...)."""
        header_stamp = self.stamp(self.times[0])
        out.write("\n")
        out.write(self.row(header_stamp, columns) + "\n")
        last: list[str] = []
        for index, moment in enumerate(self.times):
            last = values(index)
            out.write(self.row(self.stamp(moment), last) + "\n")
        out.write(self.row("Average:", last) + "\n")

    def write_multi(
        self,
        out: TextIO,
        key: str,
        devices: list[str],
        columns: list[str],
        values: Callable[[int, str], list[str]],
    ) -> None:
        """Header repeated per interval, one row per device (DEV, IFACE)."""
        for index, moment in enumerate(self.times):
            stamp = self.stamp(moment)
            out.write("\n")
            out.write(self.row(stamp, [key, *columns]) + "\n")
            for device in devices:
                out.write(self.row(stamp, [device, *values(index, device)]) + "\n")

    def run(self, out: TextIO) -> None:
        a = self.args
        out.write(
            f"Linux {a.release} ({a.host}) \t{a.date.isoformat()} \t_x86_64_\t({a.cpus} CPU)\n"
        )
        self.write_cpu(out)

        mem_total = a.mem_gb * 1024 * 1024
        swap_total = 8 * 1024 * 1024
        f2 = self.f2

        if not a.minimal:
            self.write_single(
                out, ["proc/s", "cswch/s"],
                lambda i: [f2(20 + 80 * self.load(i)), f2(2000 + 30000 * self.load(i))],
            )
            self.write_single(
                out,
                ["pgpgin/s", "pgpgout/s", "fault/s", "majflt/s", "pgfree/s",
                 "pgscank/s", "pgscand/s", "pgsteal/s", "%vmeff"],
                lambda i: [f2(500 * self.load(i)), f2(900 * self.load(i)),
                           f2(4000 * self.load(i)), f2(2 * self.load(i)),
                           f2(6000 * self.load(i)), "0.00", "0.00", "0.00", "0.00"],
            )
            self.write_single(
                out, ["tps", "rtps", "wtps", "bread/s", "bwrtn/s"],
                lambda i: [f2(150 * self.load(i)), f2(50 * self.load(i)),
                           f2(100 * self.load(i)), f2(900 * self.load(i)),
                           f2(1800 * self.load(i))],
            )

        def memory(i: int) -> list[str]:
            used = mem_total * (0.35 + 0.45 * self.load(i, 0.05))
            free = mem_total - used
            cached = mem_total * 0.2
            return [
                str(int(free)), str(int(free + cached)), str(int(used)),
                f2(100 * used / mem_total), str(int(mem_total * 0.01)),
                str(int(cached)), str(int(used * 1.3)),
                f2(130 * used / mem_total), str(int(used * 0.6)),
                str(int(used * 0.3)), str(int(400 + 4000 * self.load(i))),
                str(int(used * 0.4)), str(int(mem_total * 0.02)), "18000",
                "42000", "0",
            ]

        self.write_single(
            out,
            ["kbmemfree", "kbavail", "kbmemused", "%memused", "kbbuffers",
             "kbcached", "kbcommit", "%commit", "kbactive", "kbinact", "kbdirty",
             "kbanonpg", "kbslab", "kbkstack", "kbpgtbl", "kbvmused"],
            memory,
        )

        def swap(i: int) -> list[str]:
            used = swap_total * 0.05 * self.load(i, 0.2)
            return [str(int(swap_total - used)), str(int(used)),
                    f2(100 * used / swap_total), str(int(used * 0.1)),
                    f2(10 * used / max(used, 1))]

        self.write_single(
            out, ["kbswpfree", "kbswpused", "%swpused", "kbswpcad", "%swpcad"], swap
        )
        self.write_single(
            out, ["dentunusd", "file-nr", "inode-nr", "pty-nr"],
            lambda i: [str(int(90000 + 30000 * self.load(i))),
                       str(int(3000 + 5000 * self.load(i))),
                       str(int(70000 + 20000 * self.load(i))), "4"],
        )
        self.write_single(
            out, ["runq-sz", "plist-sz", "ldavg-1", "ldavg-5", "ldavg-15", "blocked"],
            lambda i: [str(int(a.cpus * self.load(i))), str(int(900 + 400 * self.load(i))),
                       f2(a.cpus * 0.8 * self.load(i)), f2(a.cpus * 0.75 * self.load(i, -0.01)),
                       f2(a.cpus * 0.7 * self.load(i, -0.02)), str(int(2 * self.load(i)))],
        )

        if not a.minimal:
            self.write_multi(
                out, "DEV", ["sda", "nvme0n1"],
                ["tps", "rkB/s", "wkB/s", "areq-sz", "aqu-sz", "await", "svctm", "%util"],
                lambda i, d: [f2(120 * self.load(i)), f2(800 * self.load(i)),
                              f2(1600 * self.load(i)), f2(24.0), f2(0.4 * self.load(i)),
                              f2(1.2 + self.load(i)), "0.00", f2(30 * self.load(i))],
            )
            self.write_multi(
                out, "IFACE", ["lo", "eth0"],
                ["rxpck/s", "txpck/s", "rxkB/s", "txkB/s", "rxcmp/s", "txcmp/s",
                 "rxmcst/s", "%ifutil"],
                lambda i, d: [f2(900 * self.load(i)), f2(700 * self.load(i)),
                              f2(400 * self.load(i)), f2(300 * self.load(i)),
                              "0.00", "0.00", "0.00", f2(3 * self.load(i))],
            )

        if a.restart:
            # one reboot in the middle of the day, like a real "LINUX RESTART" line
            moment = self.times[len(self.times) // 2]
            out.write("\n")
            out.write(f"{self.stamp(moment)}       LINUX RESTART\t({a.cpus} CPU)\n")
        out.write("\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-o", "--output", default="-", help="output file, '-' for stdout")
    parser.add_argument("--cpus", type=int, default=4)
    parser.add_argument("--samples", type=int, default=96, help="intervals per day")
    parser.add_argument("--interval", type=int, default=900, help="seconds between samples")
    parser.add_argument("--date", type=dt.date.fromisoformat, default=dt.date(2026, 10, 1))
    parser.add_argument("--host", default="synthetic-host")
    parser.add_argument("--release", default="6.4.0-150600.23.25-default")
    parser.add_argument("--mem-gb", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--restart", action="store_true", help="add one LINUX RESTART line")
    parser.add_argument(
        "--minimal", action="store_true",
        help="only the Overview default sections (CPU, memory, swap, kernel tables, load)",
    )
    args = parser.parse_args(argv)

    generator = Generator(args)
    if args.output == "-":
        generator.run(sys.stdout)
    else:
        with open(args.output, "w", encoding="ascii") as handle:
            generator.run(handle)


if __name__ == "__main__":
    main()
