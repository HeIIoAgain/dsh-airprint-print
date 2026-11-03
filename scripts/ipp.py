#!/usr/bin/env python3
"""Minimal, dependency-free IPP (Internet Printing Protocol) client.

Only what is needed to drive an AirPrint / IPP Everywhere printer:
Get-Printer-Attributes and Print-Job, over HTTP or HTTPS.

Used by airprint.py; kept separate so it can be imported or used as a library.
Wire format: RFC 8010 (encoding) + RFC 8011 (semantics).
"""

from __future__ import annotations

import http.client
import socket
import ssl
import struct
import sys

# ----------------------------------------------------------------------------
# value tags (RFC 8010 section 3.5)
# ----------------------------------------------------------------------------
TAG_OPERATION = 0x01
TAG_JOB = 0x02
TAG_END = 0x03
TAG_PRINTER = 0x04

TAG_TEXT = 0x41           # textWithoutLanguage
TAG_NAME = 0x42           # nameWithoutLanguage
TAG_KEYWORD = 0x44        # keyword
TAG_URI = 0x45            # uri
TAG_CHARSET = 0x47        # charset
TAG_LANGUAGE = 0x48       # naturalLanguage
TAG_MIME = 0x49           # mimeMediaType
TAG_INTEGER = 0x21
TAG_BOOLEAN = 0x22
TAG_ENUM = 0x23
TAG_RESOLUTION = 0x32
TAG_RANGE = 0x34
TAG_BEGIN_COLLECTION = 0x35
TAG_OCTET = 0x30

# operation ids (RFC 8011 section 4.4.1)
OP_PRINT_JOB = 0x0002
OP_CANCEL_JOB = 0x0008
OP_GET_JOB_ATTRIBUTES = 0x0009
OP_GET_PRINTER_ATTRIBUTES = 0x000B
OP_GET_JOBS = 0x000A

STATUS = {
    0x0000: "successful-ok",
    0x0001: "successful-ok-ignored-or-substituted-attributes",
    0x0002: "successful-ok-conflicting-attributes",
    0x0400: "client-error-bad-request",
    0x0401: "client-error-forbidden",
    0x0402: "client-error-not-authenticated",
    0x0403: "client-error-not-authorized",
    0x0404: "client-error-not-possible",
    0x0405: "client-error-timeout",
    0x0406: "client-error-not-found",
    0x0407: "client-error-gone",
    0x0408: "client-error-request-entity-too-large",
    0x040A: "client-error-document-format-not-supported",
    0x040B: "client-error-attributes-or-values-not-supported",
    0x040C: "client-error-uri-scheme-not-supported",
    0x040D: "client-error-charset-not-supported",
    0x040E: "client-error-conflicting-attributes",
    0x0411: "client-error-document-format-error",
    0x0500: "server-error-internal-error",
    0x0501: "server-error-operation-not-supported",
    0x0502: "server-error-service-unavailable",
    0x0503: "server-error-version-not-supported",
    0x0504: "server-error-device-error",
    0x0505: "server-error-temporary-error",
    0x0506: "server-error-not-accepting-jobs",
    0x0507: "server-error-busy",
    0x0508: "server-error-job-canceled",
}

PRINTER_STATE = {3: "idle", 4: "processing", 5: "stopped"}


# ----------------------------------------------------------------------------
# request encoding
# ----------------------------------------------------------------------------
def _attr(tag: int, name: str, value) -> bytes:
    raw_name = name.encode()
    if isinstance(value, bool):
        raw = b"\x01" if value else b"\x00"
    elif isinstance(value, int):
        raw = struct.pack(">i", value)
    elif isinstance(value, str):
        raw = value.encode()
    elif isinstance(value, bytes):
        raw = value
    else:
        raise TypeError(f"unsupported attribute value: {value!r}")
    return struct.pack(">BH", tag, len(raw_name)) + raw_name + struct.pack(">H", len(raw)) + raw


def build_request(
    operation: int,
    printer_uri: str,
    *,
    request_id: int = 1,
    version: tuple[int, int] = (1, 1),
    operation_attrs=(),
    job_attrs=(),
    body: bytes = b"",
    user: str = "dsh",
) -> bytes:
    out = struct.pack(">BBHI", version[0], version[1], operation, request_id)
    out += bytes([TAG_OPERATION])
    out += _attr(TAG_CHARSET, "attributes-charset", "utf-8")
    out += _attr(TAG_LANGUAGE, "attributes-natural-language", "en-us")
    out += _attr(TAG_URI, "printer-uri", printer_uri)
    out += _attr(TAG_NAME, "requesting-user-name", user)
    for tag, name, value in operation_attrs:
        out += _attr(tag, name, value)
    if job_attrs:
        out += bytes([TAG_JOB])
        for tag, name, value in job_attrs:
            out += _attr(tag, name, value)
    out += bytes([TAG_END])
    return out + body


# ----------------------------------------------------------------------------
# response decoding
# ----------------------------------------------------------------------------
def _decode_text(raw: bytes) -> str:
    """Decode an IPP text/name value.

    Some printers (Brother included) send language-tagged values even for
    nameWithoutLanguage: u16 language-length, language, u16 text-length, text.
    """
    if len(raw) >= 4:
        (language_length,) = struct.unpack(">H", raw[:2])
        if 0 < language_length < 64 and len(raw) >= 4 + language_length:
            (text_length,) = struct.unpack(">H", raw[2 + language_length:4 + language_length])
            if 4 + language_length + text_length == len(raw):
                raw = raw[4 + language_length:]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", "replace")


def _decode_value(tag: int, raw: bytes):
    if tag in (TAG_INTEGER, TAG_ENUM):
        return struct.unpack(">i", raw)[0] if len(raw) == 4 else raw
    if tag == TAG_BOOLEAN:
        return raw != b"\x00"
    if tag == TAG_RESOLUTION and len(raw) in (9,):
        x, y, unit = struct.unpack(">iiB", raw)
        return f"{x}x{y}dpi" if unit == 3 else f"{x}x{y}"
    if tag in (TAG_TEXT, TAG_NAME, TAG_KEYWORD, TAG_URI, TAG_CHARSET, TAG_LANGUAGE, TAG_MIME):
        return _decode_text(raw)
    if tag in (0x35, 0x36):  # Brother misuses the collection tags for strings
        return _decode_text(raw)
    if tag == TAG_RANGE and len(raw) % 8 == 0:
        return [struct.unpack(">ii", raw[i:i + 8]) for i in range(0, len(raw), 8)]
    return raw


def _read_name(data: bytes, offset: int) -> tuple[str, int]:
    labels = []
    guard = 0
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
            name, _ = _read_name(data, pointer)
            labels.append(name)
            offset += 2
            break
        labels.append(data[offset + 1:offset + 1 + length].decode("utf-8", "replace"))
        offset += 1 + length
    return ".".join(labels), offset


class Response:
    __slots__ = ("version", "status", "request_id", "groups")

    def __init__(self, version, status, request_id, groups):
        self.version = version
        self.status = status
        self.request_id = request_id
        self.groups = groups  # list of (group_tag, [(tag, name, value), ...])

    @property
    def ok(self) -> bool:
        return self.status in (0x0000, 0x0001, 0x0002)

    @property
    def status_name(self) -> str:
        return STATUS.get(self.status, f"unknown-0x{self.status:04x}")

    def attributes(self) -> dict[str, list]:
        """Flatten all groups into {name: [values]} preserving order."""
        out: dict[str, list] = {}
        for _tag, attrs in self.groups:
            for tag, name, value in attrs:
                if not name:
                    continue
                decoded = _decode_value(tag, value)
                bucket = out.setdefault(name, [])
                if decoded not in bucket:  # many printers repeat whole groups
                    bucket.append(decoded)
        return out

    def get(self, name: str, default=None):
        values = self.attributes().get(name)
        return values[0] if values else default


def decode_response(data: bytes) -> Response:
    if len(data) < 8:
        raise ValueError(f"short IPP response ({len(data)} bytes)")
    vmaj, vmin, status, request_id = struct.unpack(">BBHI", data[:8])
    offset = 8
    groups = []
    current = []
    while offset < len(data):
        tag = data[offset]
        if tag == TAG_END:
            if current:
                groups.append((None, current))
            break
        if tag < 0x10:  # delimiter tag
            if current:
                groups.append((tag, current))
            current = []
            offset += 1
            continue
        if offset + 3 > len(data):
            break
        (name_length,) = struct.unpack(">H", data[offset + 1:offset + 3])
        name = data[offset + 3:offset + 3 + name_length].decode("utf-8", "replace")
        offset += 3 + name_length
        if offset + 2 > len(data):
            break
        (value_length,) = struct.unpack(">H", data[offset:offset + 2])
        value = data[offset + 2:offset + 2 + value_length]
        offset += 2 + value_length
        current.append((tag, name, value))
    if current:
        groups.append((None, current))
    return Response((vmaj, vmin), status, request_id, groups)


# ----------------------------------------------------------------------------
# transport
# ----------------------------------------------------------------------------
def post(
    host: str,
    path: str,
    body: bytes,
    *,
    port: int = 631,
    tls: bool = False,
    timeout: float = 180.0,
) -> bytes:
    """POST an IPP request. Returns the raw response body."""
    if tls:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # printers ship self-signed certs
        conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=context)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/ipp", "Content-Length": str(len(body))},
        )
        reply = conn.getresponse()
        payload = reply.read()
        if reply.status != 200:
            raise IOError(f"HTTP {reply.status} {reply.reason} from {path}")
        return payload
    finally:
        conn.close()


# ----------------------------------------------------------------------------
# high level operations
# ----------------------------------------------------------------------------
def printer_uri(host: str, path: str = "/ipp/print", *, tls: bool = False,
                port: int = 631) -> str:
    scheme = "ipps" if tls else "ipp"
    return f"{scheme}://{host}:{port}{path}"


def get_printer_attributes(
    host: str,
    path: str = "/ipp/print",
    *,
    port: int = 631,
    tls: bool = False,
    timeout: float = 20.0,
) -> Response:
    uri = printer_uri(host, path, tls=tls, port=port)
    body = build_request(OP_GET_PRINTER_ATTRIBUTES, uri)
    return decode_response(post(host, path, body, port=port, tls=tls, timeout=timeout))


def print_job(
    host: str,
    document: bytes,
    *,
    path: str = "/ipp/print",
    port: int = 631,
    tls: bool = False,
    document_format: str = "image/urf",
    job_name: str = "dsh-print",
    copies: int = 1,
    user: str = "dsh",
    timeout: float = 300.0,
) -> Response:
    uri = printer_uri(host, path, tls=tls, port=port)
    body = build_request(
        OP_PRINT_JOB,
        uri,
        operation_attrs=[(TAG_MIME, "document-format", document_format)],
        job_attrs=[
            (TAG_NAME, "job-name", job_name),
            (TAG_INTEGER, "copies", copies),
        ],
        body=document,
        user=user,
    )
    return decode_response(post(host, path, body, port=port, tls=tls, timeout=timeout))


def wait_for_idle(
    host: str,
    path: str = "/ipp/print",
    *,
    port: int = 631,
    tls: bool = False,
    poll_seconds: float = 4.0,
    max_wait: float = 240.0,
    on_poll=None,
):
    """Poll printer state until it returns to idle with an empty queue."""
    import time

    deadline = time.monotonic() + max_wait
    last = None
    while time.monotonic() < deadline:
        try:
            resp = get_printer_attributes(host, path, port=port, tls=tls)
            attrs = resp.attributes()
            state = attrs.get("printer-state", [None])[0]
            queued = attrs.get("queued-job-count", [None])[0]
            reasons = attrs.get("printer-state-reasons", [None])[0]
            message = attrs.get("printer-state-message", [""])[0]
            last = {
                "state": state,
                "state_name": PRINTER_STATE.get(state, str(state)),
                "queued": queued,
                "reasons": reasons,
                "message": message,
            }
            if on_poll:
                on_poll(last)
            if state == 3 and (queued in (0, None)) and reasons in ("none", None):
                return last
        except Exception as exc:  # transient network errors are expected
            last = {"error": repr(exc)}
            if on_poll:
                on_poll(last)
        time.sleep(poll_seconds)
    return last


if __name__ == "__main__":  # tiny manual probe
    target = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    r = get_printer_attributes(target)
    print(r.status_name)
    for key, values in r.attributes().items():
        if key in ("printer-name", "printer-make-and-model", "printer-state",
                   "document-format-supported", "document-format-preferred",
                   "printer-uri-supported"):
            print(f"  {key}: {values}")
