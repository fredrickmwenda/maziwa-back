from django.db import transaction

from .models import Notification
from .sms import send_sms


def notify(farmer, title, message, sms=True):
    """In-app alert plus (on plans with SMS) a text message, sent after the database commit."""
    Notification.objects.create(farmer=farmer, title=title, message=message)
    if sms:
        org, phone = farmer.organization, farmer.phone
        text = f"{org.name}: {title}. {message}"
        transaction.on_commit(lambda: send_sms(phone, text, org=org, kind="ALERT"))
