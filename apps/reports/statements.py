"""One printable statement per farmer: milk delivered, feed on credit, advances and net pay."""
from decimal import Decimal

from apps.advances.models import Advance
from apps.milk.models import MilkCollection
from apps.milk.services import bonus_rate, load_tiers
from apps.payments.models import CreditPayment, Payment
from apps.store.models import CreditOrder
from core.documents import report_pdf

ZERO = Decimal("0")


def statement_pdf(farmer, start, end):
    org = farmer.organization
    tiers = load_tiers(org)
    cols = list(MilkCollection.objects.filter(farmer=farmer, date__range=(start, end)).order_by("date", "session"))
    milk = [[c.date, c.get_session_display(), c.litres, c.rejected_litres, c.accepted_litres, c.fat_percent or "-",
             c.protein_percent or "-", bonus_rate(tiers, c.fat_percent, c.protein_percent)] for c in cols]
    orders = CreditOrder.objects.filter(farmer=farmer, created__date__range=(start, end)).select_related("product")
    feed = [[o.created.date(), o.product.name, o.quantity, o.unit_price, o.total_cost] for o in orders]
    repay = [[c.created.date(), c.method, c.reference, c.amount] for c in
             CreditPayment.objects.filter(farmer=farmer, created__date__range=(start, end))]
    advs = [[a.disbursed_at.date(), a.principal, a.interest, a.total_due, a.disburse_method]
            for a in Advance.objects.filter(farmer=farmer, disbursed_at__date__range=(start, end))]
    pays = list(Payment.objects.filter(farmer=farmer, period_start__lte=end, period_end__gte=start))
    pay_rows = [[f"{p.period_start} to {p.period_end}", p.litres, p.bonus, p.gross, p.deductions, p.net, p.status] for p in pays]
    delivered = sum((c.litres for c in cols), ZERO)
    rejected = sum((c.rejected_litres for c in cols), ZERO)
    advance_owed = sum((a.balance for a in Advance.objects.filter(farmer=farmer, status=Advance.DISBURSED)), ZERO)
    summary = [("Farmer", f"{farmer.member_no} {farmer.full_name}"), ("Phone", farmer.phone), ("Route", farmer.route.name if farmer.route else "-"),
               ("Litres delivered", delivered), ("Litres rejected", rejected), ("Litres accepted", delivered - rejected),
               ("Milk value paid / due (KES)", sum((p.gross for p in pays), ZERO)),
               ("Feed credit and advances deducted (KES)", sum((p.deductions for p in pays), ZERO)),
               ("NET PAY (KES)", sum((p.net for p in pays), ZERO)),
               ("Feed credit still owed (KES)", farmer.credit_balance()), ("Advances still owed (KES)", advance_owed)]
    return report_pdf(org.name, "Farmer statement", f"{start} to {end}", summary, [
        ("Milk delivered", ["Date", "Session", "Delivered L", "Rejected L", "Accepted L", "Fat %", "Protein %", "Bonus/L"], milk),
        ("Payments", ["Period", "Accepted L", "Bonus", "Milk value", "Deductions", "Net", "Status"], pay_rows),
        ("Feed taken on credit", ["Date", "Feed", "Qty", "Price", "Total"], feed),
        ("Credit repayments", ["Date", "Method", "Reference", "Amount"], repay),
        ("Advances paid out", ["Date", "Principal", "Fee", "To repay", "Method"], advs)])
