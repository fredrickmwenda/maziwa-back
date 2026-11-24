from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.farmers.models import Farmer
from apps.tenants.models import Organization


FEED_TYPES = [
    ("DAIRY_MEAL", "Dairy meal"), ("CALF_PELLETS", "Calf pellets"), ("HAY", "Hay"),
    ("SILAGE", "Silage"), ("MINERAL", "Mineral salts / licks"), ("MOLASSES", "Molasses"),
    ("SUPPLEMENT", "Concentrate / supplement"), ("OTHER", "Other"),
]


class FeedMill(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="mills")
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)

    class Meta:
        unique_together = ("organization", "name")

    def __str__(self):
        return self.name


class Product(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=100)
    feed_type = models.CharField(max_length=20, choices=FEED_TYPES, default="DAIRY_MEAL")
    mill = models.ForeignKey(FeedMill, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    unit = models.CharField(max_length=20, default="bag")
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Current selling price")
    stock_qty = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Alert when stock falls to this level")
    active = models.BooleanField(default=True)
    price_updated = models.DateTimeField(default=timezone.now)

    def set_price(self, new_price, note=""):
        """Change the selling price and keep a history row. Old credit orders keep their old price."""
        new_price = Decimal(new_price)
        if new_price <= 0:
            raise ValueError("Price must be above zero.")
        self.price, self.price_updated = new_price, timezone.now()
        self.save(update_fields=["price", "price_updated"])
        ProductPrice.objects.create(product=self, price=new_price, note=note)

    def __str__(self):
        return self.name


class ProductPrice(models.Model):
    """Market price history for a product."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="prices")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.CharField(max_length=120, blank=True)
    effective_from = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-effective_from", "-id"]


class CreditOrder(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="orders")
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name="orders")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    feed_type = models.CharField(max_length=20, blank=True, help_text="Snapshot at order time")
    mill_name = models.CharField(max_length=100, blank=True, help_text="Snapshot at order time")
    quantity = models.DecimalField(max_digits=8, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created"]

    @property
    def balance(self):
        return self.total_cost - self.amount_paid


class StockMovement(models.Model):
    """Every change to stock, so the count can always be explained."""
    OPENING, PURCHASE, SALE_CREDIT, SALE_CASH, ADJUSTMENT, STOCKTAKE = (
        "OPENING", "PURCHASE", "SALE_CREDIT", "SALE_CASH", "ADJUSTMENT", "STOCKTAKE")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="stock_movements")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="movements")
    kind = models.CharField(max_length=12)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, help_text="+ in, - out")
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=60, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created", "-id"]


class PurchaseOrder(models.Model):
    ORDERED, RECEIVED, CANCELLED = "ORDERED", "RECEIVED", "CANCELLED"
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="purchase_orders")
    mill = models.ForeignKey(FeedMill, null=True, blank=True, on_delete=models.SET_NULL, related_name="purchase_orders")
    status = models.CharField(max_length=10, default=ORDERED)
    ordered_on = models.DateField(default=timezone.localdate)
    expected_on = models.DateField(null=True, blank=True)
    received_on = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    expense = models.OneToOneField("expenses.Expense", null=True, blank=True, on_delete=models.SET_NULL, related_name="purchase_order")

    class Meta:
        ordering = ["-ordered_on", "-id"]

    @property
    def reference(self):
        return f"PO-{self.pk:05d}"

    @property
    def total(self):
        return sum((l.quantity * l.unit_cost for l in self.lines.all()), Decimal("0"))


class PurchaseOrderLine(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    received_qty = models.DecimalField(max_digits=10, decimal_places=2, default=0)


class StockTake(models.Model):
    """A physical count. Differences become stock adjustments."""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="stock_takes")
    taken_on = models.DateField(default=timezone.localdate)
    notes = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]


class StockTakeLine(models.Model):
    stock_take = models.ForeignKey(StockTake, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    expected_qty = models.DecimalField(max_digits=10, decimal_places=2)
    counted_qty = models.DecimalField(max_digits=10, decimal_places=2)
    variance = models.DecimalField(max_digits=10, decimal_places=2)
    variance_value = models.DecimalField(max_digits=12, decimal_places=2, help_text="Variance at the selling price")


class CashSale(models.Model):
    """Over-the-counter sale paid now (cash or M-Pesa), next to credit orders."""
    CASH, MPESA = "CASH", "MPESA"
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="cash_sales")
    farmer = models.ForeignKey(Farmer, null=True, blank=True, on_delete=models.SET_NULL, related_name="cash_purchases")
    customer_name = models.CharField(max_length=100, blank=True)
    method = models.CharField(max_length=6, default=CASH)
    reference = models.CharField(max_length=60, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    @property
    def receipt_no(self):
        return f"S-{self.pk:06d}"


class CashSaleLine(models.Model):
    sale = models.ForeignKey(CashSale, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
