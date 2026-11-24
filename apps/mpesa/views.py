from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.accounts.permissions import allow, membership
from apps.audit import services as audit
from apps.tenants.models import Invoice

from .daraja import Daraja, MpesaError
from .models import MpesaConfig, MpesaTransaction
from .serializers import MpesaTransactionSerializer
from .services import complete_transaction, start_stk


ACK = {"ResultCode": 0, "ResultDesc": "Accepted"}


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def stk_callback(request, secret):
    tx = MpesaTransaction.objects.filter(secret=secret, kind__in=["SUBSCRIPTION", "CREDIT"]).first()
    cb = ((request.data or {}).get("Body") or {}).get("stkCallback") or {}
    if tx and (not tx.checkout_request_id or cb.get("CheckoutRequestID") == tx.checkout_request_id):
        items = {i.get("Name"): i.get("Value") for i in (cb.get("CallbackMetadata") or {}).get("Item", [])}
        ok, desc = cb.get("ResultCode") == 0, cb.get("ResultDesc", "")
        try:
            if ok and Decimal(str(items.get("Amount", 0))) < tx.amount:
                ok, desc = False, "Amount paid was less than requested"
        except InvalidOperation:
            ok, desc = False, "Bad amount in callback"
        complete_transaction(tx.pk, ok, str(items.get("MpesaReceiptNumber") or ""), desc)
        audit.log("MPESA_CALLBACK", f"STK {'success' if ok else 'failed'}: {tx.kind} KES {tx.amount}",
                  org_id=tx.organization_id, actor="mpesa")
    return Response(ACK)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def b2c_result(request, secret):
    tx = MpesaTransaction.objects.filter(secret=secret, kind__in=["PAYOUT_FARMER", "PAYOUT_STAFF"]).first()
    res = (request.data or {}).get("Result") or {}
    if tx and res.get("OriginatorConversationID") in (None, "", tx.conversation_id):
        ok = res.get("ResultCode") == 0
        complete_transaction(tx.pk, ok, str(res.get("TransactionID") or ""), res.get("ResultDesc", ""))
        audit.log("MPESA_CALLBACK", f"B2C {'success' if ok else 'failed'}: {tx.kind} KES {tx.amount}",
                  org_id=tx.organization_id, actor="mpesa")
    return Response(ACK)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def b2c_timeout(request, secret):
    """Safaricom could not process in time. We do NOT mark it failed (it may still go through);
    staff can confirm manually after checking the M-Pesa statement."""
    tx = MpesaTransaction.objects.filter(secret=secret, status="PENDING").first()
    if tx:
        tx.result_desc = "Timed out in the M-Pesa queue. Check your M-Pesa statement before paying again."
        tx.save(update_fields=["result_desc"])
    return Response(ACK)


@api_view(["GET", "PUT"])
@permission_classes([allow("mpesa.manage")])
def mpesa_config(request):
    org = membership(request).organization
    cfg, _ = MpesaConfig.objects.get_or_create(organization=org)
    if request.method == "PUT":
        d = request.data
        if d.get("env", cfg.env) not in ("sandbox", "production"):
            raise ValidationError({"env": "Use sandbox or production."})
        cfg.env = d.get("env", cfg.env)
        cfg.shortcode = (d.get("shortcode") or cfg.shortcode).strip()
        cfg.initiator_name = (d.get("initiator_name") or cfg.initiator_name).strip()
        cfg.set_secrets(consumer_key=d.get("consumer_key"), consumer_secret=d.get("consumer_secret"),
                        passkey=d.get("passkey"), initiator_password=d.get("initiator_password"))
        cfg.save()
        audit.log("MPESA_SETTINGS", "M-Pesa settings updated", org_id=org.id)
    sec = cfg.get_secrets()
    return Response({"env": cfg.env, "shortcode": cfg.shortcode, "initiator_name": cfg.initiator_name,
                     "has": {k: bool(sec.get(k)) for k in ("consumer_key", "consumer_secret", "passkey", "initiator_password")},
                     "callback_base": f"{settings.PUBLIC_BASE_URL.rstrip('/')}/api/mpesa/" if settings.PUBLIC_BASE_URL else ""})


@api_view(["GET"])
@permission_classes([allow("mpesa.manage")])
def mpesa_transactions(request):
    qs = MpesaTransaction.objects.filter(organization=membership(request).organization)[:100]
    return Response(MpesaTransactionSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([allow()])
def mpesa_status(request, pk):
    """Lets the app poll the result of an STK push the caller started."""
    tx = get_object_or_404(MpesaTransaction, pk=pk, organization=membership(request).organization,
                           initiated_by=request.user)
    return Response({"status": tx.status, "message": tx.result_desc, "receipt": tx.receipt})


@api_view(["POST"])
@permission_classes([allow("billing.manage")])
def billing_pay(request):
    """Owner pays an invoice by STK push to the platform's M-Pesa; the plan activates on confirmation."""
    m = membership(request)
    inv = get_object_or_404(Invoice, pk=request.data.get("invoice"), organization=m.organization, status="PENDING")
    try:
        tx = start_stk(Daraja.platform(), org=m.organization, kind="SUBSCRIPTION", phone=request.data.get("phone"),
                       amount=inv.amount, reference=f"INV{inv.id}", desc="Maziwa Cloud", user=request.user, invoice=inv)
    except MpesaError as e:
        raise ValidationError({"detail": str(e)})
    return Response({"transaction": tx.id, "message": "Check your phone and enter the M-Pesa PIN."}, status=202)
