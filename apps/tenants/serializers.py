from django.conf import settings


def inv_dict(i):
    return {"id": i.id, "plan": i.plan.name, "amount": i.amount, "status": i.status,
            "created": i.created, "paybill": settings.BILLING_PAYBILL, "account": f"INV{i.id}"}
