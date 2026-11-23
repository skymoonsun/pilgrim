"""Callback execution service — field mapping, HTTP dispatch, logging.

Delivery modes (mutually exclusive, chosen by ``field_mapping``):

* ``{"transform": "trust_scores"}`` — the whole result set is folded
  into the Trustpilot trust document (``app.services.trust_scores``):
  per-domain ``scores``, a ``failed`` list, and a ``crawled_at``
  timestamp.  The per-row field-mapping / static-fields / wrap-key
  machinery does not apply in this mode.
* otherwise — the classic per-row ``$.data.*`` field mapping below.

Header values that are exactly a ``{{ENV_NAME}}`` placeholder resolve
from ``os.environ`` at dispatch time; when the variable is unset or
empty the header is dropped (with a warning) — never a crash, and the
resolved secret is never logged.
"""

import logging
import os
import re
import time
from datetime import UTC, datetime, timezone
from typing import Any
from uuid import UUID

import httpx

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.callback_config import CallbackConfig
from app.models.callback_log import CallbackLog
from app.services.trust_scores import (
    build_trust_record,
    build_trust_scores,
    domain_from_review_url,
)

logger = logging.getLogger(__name__)

#: A header value that is *exactly* this shape (two opening braces, an
#: uppercase/underscore name, two closing braces) is an environment
#: placeholder, e.g. ``{{WEBHOOK_SECRET}}`` — stored literally in the
#: DB, resolved at callback dispatch.
_ENV_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_][A-Z0-9_]*)\}\}")

#: ``field_mapping["transform"]`` value that folds crawl results into a
#: trust document instead of running the per-row field mapping.
TRUST_SCORES_TRANSFORM = "trust_scores"


class CallbackService:
    """Execute webhook callbacks with field mapping and retry support."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Public API ───────────────────────────────────────────────

    async def execute_callback(
        self,
        callback_config: CallbackConfig,
        results: list[dict],
        metadata: dict | None = None,
    ) -> CallbackLog:
        """Apply field mapping to results and send HTTP request.

        Parameters
        ----------
        callback_config : CallbackConfig
            The webhook configuration with field_mapping.
        results : list[dict]
            Raw extraction results from CrawlJobResult payloads.
        metadata : dict, optional
            Schedule/job metadata (schedule_id, job_ids, timestamp).

        Returns
        -------
        CallbackLog
            The log entry for this callback attempt.
        """
        if not callback_config.is_active:
            logger.info("Callback %s is inactive — skipping", callback_config.id)
            return await self._log(
                callback_config,
                metadata,
                request_body=None,
                response_status=None,
                response_body="Callback inactive",
                success=False,
                error_message="Callback is inactive",
                duration_ms=0,
                attempt=0,
            )

        # Build payload
        payload = self._build_payload(callback_config, results, metadata)

        # Send with retries
        max_attempts = callback_config.retry_count + 1
        last_log: CallbackLog | None = None

        for attempt in range(1, max_attempts + 1):
            log = await self._send_request(
                callback_config, payload, metadata, attempt
            )
            last_log = log
            if log.success:
                break
            if attempt < max_attempts:
                import asyncio
                delay = callback_config.retry_delay_seconds * attempt
                logger.info(
                    "Callback attempt %d failed, retrying in %ds...",
                    attempt, delay,
                )
                await asyncio.sleep(delay)

        return last_log  # type: ignore[return-value]

    # ── Callback logs ────────────────────────────────────────────

    async def get_logs(
        self,
        schedule_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[CallbackLog]:
        from sqlalchemy import select

        result = await self.session.execute(
            select(CallbackLog)
            .where(CallbackLog.schedule_id == schedule_id)
            .order_by(CallbackLog.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars())

    # ── Field mapping engine ─────────────────────────────────────

    @staticmethod
    def _build_payload(
        config: CallbackConfig,
        results: list[dict],
        metadata: dict | None,
    ) -> dict[str, Any]:
        """Apply field_mapping to transform extraction results.

        The ``transform`` key and per-row mapping are mutually exclusive:
        when ``field_mapping["transform"] == "trust_scores"`` the whole
        result set is folded into one trust document (per-domain scores,
        ``failed``, ``crawled_at``) — static_fields, wrap_key and the
        per-row mapping are ignored.  For the classic mode the document
        assembly below applies unchanged.
        """
        mapping_spec = config.field_mapping or {}
        if mapping_spec.get("transform") == TRUST_SCORES_TRANSFORM:
            document = _build_trust_document(results)
            if config.batch_results:
                return {"results": document}
            return document

        field_map = mapping_spec.get("field_mapping", {})
        static_fields = mapping_spec.get("static_fields", {})
        wrap_key = mapping_spec.get("wrap_key")

        mapped_results = []
        for result in results:
            mapped = {}
            context = {
                "data": result.get("data", {}),
                "url": result.get("url", ""),
                "metadata": {
                    **(metadata or {}),
                    "http_status": result.get("http_status"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }

            for target_field, source_path in field_map.items():
                mapped[target_field] = _resolve_path(context, source_path)

            mapped_results.append(mapped)

        # Assemble final payload
        if config.batch_results:
            payload_data = mapped_results
        else:
            payload_data = mapped_results[0] if mapped_results else {}

        payload: dict[str, Any] = {}
        if wrap_key:
            payload[wrap_key] = payload_data
        else:
            if isinstance(payload_data, dict):
                payload = payload_data
            else:
                payload["results"] = payload_data

        # Add static fields
        payload.update(static_fields)

        # Add metadata if configured
        if config.include_metadata and metadata:
            payload["_metadata"] = metadata

        return payload

    # ── HTTP dispatch ────────────────────────────────────────────

    async def _send_request(
        self,
        config: CallbackConfig,
        payload: dict,
        metadata: dict | None,
        attempt: int,
    ) -> CallbackLog:
        """Send the HTTP request and log the result."""
        start = time.monotonic()
        response_status = None
        response_body = None
        success = False
        error_message = None

        try:
            headers = {"Content-Type": "application/json"}
            for header_name, header_value in (config.headers or {}).items():
                resolved = resolve_env_placeholder(header_value)
                if resolved is None:
                    # Placeholders with unset/empty env are dropped —
                    # the logged warning names the env var, never the
                    # resolved secret.
                    continue
                headers[header_name] = str(resolved)

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.request(
                    method=config.method.value,
                    url=config.url,
                    json=payload,
                    headers=headers,
                )
                response_status = resp.status_code
                response_body = resp.text[:2000]  # cap for storage
                success = 200 <= resp.status_code < 300

                if not success:
                    error_message = f"HTTP {resp.status_code}"

        except Exception as exc:
            error_message = str(exc)[:500]
            logger.error("Callback error: %s", exc)

        duration_ms = round((time.monotonic() - start) * 1000, 2)

        return await self._log(
            config, metadata, payload, response_status,
            response_body, success, error_message, duration_ms, attempt,
        )

    # ── Logging ──────────────────────────────────────────────────

    async def _log(
        self,
        config: CallbackConfig,
        metadata: dict | None,
        request_body: dict | None,
        response_status: int | None,
        response_body: str | None,
        success: bool,
        error_message: str | None,
        duration_ms: float,
        attempt: int,
    ) -> CallbackLog:
        log = CallbackLog(
            callback_config_id=config.id,
            schedule_id=config.schedule_id,
            crawl_job_id=(
                UUID(metadata["job_id"])
                if metadata and "job_id" in metadata
                else None
            ),
            request_url=config.url,
            request_method=config.method.value,
            request_body=request_body,
            response_status=response_status,
            response_body=response_body,
            success=success,
            error_message=error_message,
            duration_ms=duration_ms,
            attempt_number=attempt,
        )
        self.session.add(log)
        await self.session.commit()
        return log


# ── Trust-document transform ─────────────────────────────────────


def _build_trust_document(results: list[dict]) -> dict[str, Any]:
    """Fold per-job crawl results into one Trustpilot trust document.

    Rows whose ``url`` is a Trustpilot review URL are grouped by the
    seller domain embedded in the path; per domain the first *usable*
    extraction wins (an earlier unusable row — e.g. a blocked
    interstitial — never poisons the domain: a later row for the same
    URL supplies the numbers).  Domains with no usable row end up in the
    document's ``failed`` list; rows without a review URL cannot be
    keyed and are skipped.  The document gains the top-level
    ``crawled_at`` dispatch timestamp (UTC ISO).
    """
    rows_by_domain: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        domain = domain_from_review_url(str(result.get("url", "")))
        if domain is None:
            logger.debug("Callback result without a review URL — skipped")
            continue
        data = result.get("data")
        rows_by_domain.setdefault(domain, []).append(
            data if isinstance(data, dict) else {}
        )

    extracted_by_domain = {
        domain: _first_usable(domain, rows)
        for domain, rows in rows_by_domain.items()
    }

    document = build_trust_scores(extracted_by_domain)
    document["crawled_at"] = datetime.now(UTC).isoformat()
    return document


def _first_usable(
    domain: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """The first extraction row that yields a score (else the first row
    so ``build_trust_scores`` reports the domain under ``failed``)."""
    for row in rows:
        try:
            build_trust_record(domain, row)
        except ValueError:
            continue
        return row
    return rows[0]


# ── Env placeholders ─────────────────────────────────────────────


def resolve_env_placeholder(value: Any) -> Any:
    """Resolve a ``{{ENV_NAME}}`` header value from ``os.environ``.

    A value that is exactly a double-brace placeholder returns the
    environment value at dispatch time; when the variable is unset or
    empty the return is ``None`` and the caller must DROP the header
    (with a warning that names the env var — never the resolved secret).
    Any other value passes through unchanged.
    """
    if isinstance(value, str):
        if match := _ENV_PLACEHOLDER_RE.fullmatch(value):
            resolved = os.environ.get(match.group(1), "")
            if not resolved:
                logger.warning(
                    "Callback header placeholder %s: env unset or empty "
                    "— dropping header",
                    match.group(1),
                )
                return None
            return resolved
    return value


# ── Path resolver ────────────────────────────────────────────────


def _resolve_path(context: dict, path: str) -> Any:
    """Resolve a ``$.data.title``-style path against a context dict.

    Returns ``None`` if any segment is missing.
    """
    if not path.startswith("$."):
        return path  # literal value

    parts = path[2:].split(".")
    current: Any = context
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current
