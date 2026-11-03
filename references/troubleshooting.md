# Troubleshooting: ports, paths and safe defaults

## Which path does a client use?

| Path | Ports | Used by | Notes |
|---|---|---|---|
| IPP / AirPrint | 631 (443 for IPPS) | iOS/macOS, this skill, CUPS driverless | Needs URF/PWG/JPEG, not PDF |
| WSD (WS-Print) | 80 or 5357 + UDP 3702 discovery | Windows "add device" | Check `XAddrs` from a WS-Discovery probe |
| LPD / LPR | 515 | Windows LPR port, some Unix tools | Legacy, unauthenticated; often disabled for security |
| RAW / JetDirect | 9100 | Brother's Windows driver default, POS software | Often closed; the most attack surface |
| EWS | 80 / 443 | browser admin, test pages, protocol toggles | Needs admin login (change the factory default before exposing EWS) |

`airprint.py probe` reports all of these, including mDNS TXT and WSD `XAddrs`.
A printer can print fine while 9100 **and** 515 are closed — that is the normal
hardened AirPrint setup.

## "Is the printer broken or is it my job?"

1. `airprint.py status --host H` — `printer-state` should be `idle`, `queued` 0,
   `reasons` `none`, `media-ready` matching the paper you send.
2. `airprint.py test-page --host H --dry-run --out /tmp/p.png` — open the PNG.
   If the page looks wrong, the bug is local (layout/font), not the printer.
3. `airprint.py selftest` — catches codec regressions with no printer involved.
4. Real print; watch the polling lines: `idle → processing → idle` is success.
5. Job accepted but stuck in `processing` → look at `printer-state-reasons`
   (`media-empty`, `cover-open`, `toner-empty`, `media-jam`) and the device
   panel. Nothing in the client can fix that.

## Windows clients (when the user asks "will printing still work?")

Ask first, then check on the Windows box:

```powershell
Get-Printer | Select-Object Name, PortName, DriverName
Get-PrinterPort | Format-Table Name, Description, PrinterHostAddress, PortNumber, Protocol
# Protocol 1 = RAW (9100), 2 = LPR (515)
```

- Port description `WSD Port` → uses WSD, unaffected by LPD/9100 changes.
- `Standard TCP/IP Port` + Protocol 1 → needs TCP 9100; if that is closed the
  queue is already broken (a common silent misconfiguration).
- Protocol 2 / `LPR Port` → needs TCP 515; closing LPD breaks it.
- `http://.../ipp/print` + "Microsoft IPP Class Driver" → IPP, unaffected.

Migrating a Windows queue to IPP:

```powershell
Add-Printer -Name "Printer" -IppURL "http://PRINTER_IP:631/ipp/print" `
            -DriverName "Microsoft IPP Class Driver"
```

LPR queue names on Brother devices: use the Bonjour TXT `rp` value, or the
documented fallback `BINARY_P1`.

## Security notes worth repeating to the user

- **Do not port-forward a printer to the internet.** 9100/631 scanners find
  them within hours; the result is unwanted pages and, on old firmware, worse.
- Prefer keeping printers and clients in an isolated VLAN / IoT network with no
  WAN ingress.
- **Enabling 9100 costs more than it gives**: it is unauthenticated, unencrypted,
  bypasses EWS access control and audit, and raw PDL/PJL parsing has a long CVE
  history (buffer overflows, PJL file/NVRAM access on some models). For an
  AirPrint printer the standard IPP path is also the more capable one (job
  attributes, status, cancel).
- LPD (515) is also unauthenticated and legacy; disable it when no client needs
  it, but verify Windows/Unix clients first (see above).
- EWS admin password should not be the factory default; IPP broadcasts carry no
  authentication at all on most home printers, so the network boundary is the
  real control.
- Self-signed TLS (IPPS 443) encrypts but does not authenticate the device.

## Guardrails for this skill

- Default to `--dry-run` while iterating; one real print = one sheet of paper
  plus ink.
- Never enable/disable printer services (9100, LPD, protocols) on the user's
  device as a troubleshooting step without explicit approval — changes there
  can break their Windows/mobile queues.
- Do not attempt EWS logins with guessed passwords.
- Report only what the remote channel proves (accepted, state transitions,
  job-id). Whether the sheet physically emerged is the user's observation.
