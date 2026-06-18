"""
Email utility — sends emails via SMTP using Python's standard library.
Runs in a thread executor so it doesn't block the async event loop.
"""
from __future__ import annotations

import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from loguru import logger

from app.config import settings


def _send_smtp(to_email: str, subject: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.EMAIL_FROM, to_email, msg.as_string())


async def send_email(to_email: str, subject: str, html_body: str) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _send_smtp, to_email, subject, html_body)
    logger.info(f"[Email] Sent '{subject}' → {to_email}")


async def send_otp_email(to_email: str, full_name: str, otp: str) -> None:
    subject = "Your Password Reset OTP — JD Analyser"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto;">
        <h2 style="color: #2563eb;">Password Reset Request</h2>
        <p>Hi <strong>{full_name}</strong>,</p>
        <p>Use the OTP below to reset your password. It expires in
           <strong>{settings.OTP_EXPIRE_MINUTES} minutes</strong>.</p>
        <div style="
            font-size: 36px;
            font-weight: bold;
            letter-spacing: 10px;
            text-align: center;
            padding: 20px;
            background: #f1f5f9;
            border-radius: 8px;
            color: #1e293b;
            margin: 24px 0;
        ">{otp}</div>
        <p style="color: #64748b; font-size: 13px;">
            If you didn't request this, you can safely ignore this email.
            Do not share this OTP with anyone.
        </p>
    </div>
    """
    await send_email(to_email, subject, html_body)
