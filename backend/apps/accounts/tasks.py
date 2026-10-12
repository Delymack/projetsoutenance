# backend/apps/accounts/tasks.py
from celery import shared_task

from .services.email_service import send_verification_email
from .services.sms_service import send_verification_sms


@shared_task
def send_code_async(contact, code, contact_type, purpose):
    if contact_type == 'email':
        send_verification_email(contact, code, purpose)
    elif contact_type == 'sms':
        send_verification_sms(contact, code, purpose)
