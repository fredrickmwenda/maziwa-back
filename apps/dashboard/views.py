from datetime import date

from django.db.models import F, Sum
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.accounts.constants import KIND_FARMER
from apps.accounts.models import AccountSecurity
from apps.accounts.permissions import membership
from apps.advances.models import Advance
from apps.milk.models import MilkCollection, MilkRate
from apps.notifications.sms import sms_used_this_month
from apps.payments.models import Payment
from apps.payments.serializers import PaymentSerializer
from apps.store.models import Product


@api_view(["GET"])
def me(request):
    u, m = request.user, membership(request)
    dairies = [{"slug": x.organization.slug, "name": x.organization.name, "role": x.role.name,
                "state": x.organization.state}
               for x in u.memberships.filter(is_active=True).select_related("organization", "role")]
    base = {"username": u.username, "name": u.first_name or u.username, "dairies": dairies,
            "must_change_password": AccountSecurity.objects.filter(user=u, must_change_password=True).exists()}
    if m is None:
        return Response({**base, "role": "platform" if u.is_superuser else "choose"})
    org = m.organization
    month = date.today().replace(day=1)
    out = {**base, "role": "member", "kind": m.role.kind, "role_name": m.role.name, "perms": m.perms,
           "rate": MilkRate.current(org),
           "org": {"name": org.name, "slug": org.slug, "plan": org.plan.name, "state": org.state,
                   "ends": org.ends, "farmers_used": org.farmers.count(), "farmers_limit": org.plan.max_farmers,
                   "sms_used": sms_used_this_month(org), "sms_quota": org.plan.sms_quota if org.plan.sms_enabled else 0}}
    if m.role.kind == KIND_FARMER and m.farmer:
        f = m.farmer
        last = f.payments.first()
        out.update(credit_balance=f.credit_balance(), member_no=f.member_no,
                   litres_month=f.collections.filter(date__gte=month).aggregate(t=Sum(F("litres") - F("rejected_litres")))["t"] or 0,
                   advance_balance=sum((a.balance for a in f.advances.filter(status=Advance.DISBURSED)), 0),
                   unread=f.notifications.filter(is_read=False).count(),
                   last_payment=PaymentSerializer(last).data if last else None)
    else:
        out.update(farmers=org.farmers.count(),
                   litres_month=MilkCollection.objects.filter(organization=org, date__gte=month)
                   .aggregate(t=Sum(F("litres") - F("rejected_litres")))["t"] or 0,
                   litres_today=MilkCollection.objects.filter(organization=org, date=date.today())
                   .aggregate(t=Sum(F("litres") - F("rejected_litres")))["t"] or 0,
                   pending_payments=Payment.objects.filter(organization=org, status="PENDING").count(),
                   pending_advances=Advance.objects.filter(organization=org, status="REQUESTED").count(),
                   low_stock=Product.objects.filter(organization=org, active=True, reorder_level__gt=0,
                                                    stock_qty__lte=F("reorder_level")).count())
    return Response(out)
