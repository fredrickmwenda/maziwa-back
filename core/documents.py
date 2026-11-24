"""CSV and PDF building blocks shared by reports, payslips and payment slips."""
import csv
import io
from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def as_text(v):
    return "" if v is None else str(v)


def safe_cell(v):
    """Stop spreadsheet formula injection from user-typed text."""
    v = as_text(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@") and not v.replace(".", "", 1).lstrip("-+").isdigit() else v


def csv_bytes(headers, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow([safe_cell(c) for c in r])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")  # BOM so Excel reads UTF-8


def new_doc(buf, landscape_mode=True):
    size = landscape(A4) if landscape_mode else A4
    return SimpleDocTemplate(buf, pagesize=size, leftMargin=15 * mm, rightMargin=15 * mm,
                             topMargin=15 * mm, bottomMargin=15 * mm), size


def pdf_table(org_name, title, p, headers, rows):
    buf = io.BytesIO()
    doc, size = new_doc(buf)
    st = getSampleStyleSheet()
    cell = ParagraphStyle("c", parent=st["BodyText"], fontSize=7.5, leading=9)
    head = ParagraphStyle("h", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
    rng = f" ({p.get('start') or '...'} to {p.get('end') or '...'})" if p.get("start") or p.get("end") else ""
    out = [Paragraph(f"<b>{escape(org_name)}</b>", st["Title"]),
           Paragraph(f"{escape(title)}{escape(rng)} - generated {timezone.localdate()}", st["Normal"]), Spacer(1, 6)]
    data = [[Paragraph(escape(h), head) for h in headers]] + [[Paragraph(escape(as_text(c)), cell) for c in r] for r in rows]
    width = (size[0] - 30 * mm) / len(headers)
    t = Table(data, colWidths=[width] * len(headers), repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f6b3f")),
                           ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f1ea")])]))
    out.append(t)
    doc.build(out)
    return buf.getvalue()


def slip_pdf(org_name, heading, lines, items_title=None, items=None):
    buf = io.BytesIO()
    doc, _ = new_doc(buf, landscape_mode=False)
    st = getSampleStyleSheet()
    out = [Paragraph(f"<b>{escape(org_name)}</b>", st["Title"]), Paragraph(escape(heading), st["Heading2"]), Spacer(1, 8)]
    t = Table([[a, as_text(b)] for a, b in lines], colWidths=[60 * mm, 100 * mm])
    t.setStyle(TableStyle([("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey)]))
    out.append(t)
    if items:
        out += [Spacer(1, 10), Paragraph(escape(items_title), st["Heading3"])]
        t2 = Table([[a, as_text(b)] for a, b in items], colWidths=[100 * mm, 60 * mm])
        t2.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey)]))
        out.append(t2)
    out += [Spacer(1, 14), Paragraph(f"Generated {timezone.localdate()}", st["Italic"])]
    doc.build(out)
    return buf.getvalue()


def file_response(data, content_type, filename):
    r = HttpResponse(data, content_type=content_type)
    r["Content-Disposition"] = f'attachment; filename="{filename}"'
    return r


def report_pdf(org_name, title, subtitle, summary, tables):
    """A portrait PDF with a summary block and any number of titled tables.
    summary: [(label, value)]; tables: [(name, headers, rows)]."""
    buf = io.BytesIO()
    doc, size = new_doc(buf, landscape_mode=False)
    st = getSampleStyleSheet()
    cell = ParagraphStyle("c2", parent=st["BodyText"], fontSize=7.5, leading=9)
    head = ParagraphStyle("h2", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
    out = [Paragraph(f"<b>{escape(org_name)}</b>", st["Title"]), Paragraph(escape(title), st["Heading2"]),
           Paragraph(escape(subtitle), st["Normal"]), Spacer(1, 8)]
    if summary:
        t = Table([[a, as_text(b)] for a, b in summary], colWidths=[70 * mm, 90 * mm])
        t.setStyle(TableStyle([("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                               ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey)]))
        out.append(t)
    for name, headers, rows in tables:
        if not rows:
            continue
        out += [Spacer(1, 10), Paragraph(escape(name), st["Heading3"])]
        data = [[Paragraph(escape(h), head) for h in headers]] + [[Paragraph(escape(as_text(c)), cell) for c in r] for r in rows]
        width = (size[0] - 30 * mm) / len(headers)
        tb = Table(data, colWidths=[width] * len(headers), repeatRows=1)
        tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f6b3f")),
                                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f1ea")])]))
        out.append(tb)
    doc.build(out)
    return buf.getvalue()
