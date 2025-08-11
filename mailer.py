"""Utility functions for email validation and delivery."""

from __future__ import annotations

import logging
import os
import re
from email.message import EmailMessage
import smtplib
from typing import Iterable, Tuple

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def invalid_emails(emails: Iterable[str]) -> list[str]:
    """Return a list of addresses that fail basic validation."""

    return [e for e in emails if not EMAIL_PATTERN.fullmatch(e)]


def send_email(
    to_addrs: Iterable[str] | str,
    subject: str,
    body: str,
    attachments: list[Tuple[str, bytes, str]],
) -> tuple[bool, str | None]:
    """Send an email with arbitrary attachments via SMTP."""

    server = os.getenv("SMTP_SERVER")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASSWORD")

    # Ensure environment variables are loaded if the caller hasn't already.
    if not (server and user and pwd):
        load_dotenv()
        server = server or os.getenv("SMTP_SERVER")
        user = user or os.getenv("SMTP_USER")
        pwd = pwd or os.getenv("SMTP_PASSWORD")

    if isinstance(to_addrs, str):
        to_addrs = [to_addrs]
    to_addrs = [e for e in to_addrs if e]

    if not to_addrs:
        err = "No recipients provided"
        logger.error(err)
        return False, err

    bad = invalid_emails(to_addrs)
    if bad:
        err = "Invalid email address: " + ", ".join(bad)
        logger.error(err)
        return False, err

    if not (server and user and pwd):
        missing = []
        if not server:
            missing.append("SMTP_SERVER")
        if not user:
            missing.append("SMTP_USER")
        if not pwd:
            missing.append("SMTP_PASSWORD")
        err = "Missing SMTP configuration: " + ", ".join(missing)
        logger.error(err + ": server=%s user=%s", server, user)
        return False, err

    msg = EmailMessage()
    msg["Subject"] = subject or "Report"
    msg["From"] = user
    msg["To"] = ", ".join(to_addrs)
    msg.set_content(body or "No significant insights")

    for name, data, mime in attachments:
        try:
            main, sub = mime.split("/", 1)
            msg.add_attachment(data, maintype=main, subtype=sub, filename=name)
        except Exception:
            continue

    try:
        use_ssl = os.getenv("SMTP_SSL", "0") == "1" or port == 465
        if use_ssl:
            with smtplib.SMTP_SSL(server, port) as s:
                s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(server, port) as s:
                s.starttls()
                s.login(user, pwd)
                s.send_message(msg)
        return True, None
    except Exception as e:
        logger.exception(
            "Failed to send email via %s:%s as %s", server, port, user
        )
        return False, str(e)


__all__ = ["send_email", "invalid_emails"]

