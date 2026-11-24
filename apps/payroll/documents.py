from core.documents import slip_pdf


def payslip_pdf(e):
    return slip_pdf(e.organization.name, f"Payslip: {e.month:%B %Y}", [
        ("Name", e.member.display_name), ("Role", e.member.role.name), ("Job title", e.member.job_title),
        ("Basic salary (KES)", e.basic), ("Allowances (KES)", e.allowances), ("Deductions (KES)", e.deductions),
        ("NET PAY (KES)", e.net), ("Status", e.status), ("Reference", e.reference)])
