from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.constants import KIND_FARMER
from apps.accounts.permissions import require
from apps.farmers.models import Farmer
from apps.notifications.services import notify
from core.documents import file_response, slip_pdf
from core.tenancy import TenantMixin, same_org

from .models import (CashSale, CreditOrder, FeedMill, Product, ProductPrice, PurchaseOrder, PurchaseOrderLine,
                     StockMovement, StockTake)
from .serializers import (CashSaleSerializer, CreditOrderSerializer, FeedMillSerializer, ProductPriceSerializer,
                          ProductSerializer, PurchaseOrderSerializer, StockMovementSerializer, StockTakeSerializer)
from .services import create_cash_sale, move_stock, receive_purchase_order, record_stock_take


def _dec(value, field="value"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValidationError({field: "Enter a valid number."})


def _price(value):
    v = _dec(value, "price")
    if v <= 0:
        raise ValidationError({"price": "Price must be above zero."})
    return v


class FeedMillViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = FeedMill.objects.all()
    serializer_class = FeedMillSerializer
    permission_classes = [require("store.manage", "store.view")]
    farmer_lookup = None


class ProductViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = Product.objects.filter(active=True).select_related("mill")
    serializer_class = ProductSerializer
    permission_classes = [require("store.manage", "store.view")]
    farmer_lookup = None

    def _check_mill(self, s):
        if s.validated_data.get("mill"):
            same_org(s.validated_data["mill"], self.org, "mill")

    @transaction.atomic
    def perform_create(self, s):
        self._check_mill(s)
        opening = _dec(self.request.data.get("stock_qty") or 0, "stock_qty")
        p = s.save(organization=self.org)
        ProductPrice.objects.create(product=p, price=p.price, note="Opening price")
        if opening > 0:
            move_stock(p, opening, StockMovement.OPENING, "Opening stock", self.request.user)

    @transaction.atomic
    def perform_update(self, s):
        self._check_mill(s)
        old = s.instance.price
        p = s.save()
        if p.price != old:
            p.price_updated = timezone.now()
            p.save(update_fields=["price_updated"])
            ProductPrice.objects.create(product=p, price=p.price, note="Edited")

    @action(detail=True, methods=["post"])
    def set_price(self, request, pk=None):
        p = self.get_object()
        p.set_price(_price(request.data.get("price")), request.data.get("note", "Market price change"))
        return Response(ProductSerializer(p).data)

    @action(detail=True, methods=["post"])
    def adjust(self, request, pk=None):
        """Add stock (positive) or write off damaged/lost stock (negative): {"delta": -3, "note": "spoilt"}."""
        p = self.get_object()
        delta = _dec(request.data.get("delta"), "delta")
        if delta == 0:
            raise ValidationError({"delta": "Enter a quantity other than zero."})
        try:
            move_stock(p, delta, StockMovement.ADJUSTMENT, str(request.data.get("note", ""))[:60], request.user)
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response(ProductSerializer(p).data)

    @action(detail=False, methods=["post"])
    def reprice(self, request):
        """{"percent": 5, "mill": 3, "feed_type": "DAIRY_MEAL"}; negative percent lowers prices."""
        pct = _dec(request.data.get("percent"), "percent")
        if pct <= -100:
            raise ValidationError({"percent": "Cannot drop by 100% or more."})
        qs = self.get_queryset()
        if request.data.get("mill"):
            qs = qs.filter(mill_id=request.data["mill"])
        if request.data.get("feed_type"):
            qs = qs.filter(feed_type=request.data["feed_type"])
        n = 0
        with transaction.atomic():
            for p in qs.select_for_update():
                p.set_price((p.price * (100 + pct) / 100).quantize(Decimal("0.01")),
                            request.data.get("note") or f"Market change {pct:+}%")
                n += 1
        return Response({"updated": n})

    @action(detail=True, methods=["get"])
    def prices(self, request, pk=None):
        return Response(ProductPriceSerializer(self.get_object().prices.all()[:50], many=True).data)


class CreditOrderViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = CreditOrder.objects.select_related("product", "farmer")
    serializer_class = CreditOrderSerializer
    permission_classes = [require("orders.create", "store.view")]
    http_method_names = ["get", "post", "head", "options"]

    @transaction.atomic
    def perform_create(self, s):
        m = self.m
        farmer = m.farmer if m.role.kind == KIND_FARMER else s.validated_data.get("farmer")
        if farmer is None:
            raise ValidationError({"farmer": "Required."})
        same_org(farmer, self.org, "farmer")
        product = s.validated_data["product"]
        same_org(product, self.org, "product")
        qty = s.validated_data["quantity"]
        if qty <= 0:
            raise ValidationError({"quantity": "Enter a quantity above zero."})
        total = product.price * qty
        order = s.save(organization=self.org, farmer=farmer, unit_price=product.price, total_cost=total,
                       feed_type=product.feed_type, mill_name=product.mill.name if product.mill else "")
        try:
            move_stock(product, -qty, StockMovement.SALE_CREDIT, f"Credit order #{order.pk}", self.request.user)
        except ValueError as e:
            raise ValidationError({"quantity": str(e)})
        notify(farmer, "Credit order",
               f"{qty} {product.unit} {product.name} ({product.get_feed_type_display()}) at KES {product.price}, "
               f"total KES {total}. It will be deducted from your next milk payment.")


class StockMovementViewSet(TenantMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = StockMovement.objects.select_related("product")
    serializer_class = StockMovementSerializer
    permission_classes = [require("store.manage", "store.manage")]
    farmer_lookup = None

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("product"):
            qs = qs.filter(product_id=self.request.query_params["product"])
        return qs[:300]


class PurchaseOrderViewSet(TenantMixin, viewsets.ReadOnlyModelViewSet):
    queryset = PurchaseOrder.objects.select_related("mill").prefetch_related("lines__product")
    serializer_class = PurchaseOrderSerializer
    permission_classes = [require("store.manage", "store.manage")]
    farmer_lookup = None

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        d = request.data
        mill = get_object_or_404(FeedMill, pk=d["mill"], organization=self.org) if d.get("mill") else None
        lines = d.get("lines") or []
        if not lines:
            raise ValidationError({"lines": "Add at least one product."})
        po = PurchaseOrder.objects.create(organization=self.org, mill=mill, expected_on=d.get("expected_on") or None,
                                          notes=str(d.get("notes", ""))[:200], created_by=request.user)
        for ln in lines:
            product = get_object_or_404(Product, pk=ln.get("product"), organization=self.org)
            qty, cost = _dec(ln.get("quantity"), "quantity"), _dec(ln.get("unit_cost"), "unit_cost")
            if qty <= 0 or cost < 0:
                raise ValidationError({"lines": "Quantity must be above zero and cost cannot be negative."})
            PurchaseOrderLine.objects.create(purchase_order=po, product=product, quantity=qty, unit_cost=cost)
        return Response(PurchaseOrderSerializer(po).data, status=201)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        try:
            po = receive_purchase_order(self.get_object(), request.user)
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response(PurchaseOrderSerializer(po).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        po = self.get_object()
        if po.status != PurchaseOrder.ORDERED:
            raise ValidationError({"detail": "Only an ordered purchase order can be cancelled."})
        po.status = PurchaseOrder.CANCELLED
        po.save(update_fields=["status"])
        return Response(PurchaseOrderSerializer(po).data)


class StockTakeViewSet(TenantMixin, viewsets.ReadOnlyModelViewSet):
    queryset = StockTake.objects.prefetch_related("lines__product")
    serializer_class = StockTakeSerializer
    permission_classes = [require("store.manage", "store.manage")]
    farmer_lookup = None

    def create(self, request, *args, **kwargs):
        counts = []
        for ln in request.data.get("lines") or []:
            product = get_object_or_404(Product, pk=ln.get("product"), organization=self.org)
            counts.append((product, _dec(ln.get("counted_qty"), "counted_qty")))
        if not counts:
            raise ValidationError({"lines": "Enter at least one counted product."})
        try:
            st = record_stock_take(self.org, request.user, str(request.data.get("notes", "")), counts)
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response(StockTakeSerializer(st).data, status=201)


class CashSaleViewSet(TenantMixin, viewsets.ReadOnlyModelViewSet):
    queryset = CashSale.objects.prefetch_related("lines__product")
    serializer_class = CashSaleSerializer
    permission_classes = [require("pos.sell", "pos.sell")]
    farmer_lookup = None

    def create(self, request, *args, **kwargs):
        d = request.data
        farmer = get_object_or_404(Farmer, pk=d["farmer"], organization=self.org) if d.get("farmer") else None
        items = []
        for ln in d.get("lines") or []:
            product = get_object_or_404(Product, pk=ln.get("product"), organization=self.org)
            items.append((product, _dec(ln.get("quantity"), "quantity")))
        if not items:
            raise ValidationError({"lines": "Add at least one product."})
        method = d.get("method") if d.get("method") in ("CASH", "MPESA") else "CASH"
        try:
            sale = create_cash_sale(self.org, request.user, str(d.get("customer_name", "")), farmer, method,
                                    str(d.get("reference", "")), items)
        except ValueError as e:
            raise ValidationError({"detail": str(e)})
        return Response(CashSaleSerializer(sale).data, status=201)

    @action(detail=True, methods=["get"])
    def receipt(self, request, pk=None):
        sale = self.get_object()
        pdf = slip_pdf(
            sale.organization.name, f"Receipt {sale.receipt_no}",
            [("Date", sale.created.date()), ("Customer", sale.customer_name or (sale.farmer.full_name if sale.farmer else "Walk-in")),
             ("Paid by", sale.method), ("Reference", sale.reference), ("TOTAL (KES)", sale.total)],
            "Items", [(f"{l.product.name} x {l.quantity} @ {l.unit_price}", l.line_total) for l in sale.lines.all()])
        return file_response(pdf, "application/pdf", f"receipt-{sale.receipt_no}.pdf")
