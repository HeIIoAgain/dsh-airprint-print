# Printer notes (measured, not guessed)

Re-run `airprint.py probe --host <ip>` / `status --host <ip>` to refresh this.

## Brother DCP-T436W @ 192.168.1.50

Inkjet MFP, firmware `1.16:DBD5`, AirPrint 2.1 / Mopria 2.2, self-signed cert
`CN=PrinterXXXXXXXXXX.local` (valid 2000–2110), Bonjour name
`PrinterXXXXXXXXXX.local`.

| Port | State | Notes |
|---|---|---|
| 80 | open | EWS (`/home/status.html`), WSD print service (`/WebServices/PrinterService`) |
| 443 | open | EWS over TLS, IPPS |
| 515 | open → **closed** after setup | LPD/LPR; was advertised as `_printer._tcp` until LPR was disabled on the device |
| 631 | open | IPP at `/ipp/print` (AirPrint) |
| 9100 | closed | raw/JetDirect disabled |

IPP capabilities:

- `document-format-supported = application/octet-stream` (only!), but
  `document-format-preferred = image/urf` — URF works and is what AirPrint sends.
- `urf-supported = SRGB24`, `RS300-600` → 24-bit RGB at 300 or 600 dpi.
- `operations-supported = 2` → **Print-Job only**: no job query, no cancel.
- Defaults: `iso_a4_210x297mm`, 600x600 dpi, color, one-sided.
- `printer-device-id`: `CMD:HBP,PJL,URF` — HBP (Brother host-based) is a
  proprietary driver format; don't go there, URF is open.
- mDNS TXT after LPR was disabled:
  `pdl=image/urf,image/jpeg,image/pwg-raster,application/vnd.brother-hbp`,
  `rp=ipp/print`, `URF=...`, `TLS=1.3`, `print_wfds=T`, `mopria-certified=2.2`,
  `priority=25`.
- WSD: WS-Discovery answers on UDP 3702 with
  `XAddrs=http://192.168.1.50:80/WebServices/Device`, types
  `wsdp:Device wprt:PrintDeviceType wscn:ScanDeviceType`. WSD print therefore
  runs over **port 80**, not 5357 (TCP 5357 is closed on this device).

Firmware quirks (do not "fix" them in the client):

- Every attribute group is returned **twice**; the decoder de-duplicates.
- Strings are language-tagged (`u16 lang-len, lang, u16 text-len, text`, e.g.
  `\x00\x02en\x00\x11Brother DCP-T436W`) and sent with the *collection* tags
  `0x35`/`0x36` instead of the proper text/name tags. `ipp.py` handles it.
- `Get-Job-Attributes` is unsupported → wait for `printer-state = idle` and
  `queued-job-count = 0` instead.
- Print-Job replies `successful-ok-ignored-or-substituted-attributes` even on
  success; treat that status as OK (the tool does).

Timings observed (A4, 600 dpi, 0.7–0.9 MB URF): ~25–35 s from submission to
idle again. A4 rasters are 4961x7016 px.

## Adding a new printer

1. `airprint.py probe --host <ip>` — record ports, `pdl`/`URF` TXT, formats.
2. `airprint.py test-page --host <ip> --dry-run` then check the PNG.
3. Real print once, time it, note quirks (duplicate groups, odd tags, extra
   attributes) here.
4. If the printer only speaks JPEG (`pdl=image/jpeg` but no URF), the same
   `Print-Job` path works with `document-format=image/jpeg` and a JPEG body —
   the CLI currently only emits URF; extend `_submit` if that comes up.
