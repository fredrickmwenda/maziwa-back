import secrets

from django.conf import settings
from django.db import models

from apps.advances.models import Advance
from apps.farmers.models import Farmer
from apps.payments.models import Payment
from apps.payroll.models import PayrollEntry
from apps.tenants.models import Invoice, Organization


def new_secret():
    return secrets.token_urlsafe(24)


class MpesaConfig(models.Model):
    """A dairy's own Daraja credentials (used to pay farmers/staff and to collect feed credit)."""
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="mpesa")
    env = models.CharField(max_length=12, default="sandbox")  # sandbox | production
    shortcode = models.CharField(max_length=12, blank=True)
    initiator_name = models.CharField(max_length=60, blank=True)
    secrets_enc = models.TextField(blank=True)  # encrypted JSON: consumer_key, consumer_secret, passkey, initiator_password

    def get_secrets(self):
        from core.utils import decrypt_json
        return decrypt_json(self.secrets_enc)

    def set_secrets(self, **new):
        from core.utils import encrypt_json
        data = self.get_secrets()
        data.update({k: v for k, v in new.items() if v})
        self.secrets_enc = encrypt_json(data)


class MpesaTransaction(models.Model):
    SUBSCRIPTION, CREDIT, PAYOUT_FARMER, PAYOUT_STAFF, PAYOUT_ADVANCE = (
        "SUBSCRIPTION", "CREDIT", "PAYOUT_FARMER", "PAYOUT_STAFF", "PAYOUT_ADVANCE")
    PENDING, SUCCESS, FAILED = "PENDING", "SUCCESS", "FAILED"
    organization = models.ForeignKey(Organization, null=True, on_delete=models.CASCADE, related_name="mpesa_tx")
    kind = models.CharField(max_length=15)
    status = models.CharField(max_length=10, default=PENDING)
    phone = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    secret = models.CharField(max_length=64, unique=True, default=new_secret)
    checkout_request_id = models.CharField(max_length=80, blank=True)
    merchant_request_id = models.CharField(max_length=80, blank=True)
    conversation_id = models.CharField(max_length=80, blank=True)
    receipt = models.CharField(max_length=40, blank=True)
    result_desc = models.CharField(max_length=255, blank=True)
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.SET_NULL)
    farmer = models.ForeignKey(Farmer, null=True, blank=True, on_delete=models.SET_NULL)
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.SET_NULL)
    payroll = models.ForeignKey(PayrollEntry, null=True, blank=True, on_delete=models.SET_NULL)
    advance = models.ForeignKey(Advance, null=True, blank=True, on_delete=models.SET_NULL)
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(auto_now_add=True)
    completed = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]
