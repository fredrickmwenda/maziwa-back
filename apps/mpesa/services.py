import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.advances.models import Advance
from apps.advances.services import mark_disbursed
from apps.payments.models import Payment
from apps.payments.services import apply_credit_payment, finalize_farmer_payment
from apps.payroll.models import PayrollEntry
from apps.payroll.services import finalize_payroll
from core.utils import normalize_phone

from .daraja import Daraja, MpesaError, whole
from .models import MpesaConfig, MpesaTransaction


def _phone(raw):
    try:
        return normalize_phone(raw)
    except ValueError as e:
        raise MpesaError(str(e))


def get_org_daraja(org, need="stk"):
    cfg = MpesaConfig.objects.filter(organization=org).first()
    if not cfg:
        raise MpesaError("M-Pesa is not set up for this dairy. The owner can add the Daraja details under M-Pesa.")
    return Daraja.from_config(cfg, need)


def _cb(path):
    if not settings.PUBLIC_BASE_URL:
        raise MpesaError("The server has no PUBLIC_BASE_URL, so M-Pesa cannot send its confirmation back.")
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/api/mpesa/{path}"


def start_stk(daraja, *, org, kind, phone, amount, reference, desc, user=None, **links):
    amt = whole(amount)
    if amt < 1:
        raise MpesaError("Amount must be at least KES 1.")
    phone = _phone(phone)
    tx = MpesaTransaction.objects.create(organization=org, kind=kind, phone=phone, amount=Decimal(amt),
                                         initiated_by=user, **links)
    try:
        data = daraja.stk_push(phone, amt, reference, desc, _cb(f"stk/{tx.secret}/"))
    except Exception as e:
        tx.status, tx.result_desc = MpesaTransaction.FAILED, str(e)[:250]
        tx.save()
        raise
    tx.checkout_request_id = data.get("CheckoutRequestID", "")
    tx.merchant_request_id = data.get("MerchantRequestID", "")
    tx.save()
    return tx


def start_b2c(daraja, *, org, kind, phone, amount, remarks, user=None, **links):
    amt = whole(amount)
    if amt < 1:
        raise MpesaError("Amount must be at least KES 1.")
    phone = _phone(phone)
    tx = MpesaTransaction.objects.create(organization=org, kind=kind, phone=phone, amount=Decimal(amt),
                                         initiated_by=user, conversation_id=str(uuid.uuid4()), **links)
    try:
        daraja.b2c(phone, amt, remarks, _cb(f"b2c-result/{tx.secret}/"), _cb(f"b2c-timeout/{tx.secret}/"),
                   tx.conversation_id)
    except Exception as e:
        tx.status, tx.result_desc = MpesaTransaction.FAILED, str(e)[:250]
        tx.save()
        raise
    return tx


def payout_farmer_payment(payment, user=None):
    if payment.status != Payment.PENDING:
        raise MpesaError("This payment is not waiting to be paid.")
    if payment.net <= 0:
        raise MpesaError("Net pay is zero, so there is nothing to send.")
    d = get_org_daraja(payment.organization, "b2c")
    tx = start_b2c(d, org=payment.organization, kind=MpesaTransaction.PAYOUT_FARMER, phone=payment.farmer.phone,
                   amount=payment.net, remarks=f"Milk payment to {payment.period_end}", user=user, payment=payment)
    payment.status = "PROCESSING"
    payment.save(update_fields=["status"])
    return tx


def payout_payroll(entry, user=None):
    if entry.status != PayrollEntry.PENDING:
        raise MpesaError("This payslip is not waiting to be paid.")
    if entry.net <= 0:
        raise MpesaError("Net pay is zero, so there is nothing to send.")
    if not entry.member.phone:
        raise MpesaError(f"{entry.member.display_name} has no phone number for salary payment.")
    d = get_org_daraja(entry.organization, "b2c")
    tx = start_b2c(d, org=entry.organization, kind=MpesaTransaction.PAYOUT_STAFF, phone=entry.member.phone,
                   amount=entry.net, remarks=f"Salary {entry.month:%b %Y}", user=user, payroll=entry)
    entry.status = "PROCESSING"
    entry.save(update_fields=["status"])
    return tx


def payout_advance(advance, user=None):
    if advance.status != Advance.APPROVED:
        raise MpesaError("Only an approved advance can be paid out.")
    d = get_org_daraja(advance.organization, "b2c")
    tx = start_b2c(d, org=advance.organization, kind=MpesaTransaction.PAYOUT_ADVANCE, phone=advance.farmer.phone,
                   amount=advance.principal, remarks="Advance", user=user, advance=advance)
    advance.status = Advance.PROCESSING
    advance.save(update_fields=["status"])
    return tx


@transaction.atomic
def complete_transaction(tx_id, success, receipt="", desc=""):
    """Called by the Safaricom callbacks. Safe to call twice."""
    tx = MpesaTransaction.objects.select_for_update().get(pk=tx_id)
    if tx.status != MpesaTransaction.PENDING:
        return tx
    tx.status = MpesaTransaction.SUCCESS if success else MpesaTransaction.FAILED
    tx.receipt, tx.result_desc, tx.completed = (receipt or "")[:40], (desc or "")[:250], timezone.now()
    tx.save()
    if tx.kind == MpesaTransaction.SUBSCRIPTION:
        if success and tx.invoice and tx.invoice.status == "PENDING":
            tx.invoice.mark_paid(receipt)
    elif tx.kind == MpesaTransaction.CREDIT:
        if success and tx.farmer:
            apply_credit_payment(tx.farmer, tx.amount, "MPESA", receipt)
    elif tx.kind == MpesaTransaction.PAYOUT_FARMER and tx.payment:
        if success:
            finalize_farmer_payment(tx.payment, receipt)
        elif tx.payment.status == "PROCESSING":
            tx.payment.status = Payment.PENDING
            tx.payment.save(update_fields=["status"])
    elif tx.kind == MpesaTransaction.PAYOUT_STAFF and tx.payroll:
        if success:
            finalize_payroll(tx.payroll, receipt, user=tx.initiated_by)
        elif tx.payroll.status == "PROCESSING":
            tx.payroll.status = PayrollEntry.PENDING
            tx.payroll.save(update_fields=["status"])
    elif tx.kind == MpesaTransaction.PAYOUT_ADVANCE and tx.advance:
        if success:
            mark_disbursed(tx.advance, "MPESA", receipt, user=tx.initiated_by)
        elif tx.advance.status == Advance.PROCESSING:
            tx.advance.status = Advance.APPROVED
            tx.advance.save(update_fields=["status"])
    return tx
