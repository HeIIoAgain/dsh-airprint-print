# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 1.0.0 — 2026-11-03

First public release.

### Added

- IPP `Print-Job` client that speaks Apple Raster (URF) to AirPrint / Mopria
  printers, with no CUPS, driver, or root requirement.
- `discover`, `probe`, `status`, `test-page`, `print`, `text`, `encode`, and
  `decode` commands.
- Automatic format selection from `document-format-preferred` with fallback to
  other advertised formats, plus polling until the printer is idle.
- URF encoder/decoder with a built-in decode-and-compare verification step so a
  codec bug cannot silently waste paper.
- Implicit TLS / IPPS support with self-signed certificates.
- CJK rendering with a cached Noto Sans SC download fallback.
- DSH skill bundle (`SKILL.md` + references) and a standalone Python CLI from
  one code base.
- Reference documentation: URF format details, measured printer behavior
  (Brother DCP-T436W example), and a ports/WSD/LPD troubleshooting playbook.
- Self-test that exercises the codec with no network, plus GitHub Actions CI on
  Python 3.10 and 3.12.
