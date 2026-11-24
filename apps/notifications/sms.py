"""Africa's Talking SMS. send_sms never raises: every attempt is written to SmsLog."""
import requests
from django.conf import settings
from django.utils import timezone

from core.utils import normalize_phone

from .models import SmsLog


def _log(org, phone, message, kind, status, detail="", cost=""):
    SmsLog.objects.create(organization=org, phone=str(phone)[:20], message=message[:480], kind=kind,
                          status=status, detail=detail[:200], cost=str(cost)[:20])


def sms_used_this_month(org):
    start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return SmsLog.objects.filter(organization=org, status=SmsLog.SENT, created__gte=start).exclude(kind="OTP").count()


def send_sms(phone, message, org=None, kind="ALERT", bypass_plan=False):
    """org: the dairy whose plan/quota pays for this message. bypass_plan: security codes (not counted)."""
    try:
        to = "+" + normalize_phone(phone)
    except ValueError as e:
        return _log(org, phone, message, kind, SmsLog.FAILED, str(e))
    if org is not None and not bypass_plan:
        plan = org.plan
        if not plan.sms_enabled:
            return _log(org, to, message, kind, SmsLog.SKIPPED, "Plan does not include SMS")
        if sms_used_this_month(org) >= plan.sms_quota:
            return _log(org, to, message, kind, SmsLog.SKIPPED, "Monthly SMS quota used up")
    if not settings.AT_API_KEY:
        return _log(org, to, message, kind, SmsLog.SKIPPED, "SMS provider not configured")
    host = "api.sandbox.africastalking.com" if settings.AT_USERNAME == "sandbox" else "api.africastalking.com"
    data = {"username": settings.AT_USERNAME, "to": to, "message": message[:459]}
    if settings.AT_SENDER_ID:
        data["from"] = settings.AT_SENDER_ID
    try:
        r = requests.post(f"https://{host}/version1/messaging", data=data, timeout=8,
                          headers={"apiKey": settings.AT_API_KEY, "Accept": "application/json"})
        rec = r.json()["SMSMessageData"]["Recipients"][0]
        ok = rec.get("statusCode") in (100, 101, 102)
        _log(org, to, message, kind, SmsLog.SENT if ok else SmsLog.FAILED, rec.get("status", ""), rec.get("cost", ""))
    except Exception as e:
        _log(org, to, message, kind, SmsLog.FAILED, f"Provider error: {e.__class__.__name__}")
