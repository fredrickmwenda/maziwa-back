from core.documents import slip_pdf


def payment_slip_pdf(p):
    items = [(i.order.product.name, i.amount) for i in p.items.select_related("order__product")]
    return slip_pdf(p.organization.name, f"Milk payment: {p.period_start} to {p.period_end}", [
        ("Farmer", f"{p.farmer.member_no} {p.farmer.full_name}"), ("Litres accepted", p.litres),
        ("Litres rejected", p.rejected_litres), ("Price per litre (KES)", p.rate), ("Quality bonus (KES)", p.bonus),
        ("Milk value (KES)", p.gross), ("Deductions (KES)", p.deductions), ("  of which advances (KES)", p.advance_deductions),
        ("NET PAID (KES)", p.net), ("Status", p.status), ("Reference", p.reference)],
        "Feed credit deducted (KES)", items)
