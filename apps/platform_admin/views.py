from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.accounts.constants import KIND_OWNER, PERMISSIONS
from apps.accounts.models import Role
from apps.accounts.permissions import PlatformAdmin
from apps.audit.models import AuditLog
from apps.audit.serializers import AuditSerializer
from apps.tenants.models import Invoice, Organization
from apps.tenants.serializers import inv_dict


@api_view(["GET"])
@permission_classes([PlatformAdmin])
def platform_orgs(request):
    return Response([{"id": o.id, "name": o.name, "slug": o.slug, "plan": o.plan.name, "state": o.state,
                      "ends": o.ends, "farmers": o.n, "phone": o.phone}
                     for o in Organization.objects.select_related("plan").annotate(n=Count("farmers"))])


@api_view(["GET"])
@permission_classes([PlatformAdmin])
def platform_roles(request):
    """Every role in every dairy, with permissions and who holds it."""
    out = []
    for r in Role.objects.select_related("organization").prefetch_related("memberships__user"):
        out.append({"id": r.id, "dairy": r.organization.name, "slug": r.organization.slug, "role": r.name,
                    "kind": r.kind, "permissions": list(PERMISSIONS) if r.kind == KIND_OWNER else r.permissions,
                    "members": [x.display_name for x in r.memberships.all()]})
    return Response(out)


@api_view(["POST"])
@permission_classes([PlatformAdmin])
def platform_suspend(request, pk):
    o = get_object_or_404(Organization, pk=pk)
    o.status = Organization.SUSPENDED if request.data.get("suspend") else (
        Organization.ACTIVE if o.paid_until else Organization.TRIAL)
    o.save()
    return Response({"state": o.state})


@api_view(["GET"])
@permission_classes([PlatformAdmin])
def platform_invoices(request):
    return Response([dict(inv_dict(i), org=i.organization.name)
                     for i in Invoice.objects.filter(status="PENDING").select_related("plan", "organization")])


@api_view(["POST"])
@permission_classes([PlatformAdmin])
def platform_confirm(request, pk):
    inv = get_object_or_404(Invoice, pk=pk, status="PENDING")
    inv.mark_paid(request.data.get("reference", ""))
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([PlatformAdmin])
def platform_audit(request):
    return Response(AuditSerializer(AuditLog.objects.all()[:300], many=True).data)
