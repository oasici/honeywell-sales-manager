"""Round-18 inbound antivirus scan hook.

The whitelist + size caps land in ``email_attachment_parser`` keep
exotic bytes out of the parsing pipeline, but they do nothing
about Excel macros sneaked through ``.xlsx`` (rare — ``keep_vba=
False`` strips them at parse time, but the bytes are still in
``raw_attachments``) or PDFs with embedded JavaScript.

This module defines the scanner *interface* and a no-op default
implementation. Ops plugs in the real backend via env var:

    AV_SCAN_BACKEND=clamav     # local clamd daemon
    AV_SCAN_BACKEND=virustotal # hash-based VT API lookup
    AV_SCAN_BACKEND=none       # default — pass everything

The interface returns a verdict per attachment:

    "clean"        — scan ran, no detection
    "infected"     — scan ran, malware detected (``details``
                     populated)
    "unscanned"    — scan skipped (backend unavailable, file too
                     large for the chosen scanner, etc.)

Pre-Round-18 there was no scan at all, so even the "unscanned"
default is a meaningful upgrade — the column lands on the email
row so ops can audit what was actually checked.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AvVerdict:
    """One scan result per attachment."""

    filename: str
    status: str  # "clean" | "infected" | "unscanned"
    backend: str = "none"
    details: str | None = None


class AvScanner(Protocol):
    """Plug-in interface for AV backends."""

    name: str

    def scan(self, filename: str, data: bytes) -> AvVerdict: ...


class _NoopScanner:
    """Default backend — returns ``unscanned`` for every attachment.

    Documents the intent ("we checked, but no real scanner was
    wired") and keeps the column non-null so downstream queries
    can ``WHERE av_status != 'clean'`` without surprises.
    """

    name = "none"

    def scan(self, filename: str, data: bytes) -> AvVerdict:
        return AvVerdict(filename=filename, status="unscanned", backend=self.name)


class _ClamavScanner:
    """ClamAV local daemon backend.

    Connects to ``clamd`` on ``CLAMAV_HOST:CLAMAV_PORT`` (defaults
    ``localhost:3310``). Uses INSTREAM so bytes never touch disk.
    Failure modes (daemon unreachable, scan timeout) downgrade to
    ``unscanned`` rather than refusing the attachment — same policy
    as the rest of the email pipeline.
    """

    name = "clamav"

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port

    def scan(self, filename: str, data: bytes) -> AvVerdict:
        try:
            import clamd  # type: ignore[import-untyped]
        except ImportError:
            return AvVerdict(
                filename=filename,
                status="unscanned",
                backend=self.name,
                details="clamd-py not installed",
            )
        try:
            cd = clamd.ClamdNetworkSocket(host=self._host, port=self._port)
            import io as _io

            result = cd.instream(_io.BytesIO(data))
        except Exception as exc:  # noqa: BLE001
            logger.warning("ClamAV scan failed for %s: %s", filename, exc)
            return AvVerdict(
                filename=filename,
                status="unscanned",
                backend=self.name,
                details=f"clamd error: {exc}",
            )
        # clamd.instream returns {"stream": ("OK"|"FOUND", details)}
        verdict = (result or {}).get("stream", ("UNKNOWN", ""))
        if verdict[0] == "OK":
            return AvVerdict(filename=filename, status="clean", backend=self.name)
        if verdict[0] == "FOUND":
            return AvVerdict(
                filename=filename,
                status="infected",
                backend=self.name,
                details=str(verdict[1] or ""),
            )
        return AvVerdict(
            filename=filename,
            status="unscanned",
            backend=self.name,
            details=f"unexpected verdict: {verdict}",
        )


def get_scanner() -> AvScanner:
    """Resolve the configured backend at call time.

    Looked up per-call rather than at import time so tests can flip
    ``AV_SCAN_BACKEND`` without resetting the module. The cost is
    negligible — env-var lookup + a single constructor call.
    """
    backend = (os.environ.get("AV_SCAN_BACKEND") or "none").lower()
    if backend == "clamav":
        host = os.environ.get("CLAMAV_HOST", "localhost")
        port = int(os.environ.get("CLAMAV_PORT", "3310"))
        return _ClamavScanner(host=host, port=port)
    # VirusTotal-by-hash is intentionally **not** auto-wired:
    # uploading customer-attachment bytes to a third-party scanner
    # is a privacy regression unless the operator opts in. Leave a
    # TODO breadcrumb for a future plug-in.
    return _NoopScanner()


def scan_attachments(
    attachments: list[tuple[str, bytes]],
) -> list[AvVerdict]:
    """Scan each ``(filename, bytes)`` tuple via the active backend.

    The verdicts are surfaced to the email_processing_service so
    ``AvVerdict.status == "infected"`` flips the email to review
    queue and the attachment text is *not* fed to Claude (avoids
    re-encoding malicious payloads into LLM context).
    """
    scanner = get_scanner()
    return [scanner.scan(fn, data) for fn, data in attachments]
