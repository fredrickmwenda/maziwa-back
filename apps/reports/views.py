from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.constants import KIND_FARMER
from apps.accounts.permissions import allow, membership, require
from apps.farmers.models import Farmer
from apps.audit import services as audit
from core.documents import csv_bytes, file_response, pdf_table

from rest_framework.response import Response

from .analytics import REPORTS, period
from .datasets import DATASETS, zip_all
from .statements import statement_pdf


@api_view(["GET"])
@permission_classes([allow()])
def export_data(request, dataset):
    m = membership(request)
    p, fmt = request.query_params, request.query_params.get("fmt", "csv")
    today = timezone.localdate()
    if dataset == "all":
        if not m.has("team.manage"):
            raise PermissionDenied("Only the owner can download all data.")
        audit.log("EXPORT", "Full data export", org_id=m.organization_id)
        return file_response(zip_all(m, p), "application/zip", f"{m.organization.slug}-all-data-{today}.zip")
    if dataset not in DATASETS:
        raise ValidationError({"detail": "Unknown dataset."})
    perm, builder = DATASETS[dataset]
    if (perm and not m.has(perm)) or (perm is None and m.role.kind == KIND_FARMER):
        raise PermissionDenied("You do not have permission to export this.")
    title, headers, rows = builder(m, p)
    audit.log("EXPORT", f"Exported {dataset} ({fmt}, {len(rows)} rows)", org_id=m.organization_id)
    name = f"{m.organization.slug}-{dataset}-{today}"
    if fmt == "pdf":
        return file_response(pdf_table(m.organization.name, title, p, headers, rows), "application/pdf", name + ".pdf")
    return file_response(csv_bytes(headers, rows), "text/csv; charset=utf-8", name + ".csv")


@api_view(["GET"])
@permission_classes([require(None, "reports.view")])
def report_data(request, name):
    """JSON for the Reports screen, or ?fmt=csv / ?fmt=pdf to download the same table."""
    fn = REPORTS.get(name)
    if fn is None:
        raise ValidationError({"detail": "Unknown report."})
    m, p = membership(request), request.query_params
    try:
        out = fn(m.organization, p)
    except (ValueError, KeyError):
        raise ValidationError({"detail": "Check the dates (use YYYY-MM-DD) and month (YYYY-MM)."})
    fmt = p.get("fmt", "json")
    if fmt == "csv":
        return file_response(csv_bytes(out["headers"], out["rows"]), "text/csv; charset=utf-8", f"{name}.csv")
    if fmt == "pdf":
        start, end = out["period"]
        pdf = pdf_table(m.organization.name, out["title"], {"start": start, "end": end}, out["headers"], out["rows"])
        return file_response(pdf, "application/pdf", f"{name}.pdf")
    return Response(out)


@api_view(["GET"])
@permission_classes([allow()])
def farmer_statement(request, farmer_id=None):
    """PDF statement for one farmer. A farmer gets their own; staff need payments.view."""
    m = membership(request)
    if m.role.kind == KIND_FARMER:
        farmer = m.farmer
    else:
        if not m.has("payments.view"):
            raise PermissionDenied("You do not have permission to print statements.")
        farmer = get_object_or_404(Farmer, pk=farmer_id, organization=m.organization)
    if farmer is None:
        raise ValidationError({"detail": "No farmer record."})
    try:
        start, end = period(request.query_params)
    except ValueError:
        raise ValidationError({"detail": "Use dates like 2026-11-30."})
    audit.log("EXPORT", f"Statement for {farmer.full_name}", org_id=m.organization_id)
    return file_response(statement_pdf(farmer, start, end), "application/pdf", f"statement-{farmer.member_no}-{start}-{end}.pdf")
