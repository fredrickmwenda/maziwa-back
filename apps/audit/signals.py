"""Records every create/update/delete on money-related models with who did it."""
from decimal import Decimal

from .services import log


SKIP_FIELDS = {"secrets_enc", "price_updated", "farmer_seq", "created", "joined", "password"}


def _val(v):
    if isinstance(v, (Decimal,)) or hasattr(v, "isoformat"):
        return str(v)
    return v


def _snapshot(inst):
    return {f.name: _val(getattr(inst, f.attname)) for f in inst._meta.concrete_fields if f.name not in SKIP_FIELDS}


def _label(inst):
    name = getattr(inst, "name", None) or getattr(inst, "full_name", None) or getattr(inst, "description", None)
    return f"{inst._meta.verbose_name.title()} {name or '#' + str(inst.pk)}"


def _pre_save(sender, instance, **kw):
    instance._audit_old = None
    if instance.pk:
        old = sender.objects.filter(pk=instance.pk).first()
        instance._audit_old = _snapshot(old) if old else None


def _post_save(sender, instance, created, **kw):
    new = _snapshot(instance)
    if created:
        log("CREATE", _label(instance), org_id=_org_id(instance), instance=instance,
            changes={k: [None, v] for k, v in new.items() if v not in (None, "")})
        return
    old = getattr(instance, "_audit_old", None) or {}
    diff = {k: [old.get(k), v] for k, v in new.items() if old.get(k) != v}
    if diff:
        log("UPDATE", _label(instance), org_id=_org_id(instance), instance=instance, changes=diff)


def _post_delete(sender, instance, **kw):
    log("DELETE", _label(instance), org_id=_org_id(instance), instance=instance, changes=_snapshot(instance))


AUDITED = [
    "tenants.Organization", "tenants.Invoice", "farmers.Farmer", "collection.CollectionCentre", "collection.Route", "collection.Transporter", "collection.RouteTrip",
    "collection.TransporterPayment", "herd.Animal", "herd.HealthEvent", "advances.Advance", "advances.AdvanceSettings", "sales.MilkSale", "sales.Buyer",
    "milk.QualityTier", "store.PurchaseOrder", "store.StockTake", "store.CashSale", "milk.MilkRate", "milk.MilkCollection",
    "store.FeedMill", "store.Product", "store.CreditOrder", "payments.Payment", "payments.CreditPayment",
    "payroll.PayrollEntry", "expenses.Expense", "accounts.Role", "accounts.Membership", "mpesa.MpesaConfig",
]


def _org_id(inst):
    label = inst._meta.label
    if label == "tenants.Organization":
        return inst.pk
    if label == "herd.Animal":
        return inst.farmer.organization_id
    if label == "herd.HealthEvent":
        return inst.animal.farmer.organization_id
    return getattr(inst, "organization_id", None)


def connect():
    from django.apps import apps as django_apps
    from django.db.models.signals import post_delete, post_save, pre_save
    for label in AUDITED:
        model = django_apps.get_model(label)
        pre_save.connect(_pre_save, sender=model, weak=False, dispatch_uid=f"audit-pre-{label}")
        post_save.connect(_post_save, sender=model, weak=False, dispatch_uid=f"audit-post-{label}")
        post_delete.connect(_post_delete, sender=model, weak=False, dispatch_uid=f"audit-del-{label}")
