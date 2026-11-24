"""Management reports. Each returns {title, period, headers, rows, summary, chart}."""
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, F, Sum
from django.utils import timezone

from apps.advances.models import Advance
from apps.collection.models import CollectionCentre, Route, RouteTrip, Transporter, TransporterPayment
from apps.expenses.models import Expense
from apps.farmers.models import Farmer
from apps.milk.models import MilkCollection, MilkRate
from apps.payments.models import Payment
from apps.sales.models import MilkSale
from apps.store.models import CashSale, CreditOrder

ZERO = Decimal("0")
ACCEPTED = F("litres") - F("rejected_litres")


def _day(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def period(p):
    """?month=2026-11, or ?start=&end=, default: this month so far."""
    today = timezone.localdate()
    if p.get("month"):
        y, m = (int(x) for x in p["month"].split("-"))
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        return date(y, m, 1), nxt - timedelta(days=1)
    return (_day(p["start"]) if p.get("start") else today.replace(day=1)), (_day(p["end"]) if p.get("end") else today)


def _q(x):
    return None if x is None else Decimal(str(x)).quantize(Decimal("0.01"))


def _sum(qs, field):
    return qs.aggregate(t=Sum(field))["t"] or ZERO


def litres_by_route(org, p):
    """Per route and day: accepted litres (the per-route totals), with the centre each route delivers to."""
    start, end = period(p)
    qs = (MilkCollection.objects.filter(organization=org, date__range=(start, end))
          .values("date", "route__name", "centre__name")
          .annotate(delivered=Sum("litres"), rejected=Sum("rejected_litres"), farmers=Count("farmer", distinct=True))
          .order_by("date", "route__name"))
    rows, by_route, rejected_total = [], {}, ZERO
    for r in qs:
        route, accepted = r["route__name"] or "No route", r["delivered"] - r["rejected"]
        rows.append([r["date"], route, r["centre__name"] or "-", accepted, r["rejected"], r["farmers"]])
        by_route[route] = by_route.get(route, ZERO) + accepted
        rejected_total += r["rejected"]
    return {"title": "Daily litres by route", "period": [start, end],
            "headers": ["Date", "Route", "Centre", "Accepted litres", "Rejected litres", "Farmers"], "rows": rows,
            "summary": {"Accepted litres": sum(by_route.values(), ZERO), "Rejected litres": rejected_total},
            "chart": [{"label": k, "value": v} for k, v in sorted(by_route.items(), key=lambda kv: -kv[1])]}


def route_sheets(org, p):
    """Every route sheet in the period: litres collected against litres received at the centre."""
    start, end = period(p)
    trips = (RouteTrip.objects.filter(organization=org, date__range=(start, end)).select_related("route__centre", "transporter")
             .annotate(delivered=Sum("collections__litres"), rejected=Sum("collections__rejected_litres"), farmers_n=Count("collections"))
             .order_by("date", "session", "route__name"))
    rows, by_route, accepted_total, matched_accepted, received_total = [], {}, ZERO, ZERO, ZERO
    for t in trips:
        accepted = (t.delivered or ZERO) - (t.rejected or ZERO)
        diff = None if t.received_litres is None else t.received_litres - accepted
        rows.append([t.date, t.get_session_display(), t.route.name, t.route.centre.name if t.route.centre else "-",
                     t.transporter.name if t.transporter else "-", t.farmers_n, t.delivered or ZERO, t.rejected or ZERO, accepted,
                     t.received_litres, diff, _q(diff / accepted * 100) if diff is not None and accepted else None, t.status])
        accepted_total += accepted
        by_route[t.route.name] = by_route.get(t.route.name, ZERO) + accepted
        if t.received_litres is not None:
            matched_accepted += accepted
            received_total += t.received_litres
    gap = received_total - matched_accepted
    return {"title": "Route sheets", "period": [start, end],
            "headers": ["Date", "Session", "Route", "Centre", "Transporter", "Farmers", "Delivered L", "Rejected L", "Accepted L",
                        "Received at centre L", "Difference L", "Difference %", "Status"], "rows": rows,
            "summary": {"Route sheets": len(rows), "Accepted litres collected": accepted_total, "Received at centre (closed sheets)": received_total,
                        "Difference on closed sheets": gap, "Loss % on closed sheets": _q(gap / matched_accepted * 100) if matched_accepted else None},
            "chart": [{"label": k, "value": v} for k, v in sorted(by_route.items(), key=lambda kv: -kv[1])]}


def centres(org, p):
    """Litres accepted and received per collection centre."""
    start, end = period(p)
    acc = {r["centre__name"] or "No centre": r["t"] for r in MilkCollection.objects.filter(organization=org, date__range=(start, end))
           .values("centre__name").annotate(t=Sum(ACCEPTED))}
    rec = {r["route__centre__name"] or "No centre": r["t"] for r in RouteTrip.objects.filter(
        organization=org, date__range=(start, end), status=RouteTrip.RECEIVED).values("route__centre__name").annotate(t=Sum("received_litres"))}
    n_routes = {r["centre__name"]: r["n"] for r in Route.objects.filter(organization=org, is_active=True).values("centre__name").annotate(n=Count("id"))}
    names = sorted(set(acc) | set(rec) | {c.name for c in CollectionCentre.objects.filter(organization=org, is_active=True)})
    rows = [[n, n_routes.get(n, 0), acc.get(n) or ZERO, rec.get(n) or ZERO] for n in names]
    return {"title": "Litres per collection centre", "period": [start, end],
            "headers": ["Centre", "Routes", "Accepted L collected", "Received at centre L (closed sheets)"], "rows": rows,
            "summary": {"Centres": len(names), "Accepted litres": sum((r[2] for r in rows), ZERO)},
            "chart": [{"label": r[0], "value": r[2]} for r in rows]}


def transporters(org, p):
    """What transporters carried and are owed for the period."""
    start, end = period(p)
    carried = {r["trip__transporter"]: r for r in MilkCollection.objects.filter(
        organization=org, trip__transporter__isnull=False, trip__date__range=(start, end))
        .values("trip__transporter").annotate(litres=Sum(ACCEPTED), trips=Count("trip", distinct=True))}
    paid = {r["transporter"]: r["t"] for r in TransporterPayment.objects.filter(organization=org, period_end__range=(start, end))
            .values("transporter").annotate(t=Sum("amount"))}
    rows, total = [], ZERO
    for t in Transporter.objects.filter(organization=org):
        c = carried.get(t.id)
        litres = (c["litres"] if c else ZERO) or ZERO
        due = (litres * t.rate_per_litre).quantize(Decimal("0.01"))
        total += due
        rows.append([t.name, t.vehicle_reg or "-", c["trips"] if c else 0, litres, t.rate_per_litre, due, paid.get(t.id) or ZERO])
    return {"title": "Transporters", "period": [start, end],
            "headers": ["Transporter", "Vehicle", "Trips", "Litres carried", "Rate / L", "Amount due", "Paid in period"], "rows": rows,
            "summary": {"Total due": total}, "chart": [{"label": r[0], "value": r[5]} for r in rows]}


def suppliers(org, p):
    start, end = period(p)
    n = max(1, int(p.get("limit") or 5))
    qs = (MilkCollection.objects.filter(organization=org, date__range=(start, end))
          .values("farmer_id", "farmer__member_no", "farmer__full_name", "farmer__route__name")
          .annotate(delivered=Sum("litres"), rejected=Sum("rejected_litres"), fat=Avg("fat_percent"),
                    protein=Avg("protein_percent"), days=Count("date", distinct=True)))
    data = sorted(({**r, "accepted": r["delivered"] - r["rejected"]} for r in qs), key=lambda r: -r["accepted"])
    rows = []
    for i, r in enumerate(data):
        group = "Top" if i < n else ("Bottom" if i >= len(data) - n else "")
        rej_pct = (r["rejected"] / r["delivered"] * 100) if r["delivered"] else ZERO
        rows.append([i + 1, r["farmer__member_no"], r["farmer__full_name"], r["farmer__route__name"] or "-", r["accepted"],
                     _q(rej_pct), _q(r["fat"]), _q(r["protein"]), r["days"], group])
    return {"title": f"Top and bottom suppliers (top/bottom {n})", "period": [start, end],
            "headers": ["Rank", "No.", "Farmer", "Route", "Accepted L", "Rejected %", "Avg fat %", "Avg protein %", "Days", "Group"],
            "rows": rows, "summary": {"Suppliers": len(data), "Total accepted litres": sum((r["accepted"] for r in data), ZERO)},
            "chart": [{"label": r["farmer__full_name"], "value": r["accepted"]} for r in data[:n]]}


def credit_exposure(org, p):
    """Feed credit and advances owed, against what each farmer's milk earns in a month."""
    today = timezone.localdate()
    rate = MilkRate.current(org)
    last30 = {r["farmer_id"]: r["t"] for r in
              MilkCollection.objects.filter(organization=org, date__gte=today - timedelta(days=30))
              .values("farmer_id").annotate(t=Sum(ACCEPTED))}
    adv = {r["farmer_id"]: r["t"] for r in
           Advance.objects.filter(organization=org, status=Advance.DISBURSED)
           .values("farmer_id").annotate(t=Sum(F("total_due") - F("amount_repaid")))}
    rows, tot_feed, tot_adv, high = [], ZERO, ZERO, 0
    for f in Farmer.objects.filter(organization=org, is_active=True).prefetch_related("orders"):
        feed, advance = f.credit_balance(), adv.get(f.id) or ZERO
        exposure = feed + advance
        if exposure <= 0:
            continue
        monthly = (last30.get(f.id) or ZERO) * rate
        risk = "HIGH" if monthly == 0 or exposure > monthly else ("WATCH" if exposure > monthly / 2 else "OK")
        high += risk == "HIGH"
        tot_feed, tot_adv = tot_feed + feed, tot_adv + advance
        rows.append([f.member_no, f.full_name, feed, advance, exposure, _q(monthly),
                     _q(exposure / monthly) if monthly else None, risk])
    rows.sort(key=lambda r: -r[4])
    return {"title": "Credit exposure by farmer", "period": [today, today],
            "headers": ["No.", "Farmer", "Feed credit", "Advances", "Total owed", "Milk value (last 30 days)", "Owed / monthly milk", "Risk"],
            "rows": rows, "summary": {"Feed credit owed": tot_feed, "Advances owed": tot_adv, "Total exposure": tot_feed + tot_adv,
                                      "Farmers at HIGH risk": high},
            "chart": [{"label": r[1], "value": r[4]} for r in rows[:8]]}


def _totals(org, start, end):
    milk_sales = _sum(MilkSale.objects.filter(organization=org, date__range=(start, end)), "total")
    feed_credit = _sum(CreditOrder.objects.filter(organization=org, created__date__range=(start, end)), "total_cost")
    pos = _sum(CashSale.objects.filter(organization=org, created__date__range=(start, end)), "total")
    pay = Payment.objects.filter(organization=org, period_end__range=(start, end))
    farmer_milk = _sum(pay, "gross")
    exp = {r["category"]: r["t"] for r in Expense.objects.filter(organization=org, date__range=(start, end))
           .values("category").annotate(t=Sum("amount"))}
    expenses = sum(exp.values(), ZERO)
    income, costs = milk_sales + feed_credit + pos, farmer_milk + expenses
    return {"milk_sales": milk_sales, "feed_credit": feed_credit, "pos": pos, "income": income, "farmer_milk": farmer_milk,
            "expenses_by_category": exp, "expenses": expenses, "costs": costs, "profit": income - costs,
            "paid_litres": _sum(pay, "litres")}


def financial(org, p):
    """Profit and loss for a month or any period, plus the payout-versus-income check."""
    start, end = period(p)
    t = _totals(org, start, end)
    collected = _sum(MilkCollection.objects.filter(organization=org, date__range=(start, end)), ACCEPTED)
    sold = _sum(MilkSale.objects.filter(organization=org, date__range=(start, end)), "litres")
    unsold = collected - sold
    owed_by_buyers = sum((s.balance for s in MilkSale.objects.filter(organization=org)), ZERO)
    owed_to_farmers = _sum(Payment.objects.filter(organization=org, status__in=["PENDING", "PROCESSING"]), "net")
    avg_buy = t["farmer_milk"] / t["paid_litres"] if t["paid_litres"] else None
    avg_sell = t["milk_sales"] / sold if sold else None
    rows = [["Income", "Milk sales to buyers", t["milk_sales"]], ["Income", "Feed sold on credit", t["feed_credit"]],
            ["Income", "Feed cash sales", t["pos"]], ["Income", "TOTAL INCOME", t["income"]],
            ["Costs", "Milk paid to farmers (incl. quality bonus)", t["farmer_milk"]]]
    labels = {"FEED_PURCHASE": "Feed purchases", "TRANSPORT": "Transport", "FUEL": "Fuel", "REPAIRS": "Repairs and maintenance",
              "UTILITIES": "Utilities", "VET": "Veterinary", "COOLING": "Cooling and storage", "SALARIES": "Salaries", "OTHER": "Other"}
    rows += [["Costs", labels.get(k, k), v] for k, v in sorted(t["expenses_by_category"].items(), key=lambda kv: -kv[1])]
    rows += [["Costs", "TOTAL COSTS", t["costs"]], ["Result", "PROFIT / (LOSS)", t["profit"]]]
    pct = lambda a, b: _q(a / b * 100) if b else None
    return {"title": "Profit and loss", "period": [start, end], "headers": ["Section", "Line", "KES"], "rows": rows,
            "summary": {"Total income": t["income"], "Total costs": t["costs"], "Profit / (loss)": t["profit"],
                        "Litres collected (accepted)": collected, "Litres sold": sold,
                        "Litres not sold (loss or stock)": unsold, "Loss % of collected": pct(unsold, collected),
                        "Farmer payout as % of milk sales": pct(t["farmer_milk"], t["milk_sales"]),
                        "Average price paid per litre": _q(avg_buy), "Average price sold per litre": _q(avg_sell),
                        "Margin per litre": _q(avg_sell - avg_buy) if avg_buy is not None and avg_sell is not None else None,
                        "Still owed by buyers": owed_by_buyers, "Still owed to farmers": owed_to_farmers},
            "chart": [{"label": "Income", "value": t["income"]}, {"label": "Costs", "value": t["costs"]},
                      {"label": "Profit", "value": t["profit"]}]}


def financial_trend(org, p):
    n = min(24, max(2, int(p.get("months") or 6)))
    today = timezone.localdate()
    y, m = today.year, today.month
    months = []
    for _ in range(n):
        months.append((y, m))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    rows = []
    for y, m in reversed(months):
        start = date(y, m, 1)
        end = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        t = _totals(org, start, end)
        rows.append([f"{y}-{m:02d}", t["income"], t["costs"], t["profit"]])
    return {"title": f"Monthly summary, last {n} months", "period": [None, today], "headers": ["Month", "Income", "Costs", "Profit"],
            "rows": rows, "summary": {"Total profit": sum((r[3] for r in rows), ZERO)},
            "chart": [{"label": r[0], "value": r[3]} for r in rows]}


REPORTS = {"litres-by-route": litres_by_route, "route-sheets": route_sheets, "centres": centres, "transporters": transporters, "suppliers": suppliers, "credit-exposure": credit_exposure,
           "financial": financial, "financial-trend": financial_trend}
