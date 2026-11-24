import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HEADERS = ["No.", "Farmer", "Phone", "Litres", "Fat %", "Protein %", "Alcohol test OK", "Rejected L", "Signature"]


def route_sheet_pdf(trip, lines):
    """Printable sheet for the transporter: farmers on the route with room to write litres and sign."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    st = getSampleStyleSheet()
    centre = trip.route.centre.name if trip.route.centre else "-"
    transporter = trip.transporter.name if trip.transporter else "-"
    out = [Paragraph(f"<b>{escape(trip.organization.name)}</b>: route sheet", st["Title"]),
           Paragraph(escape(f"Route: {trip.route.name}    Centre: {centre}    Date: {trip.date} ({trip.get_session_display()})    "
                            f"Transporter: {transporter}    Vehicle: {trip.vehicle_reg or '-'}"), st["Normal"]), Spacer(1, 8)]
    data, total = [HEADERS], 0
    for f, c in lines:
        total += c.litres if c else 0
        data.append([f.member_no, f.full_name, f.phone, str(c.litres) if c else "", str(c.fat_percent or "") if c else "",
                     str(c.protein_percent or "") if c else "",
                     ("No" if not c.alcohol_passed else "Yes") if c else "", str(c.rejected_litres) if c and c.rejected_litres else "", ""])
    data.append(["", "TOTAL", "", str(total) if total else "", "", "", "", "", ""])
    widths = [20 * mm, 55 * mm, 32 * mm, 24 * mm, 18 * mm, 22 * mm, 28 * mm, 24 * mm, 38 * mm]
    t = Table(data, colWidths=widths, rowHeights=[8 * mm] + [10 * mm] * (len(data) - 1), repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f6b3f")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]))
    out += [t, Spacer(1, 14), Paragraph("Received at centre (litres): ____________    Temperature: ______    "
                                        "Transporter signature: ________________    Centre clerk signature: ________________", st["Normal"])]
    doc.build(out)
    return buf.getvalue()
