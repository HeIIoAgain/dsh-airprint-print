#!/usr/bin/env python3
"""LAN discovery helpers: TCP port probe, mDNS (Bonjour) browse, WS-Discovery.

All standard library; no avahi/zeroconf packages required.
"""

from __future__ import annotations

import socket
import struct
import time

MDNS_ADDR = ("224.0.0.251", 5353)
WSD_ADDR = ("239.255.255.250", 3702)

PRINTER_PORTS = {
    80: "EWS / WSD (HTTP)",
    443: "EWS / IPPS (TLS)",
    515: "LPD / LPR",
    631: "IPP",
    9100: "RAW / JetDirect",
    5357: "WSD print (HTTP)",
}


def tcp_scan(host: str, ports=None, timeout: float = 2.0) -> dict[int, bool]:
    results = {}
    for port in (ports or PRINTER_PORTS):
        sock = socket.socket()
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            results[port] = True
        except OSError:
            results[port] = False
        finally:
            sock.close()
    return results


# ---------------------------------------------------------------------------
# minimal DNS message reader (enough for mDNS responses)
# ---------------------------------------------------------------------------
def _enc_name(name: str) -> bytes:
    out = b""
    for label in name.split("."):
        if label:
            out += bytes([len(label)]) + label.encode()
    return out + b"\x00"


def _read_name(data: bytes, offset: int, guard: int = 0) -> tuple[str, int]:
    labels = []
    while guard < 64:
        guard += 1
        if offset >= len(data):
            break
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if length & 0xC0 == 0xC0:
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            name, _ = _read_name(data, pointer, guard)
            labels.append(name)
            offset += 2
            break
        labels.append(data[offset + 1:offset + 1 + length].decode("latin-1"))
        offset += 1 + length
    return ".".join(labels), offset


def _parse_mdns(data: bytes) -> list[dict]:
    if len(data) < 12:
        return []
    _id, _flags, qd, an, ns, ar = struct.unpack(">HHHHHH", data[:12])
    offset = 12
    for _ in range(qd):
        _name, offset = _read_name(data, offset)
        offset += 4
    records = []
    for _ in range(an + ns + ar):
        if offset >= len(data):
            break
        name, offset = _read_name(data, offset)
        if offset + 10 > len(data):
            break
        rtype, _cls, _ttl, rdlen = struct.unpack(">HHIH", data[offset:offset + 10])
        offset += 10
        rdata = data[offset:offset + rdlen]
        record = {"name": name, "type": rtype}
        if rtype == 12:  # PTR
            record["ptr"], _ = _read_name(data, offset)
        elif rtype == 33:  # SRV
            if len(rdata) >= 6:
                _prio, _weight, port = struct.unpack(">HHH", rdata[:6])
                record["port"] = port
                record["target"], _ = _read_name(data, offset + 6)
        elif rtype == 16:  # TXT
            txt, i = [], 0
            while i < len(rdata):
                length = rdata[i]
                txt.append(rdata[i + 1:i + 1 + length].decode("latin-1"))
                i += 1 + length
            record["txt"] = txt
        elif rtype == 1 and len(rdata) >= 4:  # A
            record["address"] = socket.inet_ntoa(rdata[:4])
        elif rtype == 28 and len(rdata) >= 16:  # AAAA
            record["address6"] = socket.inet_ntop(socket.AF_INET6, rdata[:16])
        records.append(record)
        offset += rdlen
    return records


def mdns_query(services, *, address: str | None = None, timeout: float = 4.0) -> list[dict]:
    """Ask for PTR records of the given service types; return all records seen."""
    query = b""
    for service in services:
        query += _enc_name(service) + struct.pack(">HH", 12, 1)
    packet = struct.pack(">HHHHHH", 0, 0, len(services), 0, 0, 0) + query
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(0.5)
    records: list[dict] = []
    try:
        sock.sendto(packet, (address, 5353) if address else MDNS_ADDR)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, _addr = sock.recvfrom(9000)
            except socket.timeout:
                continue
            records.extend(_parse_mdns(data))
    finally:
        sock.close()
    return records


def browse_printers(timeout: float = 4.0) -> list[dict]:
    """Browse mDNS for IPP/IPPS/LPD advertisers and resolve them to host:port."""
    services = ["_ipp._tcp.local", "_ipps._tcp.local", "_printer._tcp.local",
                "_pdl-datastream._tcp.local", "_http._tcp.local"]
    records = mdns_query(services, timeout=timeout)
    by_name: dict[str, dict] = {}
    srv_records = [r for r in records if r["type"] == 33]
    address_map = {r["name"]: r["address"] for r in records if r["type"] == 1 and "address" in r}
    txt_map = {r["name"]: r.get("txt", []) for r in records if r["type"] == 16}
    for srv in srv_records:
        name = srv["name"]
        service = ".".join(name.split(".")[1:])
        key = (srv.get("target", name), srv.get("port"))
        entry = by_name.setdefault(str(key), {
            "instance": name,
            "service": service,
            "port": srv.get("port"),
            "target": srv.get("target", ""),
            "addresses": set(),
            "txt": {},
        })
        if srv.get("target") in address_map:
            entry["addresses"].add(address_map[srv["target"]])
        entry["txt"].update(_txt_dict(txt_map.get(name, [])))
    printers = []
    for entry in by_name.values():
        entry["addresses"] = sorted(entry["addresses"])
        printers.append(entry)
    printers.sort(key=lambda item: (item["service"], item["instance"]))
    return printers


def _txt_dict(pairs) -> dict:
    out = {}
    for item in pairs:
        if "=" in item:
            key, value = item.split("=", 1)
            out[key] = value
        elif item:
            out[item] = ""
    return out


def wsd_probe(*, timeout: float = 4.0) -> list[dict]:
    """Send one WS-Discovery Probe; return devices that answer."""
    probe = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
        'xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery">'
        '<soap:Header><wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>'
        '<wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>'
        '<wsa:MessageID>uuid:5d8f5c1e-0001-4000-8000-000000000001</wsa:MessageID>'
        '</soap:Header><soap:Body><wsd:Probe/></soap:Body></soap:Envelope>'
    ).encode()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.5)
    found = []
    try:
        sock.sendto(probe, WSD_ADDR)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, address = sock.recvfrom(16384)
            except socket.timeout:
                continue
            text = data.decode("utf-8", "replace")
            found.append({
                "address": address[0],
                "xaddrs": _xml_values(text, "XAddrs"),
                "types": _xml_values(text, "Types"),
            })
    finally:
        sock.close()
    return found


def _xml_values(text: str, tag: str) -> list[str]:
    import re
    pattern = r"<[^>]*%s[^>]*>(.*?)</[^>]*%s>" % (tag, tag)
    return re.findall(pattern, text, flags=re.S)
