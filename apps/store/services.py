"""Stock rules. Every change to stock goes through move_stock so it is always logged."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.expenses.models import Expense

from .models import (CashSale, CashSaleLine, Product, PurchaseOrder, StockMovement, StockTake, StockTakeLine)


@transaction.atomic
def move_stock(product, delta, kind, reference="", user=None):
    """Add (+) or remove (-) stock and log it. Raises ValueError if it would go below zero."""
    p = Product.objects.select_for_update().get(pk=product.pk)
    new = p.stock_qty + Decimal(delta)
    if new < 0:
        raise ValueError(f"Only {p.stock_qty} {p.unit} of {p.name} in stock.")
    p.stock_qty = new
    p.save(update_fields=["stock_qty"])
    StockMovement.objects.create(organization=p.organization, product=p, kind=kind, quantity=delta,
                                 balance_after=new, reference=reference[:60], created_by=user)
    product.stock_qty = new
    return p


@transaction.atomic
def receive_purchase_order(po, user=None):
    """Goods arrived: add stock and record the cost as a Feed purchase expense."""
    po = PurchaseOrder.objects.select_for_update().get(pk=po.pk)
    if po.status != PurchaseOrder.ORDERED:
        raise ValueError("Only an ordered purchase order can be received.")
    total, today = Decimal("0"), timezone.localdate()
    for line in po.lines.select_related("product"):
        move_stock(line.product, line.quantity, StockMovement.PURCHASE, po.reference, user)
        line.received_qty = line.quantity
        line.save(update_fields=["received_qty"])
        total += line.quantity * line.unit_cost
    po.status, po.received_on = PurchaseOrder.RECEIVED, today
    po.expense = Expense.objects.create(
        organization=po.organization, category="FEED_PURCHASE", amount=total, date=today,
        description=f"Purchase order {po.reference}", paid_to=po.mill.name if po.mill else "",
        reference=po.reference, recorded_by=user)
    po.save()
    return po


@transaction.atomic
def record_stock_take(org, user, notes, counts):
    """counts: [(product, counted_qty)]. Differences are posted as stock movements."""
    st = StockTake.objects.create(organization=org, notes=notes[:200], created_by=user)
    for product, counted in counts:
        if counted < 0:
            raise ValueError(f"Counted quantity for {product.name} cannot be negative.")
        p = Product.objects.select_for_update().get(pk=product.pk)
        variance = counted - p.stock_qty
        StockTakeLine.objects.create(stock_take=st, product=p, expected_qty=p.stock_qty, counted_qty=counted,
                                     variance=variance, variance_value=(variance * p.price).quantize(Decimal("0.01")))
        if variance != 0:
            move_stock(p, variance, StockMovement.STOCKTAKE, f"Stock take #{st.pk}", user)
    return st


@transaction.atomic
def create_cash_sale(org, user, customer_name, farmer, method, reference, items):
    """items: [(product, quantity)]. Prices are today's selling prices."""
    sale = CashSale.objects.create(organization=org, farmer=farmer, customer_name=customer_name[:100], method=method,
                                   reference=reference[:60], created_by=user)
    total = Decimal("0")
    for product, qty in items:
        if qty <= 0:
            raise ValueError("Quantities must be above zero.")
        p = Product.objects.get(pk=product.pk)
        line_total = (p.price * qty).quantize(Decimal("0.01"))
        CashSaleLine.objects.create(sale=sale, product=p, quantity=qty, unit_price=p.price, line_total=line_total)
        move_stock(p, -qty, StockMovement.SALE_CASH, sale.receipt_no, user)
        total += line_total
    sale.total = total
    sale.save(update_fields=["total"])
    return sale
