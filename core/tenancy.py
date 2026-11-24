"""TenantMixin: scopes every queryset to the dairy in the X-Dairy header."""
from rest_framework.exceptions import ValidationError

from apps.accounts.constants import KIND_FARMER
from apps.accounts.permissions import membership, require


def same_org(obj, org, field):
    if obj.organization_id != org.id:
        raise ValidationError({field: "Not found."})


class TenantMixin:
    """Queries are limited to the dairy chosen in X-Dairy; farmer-role members only see their own rows."""
    permission_classes = [require()]
    org_lookup = "organization"
    farmer_lookup = "farmer"

    @property
    def m(self):
        return membership(self.request)

    @property
    def org(self):
        return self.m.organization

    def get_queryset(self):
        m = self.m
        qs = super().get_queryset().filter(**{self.org_lookup: m.organization})
        if self.farmer_lookup:
            if m.role.kind == KIND_FARMER:
                f = m.farmer
                return qs.filter(**{self.farmer_lookup: f.pk}) if f else qs.none()
            if self.request.query_params.get("farmer"):
                qs = qs.filter(**{self.farmer_lookup: self.request.query_params["farmer"]})
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if membership(self.request):
            ctx["org"] = self.org
        return ctx

    def perform_create(self, s):
        s.save(organization=self.org)
