from datetime import datetime

from django.db import transaction
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.constants import KIND_FARMER
from apps.accounts.models import Membership
from apps.accounts.permissions import require
from apps.mpesa.daraja import MpesaError
from apps.mpesa.services import payout_payroll
from core.documents import file_response
from core.tenancy import TenantMixin

from .documents import payslip_pdf
from .models import PayrollEntry
from .serializers import PayrollSerializer
from .services import finalize_payroll


class PayrollViewSet(TenantMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Staff see their own payslips; payroll.view sees everyone's; payroll.manage runs and pays."""
    queryset = PayrollEntry.objects.all()
    serializer_class = PayrollSerializer
    permission_classes = [require("payroll.manage", None)]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        m = self.m
        qs = PayrollEntry.objects.filter(organization=m.organization).select_related("member__user", "member__role")
        if m.role.kind == KIND_FARMER:
            return qs.none()
        return qs if m.has("payroll.view") else qs.filter(member=m)

    def perform_update(self, s):
        e = s.instance
        if e.status != PayrollEntry.PENDING:
            raise ValidationError({"detail": "Only pending payslips can be adjusted."})
        d = s.validated_data
        allow_, ded = d.get("allowances", e.allowances), d.get("deductions", e.deductions)
        if allow_ < 0 or ded < 0 or e.basic + allow_ - ded < 0:
            raise ValidationError({"detail": "Net pay cannot be negative."})
        s.save(net=e.basic + allow_ - ded)

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """{"month": "2026-11"}: creates a payslip for every active salaried staff member."""
        try:
            month = datetime.strptime(f"{request.data.get('month')}-01", "%Y-%m-%d").date()
        except ValueError:
            raise ValidationError({"month": "Use the format YYYY-MM."})
        n = 0
        for mem in (Membership.objects.filter(organization=self.org, is_active=True, monthly_salary__gt=0)
                    .exclude(role__kind=KIND_FARMER)):
            _, made = PayrollEntry.objects.get_or_create(
                member=mem, month=month,
                defaults=dict(organization=self.org, basic=mem.monthly_salary, net=mem.monthly_salary))
            n += made
        return Response({"created": n})

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def mark_paid(self, request, pk=None):
        e = self.get_object()
        if e.status == PayrollEntry.PAID:
            raise ValidationError({"detail": "Already paid."})
        finalize_payroll(e, request.data.get("reference", ""), user=request.user)
        return Response(PayrollSerializer(e).data)

    @action(detail=True, methods=["post"])
    def pay_mpesa(self, request, pk=None):
        try:
            tx = payout_payroll(self.get_object(), request.user)
        except MpesaError as e:
            raise ValidationError({"detail": str(e)})
        return Response({"transaction": tx.id, "message": "Sent to M-Pesa. Marked paid when M-Pesa confirms."}, status=202)

    @action(detail=False, methods=["post"])
    def pay_all_mpesa(self, request):
        sent, errors = 0, []
        for e in self.get_queryset().filter(status=PayrollEntry.PENDING, net__gt=0):
            try:
                payout_payroll(e, request.user)
                sent += 1
            except MpesaError as err:
                errors.append(f"{e.member.display_name}: {err}")
                if "not set up" in str(err) or "missing" in str(err):
                    break
        return Response({"sent": sent, "errors": errors[:10]})

    @action(detail=True, methods=["get"])
    def payslip(self, request, pk=None):
        e = self.get_object()
        return file_response(payslip_pdf(e), "application/pdf", f"payslip-{e.member.user.username}-{e.month:%Y-%m}.pdf")
