#!/usr/bin/env python3
"""airprint — print to AirPrint / IPP printers that only speak Apple Raster.

Why this exists
---------------
Many cheap inkjet/MFP printers (Brother, HP, Canon, Epson) expose IPP but NOT
PDF: they advertise `document-format-supported = application/octet-stream` and
`document-format-preferred = image/urf`. Raw port 9100 is often closed. So the
only way to print from a script is to build an Apple Raster (URF) bitmap and
POST it as an IPP Print-Job. That is what this tool does end to end.

Commands
--------
  selftest                    encode/decode round trip, no network
  probe   --host H            ports + mDNS + WSD + IPP capabilities
  discover                    list printers advertised on the LAN (mDNS)
  status  --host H            state, queue, media, supplies
  test-page --host H          render and print a diagnostic page
  print   --host H FILE       print an image file (png/jpg/...)
  text    --host H TEXT...    render text and print it
  encode  FILE --out X.urf    image -> URF only (no network)
  decode  X.urf --out X.png   URF -> PNG (inspection)

Examples
--------
  airprint.py discover
  airprint.py probe --host 192.168.1.50
  airprint.py test-page --host 192.168.1.50 --dry-run --out /tmp/page.png
  airprint.py print --host 192.168.1.50 photo.jpg --page-size 4x6
  airprint.py text --host 192.168.1.50 "hello from the LAN" --copy 1
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ipp          # noqa: E402
import netprobe     # noqa: E402
import render       # noqa: E402
import urf          # noqa: E402

DEFAULT_PATHS = ("/ipp/print", "/ipp", "/")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".ppm"}
KEY_ATTRS = (
    "printer-name", "printer-make-and-model", "printer-info", "printer-state",
    "printer-state-reasons", "printer-state-message", "queued-job-count",
    "document-format-supported", "document-format-preferred", "urf-supported",
    "media-ready", "media-default", "printer-resolution-default",
    "printer-is-accepting-jobs", "ipp-versions-supported", "printer-uri-supported",
    "printer-device-id", "mopria-certified", "ipp-features-supported",
    "marker-levels", "marker-names", "printer-supply",
)


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------
def _add_network(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", required=True, help="printer IPv4/hostname")
    parser.add_argument("--path", default=None,
                        help="IPP resource path (default: auto-detect /ipp/print, /ipp, /)")
    parser.add_argument("--port", type=int, default=None,
                        help="IPP port (default: 631, or 443 with --tls)")
    parser.add_argument("--tls", action="store_true", help="use IPPS over HTTPS (self-signed OK)")
    parser.add_argument("--user", default="dsh", help="requesting-user-name (default: dsh)")


def _add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", default=None, help="save a preview PNG / .urf here")
    parser.add_argument("--json", action="store_true", help="machine readable output")


def _port(args) -> int:
    return args.port if args.port else (443 if args.tls else 631)


def _clients(args):
    return dict(port=_port(args), tls=args.tls)


def _endpoints(args) -> list[str]:
    if args.path:
        return [args.path]
    return list(DEFAULT_PATHS)


def _try_attributes(args, *, quiet: bool = False):
    """Find a working IPP endpoint and return (path, Response)."""
    errors = []
    for path in _endpoints(args):
        try:
            response = ipp.get_printer_attributes(args.host, path, **_clients(args))
            if response.ok:
                return path, response
            errors.append(f"{path}: {response.status_name}")
        except Exception as exc:
            errors.append(f"{path}: {exc}")
    if not quiet:
        print("could not read printer attributes: " + "; ".join(errors))
    return None, None


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def cmd_selftest(args) -> int:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (240, 120), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle([10, 10, 110, 60], fill=(200, 30, 30))
    draw.text((10, 80), "URF self test", fill=(0, 0, 0))
    data = urf.encode_image(image, dpi=300)
    ok, mismatched, message = urf.verify([image], data, dpi=300)
    print(f"encoded {image.width}x{image.height} -> {len(data)} bytes URF")
    print(f"round trip: {'OK' if ok else 'FAILED'} ({message})")
    if not ok:
        return 1
    pages = urf.decode(data)
    if pages[0][0].tobytes() != image.convert("RGB").tobytes():
        print("decoded pixels differ from source")
        return 1
    print("selftest passed")
    return 0


def cmd_discover(args) -> int:
    printers = netprobe.browse_printers(timeout=args.timeout)
    if args.json:
        print(json.dumps(printers, indent=2, default=str))
        return 0 if printers else 1
    if not printers:
        print("no mDNS printer advertisements seen (multicast may be blocked)")
        return 1
    for printer in printers:
        addresses = ",".join(printer["addresses"]) or "?"
        txt = printer["txt"]
        pdl = txt.get("pdl", txt.get("URF", ""))
        model = txt.get("ty") or txt.get("product") or printer["instance"]
        extra = f"  pdl={pdl}" if pdl else ""
        print(f"{addresses:15s} :{printer['port']:<5d} {printer['service']:14s} {model}{extra}")
    return 0


def cmd_probe(args) -> int:
    report: dict = {"host": args.host}
    ports = netprobe.tcp_scan(args.host, timeout=args.timeout)
    report["ports"] = {str(port): open_ for port, open_ in ports.items()}
    print(f"== TCP ports on {args.host}")
    for port, label in netprobe.PRINTER_PORTS.items():
        print(f"   {port:5d}  {'OPEN ' if ports.get(port) else 'closed'}  {label}")

    print("== mDNS services (querying the printer directly)")
    services = ["_ipp._tcp.local", "_ipps._tcp.local", "_printer._tcp.local",
                "_pdl-datastream._tcp.local", "_http._tcp.local"]
    try:
        records = netprobe.mdns_query(services, address=args.host, timeout=args.timeout)
    except OSError:
        records = []
    mdns = {}
    for record in records:
        if record["type"] == 33:
            mdns.setdefault(record["name"], {})["port"] = record.get("port")
        elif record["type"] == 16:
            mdns.setdefault(record["name"], {})["txt"] = dict(
                (item.split("=", 1) + [""])[:2] for item in record.get("txt", []) if "=" in item)
    report["mdns"] = mdns
    if not mdns:
        print("   (no answer; the printer may not answer unicast mDNS)")
    for name, info in sorted(mdns.items()):
        print(f"   {name}  port={info.get('port')}")
        for key in ("ty", "pdl", "rp", "URF", "TLS", "print_wfds", "mopria-certified"):
            if key in info.get("txt", {}):
                print(f"      {key} = {info['txt'][key]}")

    print("== WS-Discovery (Windows WSD path)")
    devices = netprobe.wsd_probe(timeout=args.timeout)
    devices = [device for device in devices if device["address"] == args.host]
    report["wsd"] = devices
    if not devices:
        print("   (no WS-Discovery reply)")
    for device in devices:
        print(f"   {device['address']}  xaddrs={device['xaddrs']}  types={device['types']}")

    print("== IPP")
    path, response = _try_attributes(args)
    if response is None:
        print("   no working IPP endpoint")
        return 1
    attrs = response.attributes()
    report["ipp"] = {"path": path, "status": response.status_name,
                     "attributes": {key: attrs.get(key) for key in KEY_ATTRS if key in attrs}}
    print(f"   endpoint {path}  status={response.status_name}")
    for key in KEY_ATTRS:
        if key in attrs:
            values = attrs[key]
            print(f"   {key}: {values[0] if len(values) == 1 else values}")
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    return 0


def cmd_status(args) -> int:
    path, response = _try_attributes(args)
    if response is None:
        return 1
    attrs = response.attributes()
    state = attrs.get("printer-state", [None])[0]

    def one(name):
        values = attrs.get(name) or [None]
        return values[0] if len(values) == 1 else values

    summary = {
        "host": args.host,
        "path": path,
        "state": ipp.PRINTER_STATE.get(state, state),
        "reasons": one("printer-state-reasons"),
        "message": one("printer-state-message"),
        "queued": one("queued-job-count"),
        "accepting": one("printer-is-accepting-jobs"),
        "media_ready": one("media-ready"),
        "formats": one("document-format-supported"),
        "preferred": one("document-format-preferred"),
        "marker_levels": one("marker-levels"),
        "marker_names": one("marker-names"),
    }
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
        return 0
    print(f"{args.host}  state={summary['state']}  queued={summary['queued']}  "
          f"accepting={summary['accepting']}")
    print(f"message: {summary['message']}")
    print(f"reasons: {summary['reasons']}")
    print(f"media:   {summary['media_ready']}")
    print(f"formats: {summary['formats']}  preferred={summary['preferred']}")
    if summary["marker_levels"]:
        print(f"ink:     {summary['marker_names']} {summary['marker_levels']}")
    return 0


def _submit(images, args, *, dpi: int, page_size: str, source: str) -> int:
    """Shared tail of every print command: verify, optionally dry-run, submit, wait."""
    if not images:
        print("nothing to print")
        return 1
    started = time.time()
    data = urf.encode_images(images, dpi=dpi)
    ok, mismatched, message = urf.verify(images, data, dpi=dpi)
    if not ok:
        print(f"internal error: URF round trip failed ({message}); refusing to print")
        return 1

    job_name = args.job_name or f"dsh-{source}-{int(started)}"
    preview = args.out or f"/tmp/airprint-{int(started)}.png"
    try:
        images[0].save(preview)
    except OSError:
        preview = None

    print(f"rendered {len(images)} page(s) at {dpi} dpi {page_size.upper()}, "
          f"URF {len(data) / 1024:.0f} KiB, job {job_name}")
    if preview:
        print(f"preview: {preview}")

    if args.dry_run:
        urf_path = str(Path(preview).with_suffix(".urf")) if preview else f"/tmp/{job_name}.urf"
        Path(urf_path).write_bytes(data)
        print(f"dry run: wrote {urf_path}, nothing sent")
        return 0

    path, response = _try_attributes(args)
    if response is None:
        return 1
    attrs = response.attributes()
    supported = [value for value in attrs.get("document-format-supported", []) if isinstance(value, str)]
    preferred = attrs.get("document-format-preferred", [])
    candidates = []
    if preferred and isinstance(preferred[0], str):
        candidates.append(preferred[0])
    for value in supported:
        if value not in candidates:
            candidates.append(value)
    for value in ("image/urf", "application/octet-stream"):
        if value not in candidates:
            candidates.append(value)

    started_print = time.time()
    reply = None
    used_format = None
    for document_format in candidates:
        reply = ipp.print_job(
            args.host, data, path=path, document_format=document_format,
            job_name=job_name, copies=args.copies, user=args.user, **_clients(args))
        used_format = document_format
        if reply.ok:
            break
        if reply.status == 0x040A:
            continue  # format rejected, try the next one
        break

    if reply is None or not reply.ok:
        status = reply.status_name if reply else "no reply"
        print(f"job rejected: {status}")
        if reply is not None:
            for _tag, attrs_group in reply.groups:
                for tag, name, value in attrs_group:
                    if "unsupported" in name or name in ("status-message", "detailed-status-message"):
                        print(f"  {name}: {ipp._decode_text(value) if isinstance(value, bytes) else value}")
        return 1

    reply_attrs = reply.attributes()
    job_id = (reply_attrs.get("job-id") or ["?"])[0]
    job_uri = (reply_attrs.get("job-uri") or ["?"])[0]
    print(f"accepted: {reply.status_name}  format={used_format}  "
          f"job-id={job_id}  uri={job_uri}")

    if args.no_wait:
        return 0

    seen = {}

    def on_poll(status):
        key = (status.get("state"), status.get("queued"), status.get("reasons"))
        if key != seen.get("key"):
            seen["key"] = key
            state = status.get("state_name") or status.get("state")
            print(f"  [{time.time() - started_print:5.1f}s] state={state} "
                  f"queued={status.get('queued')} reasons={status.get('reasons')}")

    result = ipp.wait_for_idle(args.host, path, on_poll=on_poll, **_clients(args))
    elapsed = time.time() - started_print
    if result and result.get("state") == 3 and result.get("queued") in (0, None):
        print(f"done in {elapsed:.1f}s: printer is idle again")
        return 0
    print(f"submitted, but printer did not report idle within the wait window "
          f"({result}); check the device")
    return 0


def cmd_test_page(args) -> int:
    image = render.test_page(
        dpi=args.dpi, page_size=args.page_size, title=args.title,
        subtitle=args.subtitle, printer_label=args.printer_label,
        host=args.host, job_name=args.job_name or "")
    return _submit([image], args, dpi=args.dpi, page_size=args.page_size, source="test")


def cmd_print(args) -> int:
    path = Path(args.file)
    if not path.is_file():
        raise SystemExit(f"no such file: {args.file}")
    if path.suffix.lower() in (".txt", ".log", ".md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        images = render.text_pages(text, dpi=args.dpi, page_size=args.page_size,
                                   font_pt=args.font_pt, margin_mm=args.margin_mm,
                                   title=args.title)
    else:
        images = [render.image_page(path, dpi=args.dpi, page_size=args.page_size,
                                    scale=args.scale, margin_mm=args.margin_mm)]
    return _submit(images, args, dpi=args.dpi, page_size=args.page_size,
                   source=path.stem[:20])


def cmd_text(args) -> int:
    text = args.text_file and Path(args.text_file).read_text(encoding="utf-8", errors="replace")
    if args.words:
        text = (text + "\n\n" if text else "") + " ".join(args.words)
    if not text:
        print("nothing to print; pass words or --text-file")
        return 1
    images = render.text_pages(text, dpi=args.dpi, page_size=args.page_size,
                               font_pt=args.font_pt, margin_mm=args.margin_mm,
                               title=args.title)
    return _submit(images, args, dpi=args.dpi, page_size=args.page_size, source="text")


def cmd_encode(args) -> int:
    path = Path(args.file)
    if not path.is_file():
        raise SystemExit(f"no such file: {args.file}")
    image = render.image_page(path, dpi=args.dpi, page_size=args.page_size,
                              scale=args.scale, margin_mm=args.margin_mm)
    data = urf.encode_image(image, dpi=args.dpi)
    out = Path(args.out or path.with_suffix(".urf"))
    out.write_bytes(data)
    print(f"wrote {out} ({len(data) / 1024:.0f} KiB, {image.width}x{image.height} @ {args.dpi} dpi)")
    return 0


def cmd_decode(args) -> int:
    data = Path(args.file).read_bytes()
    pages = urf.decode(data)
    out = Path(args.out or Path(args.file).with_suffix(".png"))
    pages[0][0].save(out)
    print(f"decoded {len(pages)} page(s): {pages[0][0].size} @ {pages[0][1]} dpi -> {out}")
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="airprint", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    selftest = sub.add_parser("selftest", help="URF encode/decode round trip, no network")
    selftest.set_defaults(func=cmd_selftest)

    discover = sub.add_parser("discover", help="list AirPrint/IPP printers on the LAN")
    discover.add_argument("--timeout", type=float, default=4.0)
    _add_output(discover)
    discover.set_defaults(func=cmd_discover)

    probe = sub.add_parser("probe", help="ports + mDNS + WSD + IPP capabilities")
    _add_network(probe)
    probe.add_argument("--timeout", type=float, default=3.0)
    _add_output(probe)
    probe.set_defaults(func=cmd_probe)

    status = sub.add_parser("status", help="printer state, queue, media, ink")
    _add_network(status)
    _add_output(status)
    status.set_defaults(func=cmd_status)

    def add_print_options(parser_):
        _add_network(parser_)
        _add_output(parser_)
        parser_.add_argument("--dpi", type=int, default=600, choices=(300, 600))
        parser_.add_argument("--page-size", default="a4",
                             choices=sorted(render.PAGE_SIZES))
        parser_.add_argument("--copies", type=int, default=1)
        parser_.add_argument("--job-name", default=None)
        parser_.add_argument("--dry-run", action="store_true",
                             help="render and encode only; send nothing")
        parser_.add_argument("--no-wait", action="store_true",
                             help="do not poll until the printer is idle again")

    test_page = sub.add_parser("test-page", help="render and print a diagnostic page")
    add_print_options(test_page)
    test_page.add_argument("--title", default=None)
    test_page.add_argument("--subtitle", default=None)
    test_page.add_argument("--printer-label", default=None,
                           help="text shown in the Target row, e.g. 'Brother DCP-T436W @ 192.168.1.50'")
    test_page.set_defaults(func=cmd_test_page)

    print_cmd = sub.add_parser("print", help="print an image (or text) file")
    add_print_options(print_cmd)
    print_cmd.add_argument("file")
    print_cmd.add_argument("--scale", default="fit", choices=("fit", "fill", "none"))
    print_cmd.add_argument("--margin-mm", type=float, default=8.0)
    print_cmd.add_argument("--font-pt", type=float, default=11.0)
    print_cmd.add_argument("--title", default=None)
    print_cmd.set_defaults(func=cmd_print)

    text = sub.add_parser("text", help="render text and print it")
    add_print_options(text)
    text.add_argument("words", nargs="*")
    text.add_argument("--text-file", default=None)
    text.add_argument("--font-pt", type=float, default=11.0)
    text.add_argument("--margin-mm", type=float, default=15.0)
    text.add_argument("--title", default=None)
    text.set_defaults(func=cmd_text)

    encode = sub.add_parser("encode", help="image -> .urf (no network)")
    encode.add_argument("file")
    encode.add_argument("--out", default=None)
    encode.add_argument("--dpi", type=int, default=600, choices=(300, 600))
    encode.add_argument("--page-size", default="a4", choices=sorted(render.PAGE_SIZES))
    encode.add_argument("--scale", default="fit", choices=("fit", "fill", "none"))
    encode.add_argument("--margin-mm", type=float, default=8.0)
    encode.set_defaults(func=cmd_encode)

    decode = sub.add_parser("decode", help=".urf -> .png (inspection)")
    decode.add_argument("file")
    decode.add_argument("--out", default=None)
    decode.set_defaults(func=cmd_decode)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in ("discover", "probe") and not args.json:
        try:
            socket.gethostbyname(args.host) if getattr(args, "host", None) else None
        except OSError as exc:
            print(f"cannot resolve {args.host}: {exc}")
            return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
