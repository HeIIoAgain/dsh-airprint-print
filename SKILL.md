---
name: airprint-print
description: Use when printing something (a test page, an image, or generated text) on a network printer, especially AirPrint/Mopria printers that reject PDF and only accept Apple Raster (URF); also for finding printers on the LAN, reading printer state/ink, and diagnosing why a print job fails. Covers IPP probing, page rendering, URF encoding, job submission and status verification.
whenToUse: The user asks to print, wants a printer tested, gives a printer IP/hostname, or a print job must be produced from this machine. Also when a printer only exposes IPP 631 with document-format-preferred=image/urf and raw port 9100 is closed.
---

# Printing to AirPrint / IPP printers (no CUPS, no driver)

Cheap network printers (Brother/HP/Canon/Epson inkjets, MFPs) usually expose
**IPP on 631** but **no PDF support**: `document-format-supported =
application/octet-stream`, `document-format-preferred = image/urf`, raw port
9100 closed. The only payload they accept is an **Apple Raster (URF)** bitmap.
This skill renders a page with Pillow, encodes URF, and POSTs it as an IPP
`Print-Job` — no CUPS, no root, no printer driver.

## Quick start

`$SKILL_DIR` is the base directory reported by the `skill` tool; scripts live in
`$SKILL_DIR/scripts/`.

```bash
# 0. dependencies (once; numpy only speeds up encoding)
pip3 install --break-system-packages --user pillow numpy

# 1. self-test, touches no network
python3 $SKILL_DIR/scripts/airprint.py selftest

# 2. find printers, or probe a known one
python3 $SKILL_DIR/scripts/airprint.py discover
python3 $SKILL_DIR/scripts/airprint.py probe --host 192.168.1.50

# 3. render first, print second (--dry-run writes PNG + .urf, sends nothing)
python3 $SKILL_DIR/scripts/airprint.py test-page --host 192.168.1.50 --dry-run --out /tmp/page.png
python3 $SKILL_DIR/scripts/airprint.py test-page --host 192.168.1.50

# 4. print an image, or text
python3 $SKILL_DIR/scripts/airprint.py print --host 192.168.1.50 photo.jpg --page-size 4x6
python3 $SKILL_DIR/scripts/airprint.py text  --host 192.168.1.50 "hello from the LAN" --title "Note"
```

Always run the `--dry-run` variant first when the layout matters: it saves the
rendered PNG (open it with the image reader and check alignment/CJK glyphs) and
the exact `.urf` bytes, without consuming paper.

## Workflow

1. **Resolve the target.** Known IP → `probe --host`. Unknown → `discover`
   (mDNS `_ipp._tcp`), or ask the user. `probe` prints TCP ports, mDNS TXT
   (`pdl`, `URF`, `rp`), WS-Discovery, and the IPP capability summary.
2. **Confirm the payload format.** If `document-format-supported` lists
   `image/urf` or `application/octet-stream` (and `pdf-versions-supported =
   none`), URF is the way. Read `references/urf-format.md` before touching the
   encoder; the format has three non-obvious rules.
3. **Render.** `test-page` for a diagnostic page; `print FILE` for an image
   (`--scale fit|fill|none`, `--page-size`, `--dpi 300|600`); `text` for strings
   or a text file. A4 is the usual default; ask the user if the tray holds
   something else (`status` shows `media-ready`).
4. **Encode + verify.** `airprint.py` always decodes its own URF and compares it
   with the source image; it refuses to print if they differ. To check by hand:
   `encode FILE --out x.urf` then `decode x.urf --out x.png`.
5. **Submit and wait.** The tool submits with `Print-Job`, prefers the printer's
   `document-format-preferred`, falls back to other advertised formats, then
   polls until the printer is idle with an empty queue. A page typically takes
   20–40 s on an inkjet; report the job-id and elapsed time.
6. **Report honestly.** Accepted + returned to idle is the remote evidence
   available. Only the user can confirm the sheet physically came out; say so
   instead of claiming a visual check.

## Facts and limits

- **One sheet per print.** There is no simulated printing.
- **No cancel on this class of printer.** Many only implement `Print-Job`
  (`operations-supported = 2`) — no `Get-Job-Attributes`, no `Cancel-Job`.
  Once submitted, the job runs. Keep the page small while experimenting.
- **Media mismatch matters.** Send a raster whose pixel size matches the loaded
  paper (the tool sizes pages from `--page-size`); `status` shows `media-ready`.
- **`image/urf` vs `application/octet-stream`.** Both are tried automatically;
  some firmwares advertise only the latter but print URF fine.
- **TLS (`--tls`, IPPS 443) usually works** because the printer advertises
  `_ipps._tcp`, but certificates are self-signed; the tool does not verify them.

## Failure playbook

| Symptom | Likely cause / fix |
|---|---|
| `client-error-document-format-not-supported` (0x040A) | Wrong payload; try the other format, confirm `urf-supported` exists, re-check `references/urf-format.md` |
| `client-error-not-found` (0x0406) | Wrong `--path`; try `/ipp`, or `/` |
| `server-error-not-accepting-jobs` (0x0506) | Printer busy/paused/out of paper; `status` first |
| HTTP 400/404 from `/ipp/print` | Not an IPP endpoint; `probe` |
| Port 631 closed but 80 open | Try WSD/EWS path; see `references/troubleshooting.md` |
| Job accepted but state stays `processing` | Out of paper, cover open, ink error; check `printer-state-reasons` and the device panel |
| Everything works but URF prints garbage | Encoder/format bug — run `selftest`, compare with `references/urf-format.md` |

## Reference files

| File | Contents |
|---|---|
| `references/urf-format.md` | URF container layout, PackBits dialects, encoding rules, known-good sample |
| `references/printer-notes.md` | Measured facts about printers this skill has driven (e.g. a Brother DCP-T436W), quirks and timings |
| `references/troubleshooting.md` | Ports, WSD/LPD/Windows paths, security notes, safe-kill switches, when to stop |

## Maintenance

- Scripts: `scripts/airprint.py` (CLI), `ipp.py` (wire protocol), `urf.py`
  (codec), `render.py` (pages/fonts), `netprobe.py` (mDNS/WSD/ports).
- Chinese text works when a CJK font exists; otherwise the first page that needs
  one downloads Noto Sans SC into `~/.cache/dsh-airprint/fonts/` (≈8 MB).
- `python3 scripts/airprint.py --help` and `<command> --help` list every flag.
- This skill writes no configuration and touches nothing outside `/tmp` and
  `~/.cache/dsh-airprint/`; jobs themselves are the only external effect.
