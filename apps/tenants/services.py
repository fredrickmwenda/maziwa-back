from rest_framework.exceptions import PermissionDenied

from .models import Plan


def ensure_plans():
    for code, name, price, cap, sms, quota in [
        ("starter", "Starter", 0, 50, False, 0),
        ("growth", "Growth", 2500, 500, True, 1000),
        ("pro", "Pro", 7500, 5000, True, 10000),
    ]:
        Plan.objects.get_or_create(code=code, defaults=dict(
            name=name, price_kes=price, max_farmers=cap, sms_enabled=sms, sms_quota=quota))


def check_capacity(org):
    if org.farmers.count() >= org.plan.max_farmers:
        raise PermissionDenied(f"The {org.plan.name} plan allows {org.plan.max_farmers} farmers. Upgrade under Billing.")
