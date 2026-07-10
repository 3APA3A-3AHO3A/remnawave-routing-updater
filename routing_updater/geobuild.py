"""Server-side trimming of geoip.dat / geosite.dat down to the categories a template
actually uses — the same idea as the client's ``UseChunkFiles``, done on the server so
clients download a tiny file instead of the full ~10–17 MB database.

Both files are V2Ray/Xray protobuf:

    GeoSiteList { repeated GeoSite entry = 1 }
    GeoSite     { string country_code = 1; repeated Domain domain = 2 }
    GeoIPList   { repeated GeoIP entry = 1 }
    GeoIP       { string country_code = 1; repeated CIDR cidr = 2; bool reverse_match = 3 }

We only need to *select* whole top-level entries by their ``country_code`` (the category
name) and re-emit the chosen ones **verbatim** — so a minimal protobuf reader is enough and
no ``protobuf`` dependency or ``.proto`` compilation is required. Because entries are copied
byte-for-byte, every nested domain/attribute/CIDR is preserved exactly.
"""

import os

from .logger import logger

# Template fields that hold geosite / geoip references.
SITE_FIELDS = ("DirectSites", "ProxySites", "BlockSites")
IP_FIELDS = ("DirectIp", "ProxyIp", "BlockIp")


# ---- minimal protobuf primitives -------------------------------------------------

def _read_varint(buf, pos):
    """Decode a base-128 varint at ``pos``. Returns ``(value, new_pos)``."""
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


def _encode_varint(value):
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _skip_field(buf, pos, wire):
    """Advance ``pos`` past one field of the given wire type."""
    if wire == 0:  # varint
        _, pos = _read_varint(buf, pos)
    elif wire == 1:  # 64-bit
        pos += 8
    elif wire == 2:  # length-delimited
        length, pos = _read_varint(buf, pos)
        pos += length
    elif wire == 5:  # 32-bit
        pos += 4
    else:
        raise ValueError(f"Unsupported wire type {wire}")
    return pos


def _country_code(entry):
    """Read field 1 (country_code, a string) of a GeoSite/GeoIP entry."""
    pos = 0
    n = len(entry)
    while pos < n:
        tag, pos = _read_varint(entry, pos)
        field, wire = tag >> 3, tag & 0x07
        if field == 1 and wire == 2:
            length, pos = _read_varint(entry, pos)
            return entry[pos:pos + length].decode("utf-8", "replace")
        pos = _skip_field(entry, pos, wire)
    return ""


def parse_entries(data):
    """Return ``[(country_code, entry_bytes), ...]`` for the top-level ``entry`` field."""
    entries = []
    pos = 0
    n = len(data)
    while pos < n:
        tag, pos = _read_varint(data, pos)
        field, wire = tag >> 3, tag & 0x07
        if field == 1 and wire == 2:
            length, pos = _read_varint(data, pos)
            chunk = data[pos:pos + length]
            pos += length
            entries.append((_country_code(chunk), chunk))
        else:
            pos = _skip_field(data, pos, wire)
    return entries


def serialize_entries(chunks):
    """Wrap each entry as a top-level ``entry = 1`` field and concatenate."""
    out = bytearray()
    header = bytes([(1 << 3) | 2])  # field 1, wire type 2
    for chunk in chunks:
        out += header
        out += _encode_varint(len(chunk))
        out += chunk
    return bytes(out)


def trim_bytes(data, wanted_upper):
    """Keep only entries whose category is in ``wanted_upper`` (a set of UPPER names).

    Returns ``(new_bytes, found_upper_set)``. Matching is case-insensitive; the emitted
    bytes keep each entry's original casing and content untouched.
    """
    kept = []
    found = set()
    for cc, chunk in parse_entries(data):
        found.add(cc.upper())
        if cc.upper() in wanted_upper:
            kept.append(chunk)
    return serialize_entries(kept), found


# ---- template parsing ------------------------------------------------------------

def _extract(entries, prefix):
    """Pull ``prefix:name`` category names (uppercased, without ``@attribute``)."""
    out = set()
    for raw in entries or []:
        item = str(raw).strip()
        if item.lower().startswith(prefix):
            name = item[len(prefix):].split("@", 1)[0].strip()
            if name:
                out.add(name.upper())
    return out


def categories_from_template(template):
    """Return ``(site_categories, ip_categories)`` referenced by the template."""
    site, ip = set(), set()
    for field in SITE_FIELDS:
        site |= _extract(template.get(field), "geosite:")
    for field in IP_FIELDS:
        ip |= _extract(template.get(field), "geoip:")
    return site, ip


# ---- I/O -------------------------------------------------------------------------

def _trim_file(src, dst, wanted_upper, label):
    """Trim ``src`` into ``dst`` keeping ``wanted_upper``. Returns True if ``dst`` changed."""
    if not os.path.exists(src):
        logger.error(f"{label}: source {src} missing — cannot trim (clients keep old copy).")
        return False

    with open(src, "rb") as f:
        data = f.read()

    new, found = trim_bytes(data, wanted_upper)

    missing = wanted_upper - found
    if missing:
        logger.warning(f"{label}: categories not found in source: {', '.join(sorted(missing))}")
    if not wanted_upper:
        logger.warning(f"{label}: template references no categories — output will be empty.")

    old = None
    if os.path.exists(dst):
        with open(dst, "rb") as f:
            old = f.read()
    if old == new:
        return False

    tmp = dst + ".tmp"
    with open(tmp, "wb") as f:
        f.write(new)
    os.replace(tmp, dst)  # atomic
    kept = len(wanted_upper & found)
    logger.info(f"{label}: trimmed to {kept} categor(y/ies), {len(new)} bytes (from {len(data)}).")
    return True


def trim_all(cache_dir, out_dir, site_categories, ip_categories):
    """Trim the cached full databases into the served ones. Returns True if either changed."""
    os.makedirs(out_dir, exist_ok=True)
    changed = False
    changed |= _trim_file(
        os.path.join(cache_dir, "geosite.dat"),
        os.path.join(out_dir, "geosite.dat"),
        site_categories,
        "geosite.dat",
    )
    changed |= _trim_file(
        os.path.join(cache_dir, "geoip.dat"),
        os.path.join(out_dir, "geoip.dat"),
        ip_categories,
        "geoip.dat",
    )
    return changed
