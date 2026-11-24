import io
import zipfile

from apps.accounts.constants import KIND_FARMER
from apps.advances.models import Advance
from apps.expenses.models import Expense
from apps.farmers.models import Farmer
from apps.herd.models import HealthEvent
from apps.milk.models import MilkCollection
from apps.payments.models import CreditPayment, Payment
from apps.payroll.models import PayrollEntry
from apps.sales.models import MilkSale
from apps.store.models import CreditOrder, StockMovement
from core.documents import csv_bytes


def scoped(qs, m, field):
    """A farmer only ever exports their own rows."""
    if m.role.kind == KIND_FARMER:
        f = m.farmer
        return qs.filter(**{field: f.pk}) if f else qs.none()
    return qs


def _range(qs, p, field):
    if p.get("start"):
        qs = qs.filter(**{f"{field}__gte": p["start"]})
    if p.get("end"):
        qs = qs.filter(**{f"{field}__lte": p["end"]})
    return qs


def ds_farmers(m, p):
    qs = scoped(Farmer.objects.filter(organization=m.organization).select_related("route").prefetch_related("orders"), m, "id")
    return "Farmers", ["No.", "Name", "Phone", "National ID", "Village", "Route", "Credit owed"], [
        [f.member_no, f.full_name, f.phone, f.national_id, f.village, f.route.name if f.route else "", f.credit_balance()] for f in qs]


def ds_milk(m, p):
    qs = _range(scoped(MilkCollection.objects.filter(organization=m.organization).select_related("farmer"), m, "farmer"), p, "date")
    return "Milk collection", ["Date", "Session", "Farmer no.", "Farmer", "Delivered L", "Rejected L", "Accepted L", "Fat %",
                               "Protein %", "Reject reason"], [
        [c.date, c.get_session_display(), c.farmer.member_no, c.farmer.full_name, c.litres, c.rejected_litres,
         c.accepted_litres, c.fat_percent, c.protein_percent, c.get_reject_reason_display()] for c in qs]


def ds_payments(m, p):
    qs = _range(scoped(Payment.objects.filter(organization=m.organization).select_related("farmer"), m, "farmer"), p, "period_end")
    return "Farmer payments", ["From", "To", "Farmer no.", "Farmer", "Accepted L", "Rejected L", "Rate", "Bonus", "Milk value",
                               "Deductions", "Net", "Status", "Reference"], [
        [x.period_start, x.period_end, x.farmer.member_no, x.farmer.full_name, x.litres, x.rejected_litres, x.rate, x.bonus,
         x.gross, x.deductions, x.net, x.status, x.reference] for x in qs]


def ds_credit(m, p):
    qs = _range(scoped(CreditOrder.objects.filter(organization=m.organization).select_related("farmer", "product"), m, "farmer"), p, "created__date")
    return "Feed on credit", ["Date", "Farmer no.", "Farmer", "Feed", "Type", "Mill", "Qty", "Price", "Total", "Paid", "Balance"], [
        [o.created.date(), o.farmer.member_no, o.farmer.full_name, o.product.name, o.feed_type, o.mill_name,
         o.quantity, o.unit_price, o.total_cost, o.amount_paid, o.balance] for o in qs]


def ds_credit_payments(m, p):
    qs = _range(scoped(CreditPayment.objects.filter(organization=m.organization).select_related("farmer"), m, "farmer"), p, "created__date")
    return "Credit repayments", ["Date", "Farmer no.", "Farmer", "Amount", "Method", "Reference"], [
        [c.created.date(), c.farmer.member_no, c.farmer.full_name, c.amount, c.method, c.reference] for c in qs]


def ds_advances(m, p):
    qs = _range(scoped(Advance.objects.filter(organization=m.organization).select_related("farmer"), m, "farmer"), p, "requested_at__date")
    return "Advances and loans", ["Requested", "Farmer no.", "Farmer", "Principal", "Fee", "Total due", "Repaid", "Balance", "Status", "Reference"], [
        [a.requested_at.date(), a.farmer.member_no, a.farmer.full_name, a.principal, a.interest, a.total_due, a.amount_repaid,
         a.balance, a.status, a.reference] for a in qs]


def ds_health(m, p):
    qs = _range(scoped(HealthEvent.objects.filter(animal__farmer__organization=m.organization).select_related("animal__farmer"),
                       m, "animal__farmer"), p, "date")
    return "Animal health records", ["Date", "Farmer", "Animal", "Type", "Details", "Vet", "Cost", "Withdrawal ends", "Next due"], [
        [e.date, e.animal.farmer.full_name, e.animal.tag, e.get_kind_display(), e.description, e.vet_name, e.cost,
         e.withdrawal_ends, e.next_due] for e in qs]


def ds_sales(m, p):
    qs = _range(MilkSale.objects.filter(organization=m.organization).select_related("buyer"), p, "date")
    return "Milk sales", ["Date", "Buyer", "Litres", "Price/L", "Total", "Received", "Balance", "Status", "Reference"], [
        [s.date, s.buyer.name, s.litres, s.price_per_litre, s.total, s.amount_received, s.balance, s.status, s.reference] for s in qs]


def ds_stock(m, p):
    qs = _range(StockMovement.objects.filter(organization=m.organization).select_related("product"), p, "created__date")
    return "Stock movements", ["Date", "Product", "Type", "Quantity", "Balance after", "Reference"], [
        [x.created.date(), x.product.name, x.kind, x.quantity, x.balance_after, x.reference] for x in qs]


def ds_expenses(m, p):
    qs = _range(Expense.objects.filter(organization=m.organization), p, "date")
    return "Expenses", ["Date", "Category", "Description", "Paid to", "Reference", "Amount"], [
        [e.date, e.get_category_display(), e.description, e.paid_to, e.reference, e.amount] for e in qs]


def ds_payroll(m, p):
    qs = PayrollEntry.objects.filter(organization=m.organization).select_related("member__user", "member__role")
    if not m.has("payroll.view"):
        qs = qs.filter(member=m)
    qs = _range(qs, p, "month")
    return "Payroll", ["Month", "Staff", "Role", "Basic", "Allowances", "Deductions", "Net pay", "Status", "Reference"], [
        [e.month.strftime("%Y-%m"), e.member.display_name, e.member.role.name, e.basic, e.allowances,
         e.deductions, e.net, e.status, e.reference] for e in qs]


# dataset -> (permission needed, builder). None = any non-farmer member.
DATASETS = {
    "farmers": ("farmers.view", ds_farmers), "milk": ("milk.view", ds_milk),
    "payments": ("payments.view", ds_payments), "credit": ("store.view", ds_credit),
    "credit-payments": ("store.view", ds_credit_payments), "advances": ("advances.view", ds_advances),
    "health": ("herd.view", ds_health), "sales": ("sales.view", ds_sales), "stock-movements": ("store.manage", ds_stock),
    "expenses": ("expenses.view", ds_expenses), "payroll": (None, ds_payroll),
}


def zip_all(m, p):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, (_, fn) in DATASETS.items():
            _, headers, rows = fn(m, p)
            z.writestr(f"{name}.csv", csv_bytes(headers, rows))
    return buf.getvalue()
