from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import allow, membership

from .models import Invoice, Plan
from .serializers import inv_dict
from .services import ensure_plans


@api_view(["GET"])
@permission_classes([allow("billing.manage")])
def billing(request):
    ensure_plans()
    org = membership(request).organization
    return Response({"plans": [{"code": p.code, "name": p.name, "price": p.price_kes,
                                "max_farmers": p.max_farmers, "sms": p.sms_enabled, "sms_quota": p.sms_quota}
                               for p in Plan.objects.filter(price_kes__gt=0)],
                     "invoices": [inv_dict(i) for i in org.invoices.select_related("plan")[:20]]})


@api_view(["POST"])
@permission_classes([allow("billing.manage")])
def subscribe(request):
    org = membership(request).organization
    plan = get_object_or_404(Plan, code=request.data.get("plan"), price_kes__gt=0)
    if plan.max_farmers < org.farmers.count():
        raise ValidationError({"detail": f"You have more farmers than the {plan.name} plan allows."})
    inv = Invoice.objects.create(organization=org, plan=plan, amount=plan.price_kes)
    return Response(inv_dict(inv), status=201)
