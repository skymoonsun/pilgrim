"""Email notification service — build content, send via SMTP, log results."""

import logging
import re
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any
from uuid import UUID

import aiosmtplib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.email_notification_config import EmailNotificationConfig
from app.models.email_notification_log import EmailNotificationLog
from app.services.callback_service import _resolve_path

logger = logging.getLogger(__name__)

# ── Default HTML template ────────────────────────────────────────

_DEFAULT_SUBJECT = "Pilgrim: {{schedule_name}} completed"

_DEFAULT_BODY_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head><style>
  body {{ font-family: Arial, sans-serif; color: #333; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
  th {{ background-color: #f5f5f5; }}
  .meta {{ margin-top: 16px; font-size: 0.85rem; color: #666; }}
  .status-success {{ color: #22c55e; }}
  .status-failure {{ color: #ef4444; }}
</style></head>
<body>
<h2>Crawl Results</h2>
<p>Schedule: {schedule_name}</p>
<table>
<thead><tr><th>URL</th><th>Status</th><th>Data</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
{metadata_section}
<p>Completed at: {timestamp}</p>
</body>
</html>
"""

_FAILURE_BODY_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head><style>
  body {{ font-family: Arial, sans-serif; color: #333; }}
  .error {{ color: #ef4444; }}
  .meta {{ margin-top: 16px; font-size: 0.85rem; color: #666; }}
</style></head>
<body>
<h2 class="error">Crawl Failed</h2>
<p>Schedule: {schedule_name}</p>
<p>URL: {target_url}</p>
<p>Error: {error_message}</p>
{metadata_section}
<p>Time: {timestamp}</p>
</body>
</html>
"""


class EmailNotificationService:
    """Build email content from extraction results and send via SMTP."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Public API ───────────────────────────────────────────────

    async def execute_notification(
        self,
        config: EmailNotificationConfig,
        results: list[dict],
        metadata: dict | None,
        trigger_reason: str,
    ) -> EmailNotificationLog:
        """Apply field mapping, build HTML email, send via SMTP, log result.

        Parameters
        ----------
        config : EmailNotificationConfig
            The email notification configuration.
        results : list[dict]
            Raw extraction results from CrawlJobResult payloads.
        metadata : dict, optional
            Schedule/job metadata (schedule_id, job_ids, timestamp).
        trigger_reason : str
            "success" or "failure" — controls subject and body template.
        """
        if not config.is_active:
            logger.info("EmailNotification %s is inactive — skipping", config.id)
            return await self._log(
                config, metadata,
                recipients=config.recipient_emails,
                subject="(inactive)",
                trigger_reason=trigger_reason,
                body_html=None,
                success=False,
                error_message="Email notification is inactive",
                smtp_response_code=None,
                duration_ms=0,
                attempt=0,
            )

        # Build subject and body
        subject = self._build_email_subject(config, metadata)
        body_html = self._build_email_body(config, results, metadata, trigger_reason)
        recipients: list[str] = config.recipient_emails

        # Send with retries (simple retry, no backoff for now)
        max_attempts = 2
        last_log: EmailNotificationLog | None = None

        for attempt in range(1, max_attempts + 1):
            success, smtp_code, error_msg, duration = await self._send_email(
                recipients, subject, body_html,
            )
            log = await self._log(
                config, metadata,
                recipients=recipients,
                subject=subject,
                trigger_reason=trigger_reason,
                body_html=body_html[:5000] if body_html else None,
                success=success,
                error_message=error_msg,
                smtp_response_code=smtp_code,
                duration_ms=duration,
                attempt=attempt,
            )
            last_log = log
            if success:
                break
            if attempt < max_attempts:
                import asyncio
                await asyncio.sleep(5 * attempt)

        return last_log  # type: ignore[return-value]

    # ── Log queries ────────────────────────────────────────────────

    async def get_logs(
        self,
        schedule_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[EmailNotificationLog]:
        result = await self.session.execute(
            select(EmailNotificationLog)
            .where(EmailNotificationLog.schedule_id == schedule_id)
            .order_by(EmailNotificationLog.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars())

    # ── Content building ──────────────────────────────────────────

    @staticmethod
    def _build_email_subject(
        config: EmailNotificationConfig,
        metadata: dict | None,
    ) -> str:
        """Render subject_template with {{var}} placeholders."""
        template = config.subject_template or _DEFAULT_SUBJECT
        context = metadata or {}

        def _replace(match: re.Match) -> str:
            key = match.group(1)
            value = context.get(key, "")
            return str(value)

        return re.sub(r"\{\{(\w+)\}\}", _replace, template)

    @staticmethod
    def _build_email_body(
        config: EmailNotificationConfig,
        results: list[dict],
        metadata: dict | None,
        trigger_reason: str,
    ) -> str:
        """Build HTML email body from results.

        If field_mapping is configured, applies it using _resolve_path()
        (same engine as CallbackService) and renders mapped data.
        Otherwise, uses default templates.
        """
        schedule_name = (metadata or {}).get("schedule_name", "Unknown")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        metadata_section = ""
        if config.include_metadata and metadata:
            meta_items = "".join(
                f"<li><strong>{k}</strong>: {v}</li>"
                for k, v in metadata.items()
            )
            metadata_section = f'<div class="meta"><ul>{meta_items}</ul></div>'

        if trigger_reason == "failure":
            target_url = (metadata or {}).get("target_url", "N/A")
            error_message = (metadata or {}).get("error_message", "Unknown error")
            return _FAILURE_BODY_TEMPLATE.format(
                schedule_name=schedule_name,
                target_url=target_url,
                error_message=error_message,
                metadata_section=metadata_section,
                timestamp=timestamp,
            )

        # Success path
        mapping_spec = config.field_mapping or {}
        field_map = mapping_spec.get("field_mapping", {})
        static_fields = mapping_spec.get("static_fields", {})
        wrap_key = mapping_spec.get("wrap_key")

        if field_map:
            # Use field_mapping to transform results
            mapped_results = []
            for result in results:
                context = {
                    "data": result.get("data", {}),
                    "url": result.get("url", ""),
                    "metadata": {
                        **(metadata or {}),
                        "http_status": result.get("http_status"),
                        "timestamp": timestamp,
                    },
                }
                mapped = {}
                for target_field, source_path in field_map.items():
                    mapped[target_field] = _resolve_path(context, source_path)
                mapped_results.append(mapped)

            rows = ""
            for item in mapped_results:
                cells = "".join(
                    f"<td>{item.get(k, '')}</td>" for k in item
                )
                rows += f"<tr>{cells}</tr>"

            headers = "".join(
                f"<th>{k}</th>" for k in (mapped_results[0].keys() if mapped_results else [])
            )
            table_html = f"<table><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table>"

            if static_fields:
                static_items = "".join(
                    f"<li><strong>{k}</strong>: {v}</li>"
                    for k, v in static_fields.items()
                )
                table_html += f'<div class="meta"><ul>{static_items}</ul></div>'

            return _DEFAULT_BODY_TEMPLATE.format(
                schedule_name=schedule_name,
                rows=f"<tr><td colspan='3'>No results</td></tr>" if not mapped_results else rows,
                metadata_section=metadata_section,
                timestamp=timestamp,
            ).replace(
                "<table>\n<thead><tr><th>URL</th><th>Status</th><th>Data</th></tr></thead>\n<tbody>\n{rows}\n</tbody>\n</table>",
                table_html,
            )

        # No field_mapping — use default template with raw results
        rows = ""
        for result in results:
            url = result.get("url", "—")
            http_status = result.get("http_status", "—")
            data = result.get("data", {})
            data_str = (
                ", ".join(f"{k}: {v}" for k, v in data.items())
                if isinstance(data, dict) else str(data)
            )
            rows += f"<tr><td>{url}</td><td>{http_status}</td><td>{data_str}</td></tr>"

        if not results:
            rows = "<tr><td colspan='3'>No results</td></tr>"

        return _DEFAULT_BODY_TEMPLATE.format(
            schedule_name=schedule_name,
            rows=rows,
            metadata_section=metadata_section,
            timestamp=timestamp,
        )

    # ── SMTP dispatch ──────────────────────────────────────────────

    async def _send_email(
        self,
        recipients: list[str],
        subject: str,
        body_html: str,
    ) -> tuple[bool, int | None, str | None, float]:
        """Send email via aiosmtplib.

        Returns (success, smtp_response_code, error_message, duration_ms).
        """
        settings = get_settings()
        start = time.monotonic()

        msg = EmailMessage()
        msg["From"] = settings.smtp_from_address
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg.set_content(body_html, subtype="html")

        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_username,
                password=settings.smtp_password,
                start_tls=settings.smtp_use_tls,
            )
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            logger.info("Email sent to %s: %s", recipients, subject)
            return True, 250, None, duration_ms

        except aiosmtplib.SMTPResponseException as exc:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            error_msg = f"SMTP {exc.code}: {exc.message}"
            logger.error("SMTP error sending email: %s", error_msg)
            return False, exc.code, error_msg, duration_ms

        except Exception as exc:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            error_msg = str(exc)[:500]
            logger.error("Email send error: %s", exc)
            return False, None, error_msg, duration_ms

    # ── Logging ────────────────────────────────────────────────────

    async def _log(
        self,
        config: EmailNotificationConfig,
        metadata: dict | None,
        recipients: list[str],
        subject: str,
        trigger_reason: str,
        body_html: str | None,
        success: bool,
        error_message: str | None,
        smtp_response_code: int | None,
        duration_ms: float,
        attempt: int,
    ) -> EmailNotificationLog:
        log = EmailNotificationLog(
            email_notification_config_id=config.id,
            schedule_id=config.schedule_id,
            crawl_job_id=(
                UUID(metadata["job_id"])
                if metadata and "job_id" in metadata
                else None
            ),
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            trigger_reason=trigger_reason,
            success=success,
            error_message=error_message,
            smtp_response_code=smtp_response_code,
            duration_ms=duration_ms,
            attempt_number=attempt,
        )
        self.session.add(log)
        await self.session.commit()
        return log