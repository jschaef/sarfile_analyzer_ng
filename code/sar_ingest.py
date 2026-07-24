"""Shared upload preprocessing: xz decompression and sadf-JSON conversion.

Used by both the REST API (api/services.py) and the Streamlit UI (mng_sar.py).
The sadf JSON is rendered back into the classic ``sar -A`` text layout so that
parse_into_polars.parse_sar_file stays the single parsing authority - headers,
metrics and devices come out identical to a text upload by construction.

Recommended export on the source host::

    sadf -j <sa-file> -- -A > report.json

``-- -A`` passes the "all activities" flag through to sar - a plain
``sadf -j`` only exports CPU utilisation, which is the usual reason a report
shows nothing but one CPU section.

Timestamps are used exactly as they appear in the JSON. sadf writes UTC unless
``-t`` is given, which is what you want for hosts running in UTC. Add ``-t``
only when the source host uses a local timezone and that wall-clock time is
what should show up on the axis.

Sections the text parser ignores anyway (interrupts, CPU MHz) are skipped.
Unknown sections/fields are skipped with a warning instead of failing.
"""

import json
import lzma
import os

XZ_MAGIC = b"\xfd7zXZ\x00"
MAX_DECOMPRESSED_BYTES = int(
    os.getenv("SAR_MAX_DECOMPRESSED_BYTES", 512 * 1024 * 1024)
)

# Sections that parse_into_polars drops anyway (reg_ignore / df_clean_data)
_SKIPPED_SECTIONS = {"interrupts", "power-management"}

# Ordered (json_field, sar_column) pairs per section. Only fields present in
# the JSON are emitted (in this order), so short formats (plain ``sadf -j``)
# and full ones (``sadf -j -- -A``) both work.
# 'device': (json_field, sar_header_column); FILESYSTEM is special-cased
# because sar prints the device column LAST for it.
_SECTIONS = {
    "cpu-load": {
        "device": ("cpu", "CPU"),
        "fields": [
            ("usr", "%usr"), ("user", "%user"), ("nice", "%nice"),
            ("sys", "%sys"), ("system", "%system"), ("iowait", "%iowait"),
            ("steal", "%steal"), ("irq", "%irq"), ("soft", "%soft"),
            ("guest", "%guest"), ("gnice", "%gnice"), ("idle", "%idle"),
        ],
    },
    "process-and-context-switch": {
        "fields": [("proc", "proc/s"), ("cswch", "cswch/s")],
    },
    "swap-pages": {
        "fields": [("pswpin", "pswpin/s"), ("pswpout", "pswpout/s")],
    },
    "paging": {
        "fields": [
            ("pgpgin", "pgpgin/s"), ("pgpgout", "pgpgout/s"),
            ("fault", "fault/s"), ("majflt", "majflt/s"),
            ("pgfree", "pgfree/s"), ("pgscank", "pgscank/s"),
            ("pgscand", "pgscand/s"), ("pgsteal", "pgsteal/s"),
            ("vmeff-percent", "%vmeff"),
        ],
    },
    "io": {
        "flatten": ["io-reads", "io-writes"],
        "fields": [
            ("tps", "tps"), ("rtps", "rtps"), ("wtps", "wtps"),
            ("bread", "bread/s"), ("bwrtn", "bwrtn/s"),
        ],
    },
    # one JSON dict feeds two text sections (memory + swap utilization)
    "memory": {
        "fields": [
            ("memfree", "kbmemfree"), ("avail", "kbavail"),
            ("memused", "kbmemused"), ("memused-percent", "%memused"),
            ("buffers", "kbbuffers"), ("cached", "kbcached"),
            ("commit", "kbcommit"), ("commit-percent", "%commit"),
            ("active", "kbactive"), ("inactive", "kbinact"),
            ("dirty", "kbdirty"), ("anonpg", "kbanonpg"),
            ("slab", "kbslab"), ("kstack", "kbkstack"),
            ("pgtbl", "kbpgtbl"), ("vmused", "kbvmused"),
        ],
    },
    "memory-swap": {
        "source": "memory",
        "fields": [
            ("swpfree", "kbswpfree"), ("swpused", "kbswpused"),
            ("swpused-percent", "%swpused"), ("swpcad", "kbswpcad"),
            ("swpcad-percent", "%swpcad"),
        ],
    },
    "hugepages": {
        "fields": [
            ("hugfree", "kbhugfree"), ("hugused", "kbhugused"),
            ("hugused-percent", "%hugused"),
        ],
    },
    "kernel": {
        "fields": [
            ("dentunusd", "dentunusd"), ("file-nr", "file-nr"),
            ("inode-nr", "inode-nr"), ("pty-nr", "pty-nr"),
        ],
    },
    "queue": {
        "fields": [
            ("runq-sz", "runq-sz"), ("plist-sz", "plist-sz"),
            ("ldavg-1", "ldavg-1"), ("ldavg-5", "ldavg-5"),
            ("ldavg-15", "ldavg-15"), ("blocked", "blocked"),
        ],
    },
    "disk": {
        "device": ("disk-device", "DEV"),
        "fields": [
            ("tps", "tps"), ("rkB", "rkB/s"), ("wkB", "wkB/s"),
            ("areq-sz", "areq-sz"), ("aqu-sz", "aqu-sz"),
            ("await", "await"), ("svctm", "svctm"),
            ("util-percent", "%util"),
        ],
    },
    "serial": {
        "device": ("line", "TTY"),
        "fields": [
            ("rcvin", "rcvin/s"), ("xmtin", "xmtin/s"),
            ("framerr", "framerr/s"), ("prtyerr", "prtyerr/s"),
            ("brk", "brk/s"), ("ovrun", "ovrun/s"),
        ],
    },
    "filesystems": {
        "device_last": ("filesystem", "FILESYSTEM"),
        "fields": [
            ("MBfsfree", "MBfsfree"), ("MBfsused", "MBfsused"),
            ("%fsused", "%fsused"), ("%ufsused", "%ufsused"),
            ("Ifree", "Ifree"), ("Iused", "Iused"), ("%Iused", "%Iused"),
        ],
    },
}

_NETWORK_SECTIONS = {
    "net-dev": {
        "device": ("iface", "IFACE"),
        "fields": [
            ("rxpck", "rxpck/s"), ("txpck", "txpck/s"), ("rxkB", "rxkB/s"),
            ("txkB", "txkB/s"), ("rxcmp", "rxcmp/s"), ("txcmp", "txcmp/s"),
            ("rxmcst", "rxmcst/s"), ("ifutil-percent", "%ifutil"),
        ],
    },
    "net-edev": {
        "device": ("iface", "IFACE"),
        "fields": [
            ("rxerr", "rxerr/s"), ("txerr", "txerr/s"), ("coll", "coll/s"),
            ("rxdrop", "rxdrop/s"), ("txdrop", "txdrop/s"),
            ("txcarr", "txcarr/s"), ("rxfram", "rxfram/s"),
            ("rxfifo", "rxfifo/s"), ("txfifo", "txfifo/s"),
        ],
    },
    "net-nfs": {
        "fields": [
            ("call", "call/s"), ("retrans", "retrans/s"), ("read", "read/s"),
            ("write", "write/s"), ("access", "access/s"),
            ("getatt", "getatt/s"),
        ],
    },
    "net-nfsd": {
        "fields": [
            ("scall", "scall/s"), ("badcall", "badcall/s"),
            ("packet", "packet/s"), ("udp", "udp/s"), ("tcp", "tcp/s"),
            ("hit", "hit/s"), ("miss", "miss/s"), ("sread", "sread/s"),
            ("swrite", "swrite/s"), ("saccess", "saccess/s"),
            ("sgetatt", "sgetatt/s"),
        ],
    },
    "net-sock": {
        "fields": [
            ("totsck", "totsck"), ("tcpsck", "tcpsck"), ("udpsck", "udpsck"),
            ("rawsck", "rawsck"), ("ip-frag", "ip-frag"),
            ("tcp-tw", "tcp-tw"),
        ],
    },
    "net-ip": {
        "fields": [
            ("irec", "irec/s"), ("fwddgm", "fwddgm/s"), ("idel", "idel/s"),
            ("orq", "orq/s"), ("asmrq", "asmrq/s"), ("asmok", "asmok/s"),
            ("fragok", "fragok/s"), ("fragcrt", "fragcrt/s"),
        ],
    },
    "net-eip": {
        "fields": [
            ("ihdrerr", "ihdrerr/s"), ("iadrerr", "iadrerr/s"),
            ("iukwnpr", "iukwnpr/s"), ("idisc", "idisc/s"),
            ("odisc", "odisc/s"), ("onort", "onort/s"), ("asmf", "asmf/s"),
            ("fragf", "fragf/s"),
        ],
    },
    "net-icmp": {
        "fields": [
            ("imsg", "imsg/s"), ("omsg", "omsg/s"), ("iech", "iech/s"),
            ("iechr", "iechr/s"), ("oech", "oech/s"), ("oechr", "oechr/s"),
            ("itm", "itm/s"), ("itmr", "itmr/s"), ("otm", "otm/s"),
            ("otmr", "otmr/s"), ("iadrmk", "iadrmk/s"),
            ("iadrmkr", "iadrmkr/s"), ("oadrmk", "oadrmk/s"),
            ("oadrmkr", "oadrmkr/s"),
        ],
    },
    "net-eicmp": {
        "fields": [
            ("ierr", "ierr/s"), ("oerr", "oerr/s"), ("idstunr", "idstunr/s"),
            ("odstunr", "odstunr/s"), ("itmex", "itmex/s"),
            ("otmex", "otmex/s"), ("iparmpb", "iparmpb/s"),
            ("oparmpb", "oparmpb/s"), ("isrcq", "isrcq/s"),
            ("osrcq", "osrcq/s"), ("iredir", "iredir/s"),
            ("oredir", "oredir/s"),
        ],
    },
    "net-tcp": {
        "fields": [
            ("active", "active/s"), ("passive", "passive/s"),
            ("iseg", "iseg/s"), ("oseg", "oseg/s"),
        ],
    },
    "net-etcp": {
        "fields": [
            ("atmptf", "atmptf/s"), ("estres", "estres/s"),
            ("retrans", "retrans/s"), ("isegerr", "isegerr/s"),
            ("orsts", "orsts/s"),
        ],
    },
    "net-udp": {
        "fields": [
            ("idgm", "idgm/s"), ("odgm", "odgm/s"), ("noport", "noport/s"),
            ("idgmerr", "idgmerr/s"),
        ],
    },
    "net-sock6": {
        "fields": [
            ("tcp6sck", "tcp6sck"), ("udp6sck", "udp6sck"),
            ("raw6sck", "raw6sck"), ("ip6-frag", "ip6-frag"),
        ],
    },
    "net-ip6": {
        "fields": [
            ("irec6", "irec6/s"), ("fwddgm6", "fwddgm6/s"),
            ("idel6", "idel6/s"), ("orq6", "orq6/s"),
            ("asmrq6", "asmrq6/s"), ("asmok6", "asmok6/s"),
            ("imcpck6", "imcpck6/s"), ("omcpck6", "omcpck6/s"),
            ("fragok6", "fragok6/s"), ("fragcr6", "fragcr6/s"),
        ],
    },
    "net-eip6": {
        "fields": [
            ("ihdrer6", "ihdrer6/s"), ("iadrer6", "iadrer6/s"),
            ("iukwnp6", "iukwnp6/s"), ("i2big6", "i2big6/s"),
            ("idisc6", "idisc6/s"), ("odisc6", "odisc6/s"),
            ("inort6", "inort6/s"), ("onort6", "onort6/s"),
            ("asmf6", "asmf6/s"), ("fragf6", "fragf6/s"),
            ("itrpck6", "itrpck6/s"),
        ],
    },
    "net-icmp6": {
        "fields": [
            ("imsg6", "imsg6/s"), ("omsg6", "omsg6/s"), ("iech6", "iech6/s"),
            ("iechr6", "iechr6/s"), ("oechr6", "oechr6/s"),
            ("igmbq6", "igmbq6/s"), ("igmbr6", "igmbr6/s"),
            ("ogmbr6", "ogmbr6/s"), ("igmbrd6", "igmbrd6/s"),
            ("ogmbrd6", "ogmbrd6/s"), ("irtsol6", "irtsol6/s"),
            ("ortsol6", "ortsol6/s"), ("irtad6", "irtad6/s"),
            ("inbsol6", "inbsol6/s"), ("onbsol6", "onbsol6/s"),
            ("inbad6", "inbad6/s"), ("onbad6", "onbad6/s"),
        ],
    },
    "net-eicmp6": {
        "fields": [
            ("ierr6", "ierr6/s"), ("idtunr6", "idtunr6/s"),
            ("odtunr6", "odtunr6/s"), ("itmex6", "itmex6/s"),
            ("otmex6", "otmex6/s"), ("iprmpb6", "iprmpb6/s"),
            ("oprmpb6", "oprmpb6/s"), ("iredir6", "iredir6/s"),
            ("oredir6", "oredir6/s"), ("ipck2b6", "ipck2b6/s"),
            ("opck2b6", "opck2b6/s"),
        ],
    },
    "net-udp6": {
        "fields": [
            ("idgm6", "idgm6/s"), ("odgm6", "odgm6/s"),
            ("noport6", "noport6/s"), ("idgmer6", "idgmer6/s"),
        ],
    },
    "softnet": {
        "device": ("cpu", "CPU"),
        "fields": [
            ("total", "total/s"), ("dropd", "dropd/s"),
            ("squeezd", "squeezd/s"), ("rx_rps", "rx_rps/s"),
            ("flw_lim", "flw_lim/s"),
        ],
    },
}


# Legacy fields sadf still exports but ``sar -A`` no longer prints: dropping
# them is intentional, so they must not be reported as unknown.
_IGNORED_FIELDS = {"rd_sec", "wr_sec", "avgrq-sz", "avgqu-sz"}


def _known_fields(spec: dict) -> set[str]:
    fields = {json_field for json_field, _ in spec["fields"]}
    for key in ("device", "device_last"):
        if key in spec:
            fields.add(spec[key][0])
    fields.update(spec.get("flatten", []))
    return fields


def _build_known_map() -> dict[str, set[str]]:
    """Fields consumed per JSON section, unioned over every spec fed by it.

    Needed because one JSON object can feed several text sections - 'memory'
    supplies both the memory and the swap-utilisation block - and a field
    handled by the sibling spec must not be flagged as unknown.
    """
    known: dict[str, set[str]] = {}
    for name, spec in _SECTIONS.items():
        source = spec.get("source", name)
        known.setdefault(source, set()).update(_known_fields(spec))
    for name, spec in _NETWORK_SECTIONS.items():
        known.setdefault(f"network.{name}", set()).update(_known_fields(spec))
    return known


_KNOWN_FIELDS = _build_known_map()


def maybe_decompress_xz(content: bytes, filename: str) -> tuple[bytes, str]:
    """Transparently decompress single-file .xz uploads (with a size cap)."""
    if not content.startswith(XZ_MAGIC):
        return content, filename
    decompressor = lzma.LZMADecompressor()
    try:
        data = decompressor.decompress(content, max_length=MAX_DECOMPRESSED_BYTES)
    except lzma.LZMAError as exc:
        raise ValueError(f"{filename}: broken xz archive ({exc})")
    if not decompressor.eof:
        raise ValueError(
            f"{filename}: decompressed size exceeds the "
            f"{MAX_DECOMPRESSED_BYTES // (1024 * 1024)} MB limit"
        )
    if filename.endswith(".xz"):
        filename = filename[: -len(".xz")]
    return data, filename


def is_sadf_json(content: bytes) -> bool:
    head = content[:64].lstrip()
    return head.startswith(b"{") and b'"sysstat"' in content[:4096]


def _fmt(value) -> str:
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _render_rows(
    spec: dict, payload, time: str, out: list, warnings: set, section: str
):
    """Emit one header block (header line + data lines) for a section."""
    rows = payload if isinstance(payload, list) else [payload]
    if not rows:
        return
    first = rows[0]
    if spec.get("flatten"):
        first = dict(first)
        for key in spec["flatten"]:
            if isinstance(first.get(key), dict):
                first.update(first.pop(key))
    known = [(j, c) for j, c in spec["fields"] if j in first]
    if not known:
        warnings.add(f"section with unknown fields skipped: {list(first)[:4]}")
        return
    handled = _KNOWN_FIELDS.get(section, set())
    for field in first:
        if field not in handled and field not in _IGNORED_FIELDS:
            warnings.add(f"unknown field skipped: {section}.{field}")

    columns = [c for _, c in known]
    if "device" in spec:
        header = f"{spec['device'][1]} {' '.join(columns)}"
    elif "device_last" in spec:
        header = f"{' '.join(columns)} {spec['device_last'][1]}"
    else:
        header = " ".join(columns)

    out.append("")
    out.append(f"{time} {header}")
    for row in rows:
        if spec.get("flatten"):
            row = dict(row)
            for key in spec["flatten"]:
                if isinstance(row.get(key), dict):
                    row.update(row.pop(key))
        values = [_fmt(row.get(j, 0)) for j, _ in known]
        if "device" in spec:
            values.insert(0, str(row.get(spec["device"][0], "?")))
        elif "device_last" in spec:
            values.append(str(row.get(spec["device_last"][0], "?")))
        out.append(f"{time} {' '.join(values)}")


def sadf_json_to_sar_text(content: bytes) -> tuple[str, list[str]]:
    """Render sadf -j JSON back into the classic sar -A text layout."""
    try:
        data = json.loads(content)
        host = data["sysstat"]["hosts"][0]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"not a valid sadf JSON file ({exc})")

    ncpu = host.get("number-of-cpus", 1)
    os_details = (
        f"Linux {host.get('release', 'unknown')} ({host.get('nodename', 'unknown')}) "
        f"\t{host.get('file-date', '2000-01-01')} \t_{host.get('machine', 'unknown')}_"
        f"\t({ncpu} CPU)"
    )
    out = [os_details]
    warnings: set[str] = set()

    for entry in host.get("statistics", []):
        time = entry.get("timestamp", {}).get("time")
        if not time:
            continue
        for section, payload in entry.items():
            if section in ("timestamp",) or section in _SKIPPED_SECTIONS:
                continue
            if section == "network":
                for sub, sub_payload in payload.items():
                    spec = _NETWORK_SECTIONS.get(sub)
                    if spec is None:
                        warnings.add(f"unknown network section skipped: {sub}")
                        continue
                    _render_rows(
                        spec, sub_payload, time, out, warnings, f"network.{sub}"
                    )
                continue
            spec = _SECTIONS.get(section)
            if spec is None:
                warnings.add(f"unknown section skipped: {section}")
                continue
            _render_rows(spec, payload, time, out, warnings, section)
            # memory feeds a second text section (swap utilization)
            if section == "memory":
                _render_rows(
                    _SECTIONS["memory-swap"], payload, time, out, warnings, section
                )

    for restart in host.get("restarts", []):
        boot = restart.get("boot", restart) if isinstance(restart, dict) else {}
        boot_time = boot.get("time")
        if boot_time:
            out.append("")
            out.append(f"{boot_time} LINUX RESTART\t({ncpu} CPU)")

    if len(out) <= 1:
        raise ValueError("sadf JSON contains no usable statistics sections")
    out.append("")
    return "\n".join(out) + "\n", sorted(warnings)


def preprocess_upload(content: bytes, filename: str) -> tuple[bytes, str, list[str]]:
    """xz decompression + sadf-JSON conversion; returns (content, name, warnings).

    Raises ValueError with a user-facing message on broken input.
    """
    warnings: list[str] = []
    content, filename = maybe_decompress_xz(content, filename)
    if is_sadf_json(content):
        text, conv_warnings = sadf_json_to_sar_text(content)
        content = text.encode()
        if filename.endswith(".json"):
            filename = filename[: -len(".json")]
        warnings.append(f"{filename}: converted from sadf JSON")
        warnings.extend(f"{filename}: {w}" for w in conv_warnings)
    return content, filename, warnings
