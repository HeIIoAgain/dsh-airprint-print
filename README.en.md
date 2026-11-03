# dsh-airprint-print

English | [简体中文](README.md)

Print to AirPrint / Mopria printers **without CUPS, without a driver, without root**. This tool renders a page to an **Apple Raster (URF)** bitmap and submits it through IPP `Print-Job`.

It targets a very common class of cheap network printers: only IPP 631 is open, `document-format-supported = application/octet-stream`, `document-format-preferred = image/urf`, **no PDF support**, and raw port 9100 closed. The only payload those devices accept is URF, and this tool handles the whole chain: probe → render → encode → submit → wait.

Two ways to use it:

- **As a DSH skill**: drop it into `~/.dsh/skills/` and tell the agent "print this image".
- **As a standalone Python CLI**: works on any machine, DSH not required.

## Features

| Command | Purpose |
|---|---|
| `selftest` | URF encode/decode round trip, no network |
| `discover` | Find AirPrint printers via mDNS |
| `probe --host H` | Ports, mDNS TXT, WS-Discovery, IPP capabilities |
| `status --host H` | State, queue, media, supplies |
| `test-page --host H` | Render and print a diagnostic page |
| `print --host H FILE` | Print an image (png/jpg/webp…) |
| `text --host H TEXT` | Render text and print it (CJK supported) |
| `encode / decode` | Image ↔ URF conversion, fully local |

- Automatically prefers the printer's `document-format-preferred`, falls back to other advertised formats
- Polls until `idle` with an empty queue, then reports the job id and elapsed time
- Decodes its own URF and compares it to the source image; refuses to print on mismatch
- IPPS support (`--tls`, self-signed certificates accepted)
- CJK text uses a system font; if absent, Noto Sans SC is downloaded once to `~/.cache/dsh-airprint/fonts/` (≈8 MB)

## Install

### Option A — DSH skill (recommended)

```sh
git clone https://github.com/HeIIoAgain/dsh-airprint-print.git ~/.dsh/skills/airprint-print
```

The DSH filesystem skill provider watches `~/.dsh/skills/`, so the skill is discovered as soon as the clone finishes; a new session can use it. The target directory must be named `airprint-print` (matching `SKILL.md`'s `name`); back up an existing directory first.

Dependencies:

```sh
pip3 install --user pillow numpy   # numpy is optional and only speeds up encoding
```

### Option B — standalone CLI

```sh
git clone https://github.com/HeIIoAgain/dsh-airprint-print.git
cd dsh-airprint-print
pip3 install -r requirements.txt
python3 scripts/airprint.py selftest
```

Requires Python ≥ 3.10 and Pillow; numpy optional.

## Quick start

```sh
# 1. self-test (no network)
python3 scripts/airprint.py selftest

# 2. find printers, or probe a known host
python3 scripts/airprint.py discover
python3 scripts/airprint.py probe --host 192.168.1.50

# 3. dry-run first: render and save PNG/URF, consume no paper
python3 scripts/airprint.py test-page --host 192.168.1.50 --dry-run --out /tmp/page.png
python3 scripts/airprint.py test-page --host 192.168.1.50

# 4. print an image or text
python3 scripts/airprint.py print --host 192.168.1.50 photo.jpg --page-size 4x6
python3 scripts/airprint.py text  --host 192.168.1.50 "hello from the LAN" --title "Note"
```

When layout matters, always run `--dry-run` first: it writes the rendered PNG and the exact `.urf` bytes so you can inspect alignment and CJK glyphs without using paper.

As a DSH skill you do not type these commands: ask the agent to "print this", "test the printer", or "why won't this printer print", and it follows the workflow in [`SKILL.md`](SKILL.md).

## How it works

1. **Probe**: read `document-format-supported/preferred`, `urf-supported`, `media-ready` from IPP 631; optionally inspect mDNS TXT, WS-Discovery, and ports 80/443/515/9100.
2. **Render**: Pillow produces an RGB bitmap for `--page-size` at `--dpi`.
3. **Encode**: pack the bitmap into URF (PackBits + line headers), then immediately decode and compare against the source image so an encoder bug cannot waste paper.
4. **Submit**: IPP `Print-Job`, then wait for `printer-state = idle` and `queued-job-count = 0`.

## Limits

- **One sheet per print**; there is no simulated printing.
- This class of printer usually implements only `Print-Job` (`operations-supported = 2`): no job query, no cancel. Once submitted, it runs.
- Media must match the loaded paper; `status` reports `media-ready`.
- TLS uses the printer's self-signed certificate; the tool does not verify it.
- The remote channel only proves "accepted and back to idle"; **only a human can confirm the sheet physically came out**.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `client-error-document-format-not-supported` (0x040A) | Wrong payload; try the other format, confirm `urf-supported`, re-read `references/urf-format.md` |
| `client-error-not-found` (0x0406) | Wrong `--path`; try `/ipp` or `/` |
| `server-error-not-accepting-jobs` (0x0506) | Printer busy/paused/out of paper; run `status` first |
| 631 closed but 80 open | Likely WSD/EWS only; see `references/troubleshooting.md` |
| Job stays `processing` | Out of paper, cover open, ink error; check `printer-state-reasons` |
| Prints garbage | Encoder/format bug; run `selftest`, compare with `references/urf-format.md` |

Full playbook in [`references/troubleshooting.md`](references/troubleshooting.md); measured device behavior in [`references/printer-notes.md`](references/printer-notes.md).

## Security notes

- Do not port-forward printer ports 631/9100 to the internet; scanners find them within hours.
- Keep printers on an isolated VLAN / IoT network with no WAN ingress.
- Do not toggle device services (9100, LPD, protocols) as a troubleshooting step without approval — it can break existing Windows/mobile queues.
- Do not try EWS logins with guessed passwords; change factory defaults.
- Iterate with `--dry-run`; one real print costs a sheet of paper and ink.

## Layout

```
.
├── SKILL.md                  # DSH model-facing entry (frontmatter + workflow)
├── scripts/
│   ├── airprint.py           # CLI: commands, rendering, submit, polling
│   ├── ipp.py                # IPP wire protocol (encode/decode, Print-Job, status)
│   ├── urf.py                # Apple Raster codec (with optional numpy fast path)
│   ├── render.py             # page rendering, fonts, CJK fallback
│   └── netprobe.py           # mDNS / WS-Discovery / port probing
└── references/
    ├── urf-format.md         # URF container, PackBits dialects, gotchas
    ├── printer-notes.md      # measured device facts (example: Brother DCP-T436W)
    └── troubleshooting.md    # ports, WSD/LPD, safe defaults
```

## Development

```sh
python3 -m compileall -q scripts     # syntax check
python3 scripts/airprint.py selftest # codec round trip, no network
```

CI (GitHub Actions) runs the same checks on Python 3.10 and 3.12 with no printer or network required. Real printing can only be verified on a LAN with a printer.

## License

[MIT](LICENSE)
