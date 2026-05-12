from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Templates for different events
TEMPLATES = {
    "booking_created": {
        "subject": "Booking Received: {reference}",
        "message": "Hello {name}, your booking from {pickup} to {dropoff} on {date} at {time} has been received. Reference: {reference}."
    },
    "booking_confirmed": {
        "subject": "Booking Confirmed: {reference}",
        "message": "Great news {name}! Your trip {reference} is confirmed. A driver will be assigned soon."
    },
    "driver_assigned": {
        "subject": "Driver Assigned: {reference}",
        "message": "Your driver {driver_name} has been assigned to trip {reference}. Vehicle: {vehicle}."
    },
    "payment_verified": {
        "subject": "Payment Verified: {reference}",
        "message": "Your payment for trip {reference} has been verified. Thank you!"
    },
    "cancellation_approved": {
        "subject": "Trip Cancelled: {reference}",
        "message": "Your trip {reference} has been successfully cancelled."
    }
}

def send_email_message(to_email: str, template_key: str, context: dict[str, Any]) -> bool:
    """
    Stub for sending email. Logs if provider not configured.
    """
    template = TEMPLATES.get(template_key)
    if not template:
        logger.error(f"Email template not found: {template_key}")
        return False

    subject = template["subject"].format(**context)
    body = template["message"].format(**context)

    # Check for real provider config here in future (e.g. SENDGRID_API_KEY)
    if not os.environ.get("SENDGRID_API_KEY") and not os.environ.get("SMTP_SERVER"):
        logger.info(f"[MESSAGING] Email Stub: To: {to_email} | Subject: {subject} | Body: {body}")
        return True

    # Real implementation would go here
    return True

def send_whatsapp_message(to_phone: str, template_key: str, context: dict[str, Any]) -> bool:
    """
    Stub for sending WhatsApp. Logs if provider not configured.
    """
    template = TEMPLATES.get(template_key)
    if not template:
        return False

    body = template["message"].format(**context)

    if not os.environ.get("TWILIO_WHATSAPP_SID"):
        logger.info(f"[MESSAGING] WhatsApp Stub: To: {to_phone} | Body: {body}")
        return True

    return True

def send_sms_message(to_phone: str, template_key: str, context: dict[str, Any]) -> bool:
    """
    Stub for sending SMS. Logs if provider not configured.
    """
    template = TEMPLATES.get(template_key)
    if not template:
        return False

    body = template["message"].format(**context)

    if not os.environ.get("TWILIO_SMS_SID"):
        logger.info(f"[MESSAGING] SMS Stub: To: {to_phone} | Body: {body}")
        return True

    return True
