# Security policy

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue for an unfixed
vulnerability.

- Use GitHub's [private vulnerability reporting](https://github.com/muhammadmishbakhuzzuhail/transdoc/security/advisories/new)
  (Security → Report a vulnerability), or
- email the maintainer (see the address in [CITATION.cff](CITATION.cff) / the commit history).

Please include: affected version/commit, a description, reproduction steps or a proof-of-concept,
and the impact you observed. You'll get an acknowledgement as soon as possible; please allow a
reasonable window for a fix before any public disclosure.

## Supported versions

This is a young project; only the latest `main` (and the most recent tagged release) receives
security fixes.

| Version | Supported |
|---------|-----------|
| `main` / latest release | ✅ |
| older | ❌ |

## Scope & deployment notes

transdoc accepts **arbitrary uploaded documents** and runs OCR, LibreOffice and (optionally) local
ML models over them. The threat model differs sharply by deployment:

- **Localhost, single-user (default).** The server binds `127.0.0.1` and has no authentication by
  design. This is the supported posture for the CLI/desktop use case.
- **Exposed service (e.g. the Docker image, which binds `0.0.0.0`).** There is **no built-in
  authentication or rate-limiting**. If you expose transdoc on a network you **must** place it
  behind an authenticating reverse proxy (and ideally rate-limiting + an egress allowlist). The
  container runs as a non-root user and ships a healthcheck, but it is not a multi-tenant service.

Job ids are unguessable 128-bit tokens and act as bearer secrets for `/api/download`, `/api/jobs`
and `/api/preview`; treat URLs containing them as sensitive.

Input hardening already in place: file-size / page-count / decompression-bomb caps, streaming
upload limits, zip-bomb checks, formula-injection neutralisation on CSV/XLSX export, hardened XML
(defusedxml) on TMX import, and argv-list subprocess calls (no shell) with resource limits.
