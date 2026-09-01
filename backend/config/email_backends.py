"""A Django email backend that sends through Resend.

Django's own SMTP backend needs a mail server; this box has none, and Resend
is an HTTP API, so the backend is a thin adapter: Django keeps building
EmailMessage objects the ordinary way and `send_mail` / `EmailMessage.send()`
carry on working, which is what lets `send_cutting_digest` stay unaware of any
of this.

Configured entirely from the environment (see deploy/README.md):

    EMAIL_BACKEND=config.email_backends.ResendBackend
    RESEND_API_KEY=re_...
    DEFAULT_FROM_EMAIL=onboarding@resend.dev
"""
import logging

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class ResendBackend(BaseEmailBackend):
    """Send each message through the Resend API.

    One HTTP call per message. That is fine for a digest that runs once a day
    over a handful of recipients; it would not be for bulk mail, and Resend has
    a batch endpoint to move to if this ever becomes bulk mail.
    """

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, "RESEND_API_KEY", "") or ""

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            logger.error("RESEND_API_KEY is not set — no mail sent")
            if not self.fail_silently:
                raise ValueError("RESEND_API_KEY is not set")
            return 0

        import resend

        resend.api_key = self.api_key
        sent = 0
        for message in email_messages:
            try:
                resend.Emails.send(self._payload(message))
            except Exception:  # noqa: BLE001 — one bad address must not stop the rest
                logger.exception("resend: failed to send %r", message.subject)
                if not self.fail_silently:
                    raise
                continue
            sent += 1
        return sent

    def _payload(self, message) -> dict:
        recipients = list(message.to or [])
        payload = {
            "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
            "to": recipients,
            "subject": message.subject or "",
        }
        # Django says which one it built; Resend wants the matching key.
        body_key = "html" if message.content_subtype == "html" else "text"
        payload[body_key] = message.body or ""

        # Any alternative HTML part Django attached alongside the plain text.
        for content, mimetype in getattr(message, "alternatives", []) or []:
            if mimetype == "text/html":
                payload["html"] = content

        if message.cc:
            payload["cc"] = list(message.cc)
        if message.bcc:
            payload["bcc"] = list(message.bcc)
        if message.reply_to:
            payload["reply_to"] = list(message.reply_to)
        return payload
