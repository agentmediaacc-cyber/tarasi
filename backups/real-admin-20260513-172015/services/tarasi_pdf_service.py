import os, qrcode
from pathlib import Path
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from services.tarasi_bot_service import COMPANY, ticket_number

BASE_DIR = Path(__file__).resolve().parent.parent
QUOTE_DIR = BASE_DIR / "static" / "generated" / "quotes"
QUOTE_DIR.mkdir(parents=True, exist_ok=True)

def money(value):
    try:
        return f"N$ {float(value):,.2f}"
    except Exception:
        return "N$ 0.00"

def generate_quote_pdf(data, base_url=""):
    ref = data.get("reference") or ticket_number("TRQ")
    issue_date = datetime.now()
    expiry_date = issue_date + timedelta(days=7)

    filename = f"{ref}.pdf"
    pdf_path = QUOTE_DIR / filename

    preview_url = f"{base_url.rstrip('/')}/quote/preview/{ref}" if base_url else f"/quote/preview/{ref}"
    qr_path = QUOTE_DIR / f"{ref}-qr.png"
    qrcode.make(preview_url).save(qr_path)

    price = float(data.get("estimated_price") or 0)
    subtotal = price
    total = subtotal

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=16*mm,
        leftMargin=16*mm,
        topMargin=14*mm,
        bottomMargin=14*mm
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=styles["Title"], fontSize=24, textColor=colors.HexColor("#063b34"), alignment=TA_CENTER, spaceAfter=8)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#5d6b64"))
    normal = ParagraphStyle("normal", parent=styles["Normal"], fontSize=10, leading=14)
    heading = ParagraphStyle("heading", parent=styles["Heading2"], fontSize=14, textColor=colors.HexColor("#063b34"))

    story = []

    header = Table([
        [
            Paragraph(f"<b>{COMPANY['name']}</b><br/>{COMPANY['po_box']}<br/>{COMPANY['email']}<br/>TIN: {COMPANY['tin']}<br/>Reg No: {COMPANY['reg_no']}", normal),
            Paragraph("<b>PREMIUM QUOTATION</b><br/>Trackable • QR Verified", title)
        ]
    ], colWidths=[95*mm, 75*mm])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#fff6e6")),
        ("BOX", (0,0), (-1,-1), 1, colors.HexColor("#d9a441")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("PADDING", (0,0), (-1,-1), 12),
    ]))
    story.append(header)
    story.append(Spacer(1, 10))

    meta = Table([
        ["Reference", ref, "Status", data.get("status", "Pending")],
        ["Issue Date", issue_date.strftime("%d %B %Y"), "Expiry Date", expiry_date.strftime("%d %B %Y")],
        ["Client", data.get("client_name", "Client"), "Phone", data.get("phone", "")],
        ["Email", data.get("email", ""), "Service", data.get("service_type", "Transport").title()],
    ], colWidths=[32*mm, 58*mm, 32*mm, 48*mm])
    meta.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), .5, colors.HexColor("#e5d6b8")),
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#063b34")),
        ("BACKGROUND", (2,0), (2,-1), colors.HexColor("#063b34")),
        ("TEXTCOLOR", (0,0), (0,-1), colors.white),
        ("TEXTCOLOR", (2,0), (2,-1), colors.white),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"),
        ("PADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(meta)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Journey Details", heading))
    journey = Table([
        ["Pickup", data.get("pickup", "")],
        ["Drop-off", data.get("dropoff", "")],
        ["Travel Date", data.get("travel_date", "")],
        ["Passengers", str(data.get("passengers", "1"))],
        ["Vehicle", data.get("vehicle", "Sedan").title()],
        ["Notes", data.get("notes", "Premium Tarasi transport quotation.")],
    ], colWidths=[42*mm, 128*mm])
    journey.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), .5, colors.HexColor("#e5d6b8")),
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#fff1cc")),
        ("PADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(journey)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Price Summary", heading))
    price_table = Table([
        ["Description", "Amount"],
        [f"{data.get('service_type','Transport').title()} service - {data.get('vehicle','Sedan').title()}", money(subtotal)],
        ["Total Due", money(total)],
    ], colWidths=[125*mm, 45*mm])
    price_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#063b34")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#d9a441")),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"),
        ("GRID", (0,0), (-1,-1), .5, colors.HexColor("#d7c28e")),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
        ("PADDING", (0,0), (-1,-1), 9),
    ]))
    story.append(price_table)
    story.append(Spacer(1, 14))

    banking = Table([
        [
            Paragraph(
                f"<b>Banking Details</b><br/>"
                f"Bank: {COMPANY['bank']}<br/>"
                f"Account Name: {COMPANY['account_name']}<br/>"
                f"Account Number: {COMPANY['account_number']}<br/>"
                f"Branch: {COMPANY['branch']}<br/>"
                f"Branch Code: {COMPANY['branch_code']}<br/>"
                f"Use reference: <b>{ref}</b>",
                normal
            ),
            Image(str(qr_path), width=34*mm, height=34*mm)
        ]
    ], colWidths=[125*mm, 45*mm])
    banking.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 1, colors.HexColor("#063b34")),
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#fffaf0")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("PADDING", (0,0), (-1,-1), 10),
    ]))
    story.append(banking)
    story.append(Spacer(1, 12))

    story.append(Paragraph(
        "This quotation is system-generated and trackable. Final confirmation depends on vehicle availability, "
        "route conditions, waiting time, special requests and payment confirmation.",
        small
    ))

    doc.build(story)

    return {
        "reference": ref,
        "pdf_url": f"/static/generated/quotes/{filename}",
        "preview_url": preview_url,
        "expires": expiry_date.strftime("%Y-%m-%d"),
    }
