from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

OUTPUT_DIR = "data/generated_docs"

def generate_quote_pdf(quote_data: dict[str, Any]) -> str:
    """Generates a premium PDF quotation."""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
    filename = f"Quotation_{quote_data.get('quote_number', 'UNSET')}.pdf"
    file_path = os.path.join(OUTPUT_DIR, filename)
    
    doc = SimpleDocTemplate(file_path, pagesize=A4)
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor("#000000"),
        alignment=1, # Center
        spaceAfter=20
    )
    
    elements = []
    
    # Header
    elements.append(Paragraph("Tarasi Shuttle and Transfer Services CC", title_style))
    elements.append(Paragraph("Premium Namibia Transport Concierge", styles['Normal']))
    elements.append(Spacer(1, 10))
    
    # Company Info
    company_info = [
        ["TIN:", "15733730-011"],
        ["Reg No:", "CC/2025/11107"],
        ["Email:", "tarasishuttle@gmail.com"],
        ["Date:", datetime.now().strftime("%Y-%m-%d")],
        ["Valid Until:", (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")]
    ]
    
    t = Table(company_info, colWidths=[100, 300])
    t.setStyle(TableStyle([
        ('TEXTCOLOR', (0,0), (0,-1), colors.grey),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 20))
    
    # Quote Details Title
    elements.append(Paragraph(f"QUOTATION: {quote_data.get('quote_number')}", styles['Heading2']))
    elements.append(Spacer(1, 10))
    
    # Quote Table
    quote_info = [
        ["Description", "Details"],
        ["Pickup:", quote_data.get("pickup_text", "N/A")],
        ["Drop-off:", quote_data.get("dropoff_text", "N/A")],
        ["Vehicle:", str(quote_data.get("vehicle_type", "sedan")).upper()],
        ["Passengers:", str(quote_data.get("passengers", 1))],
        ["Distance:", f"{quote_data.get('distance_km', 0)} km"],
        ["Service:", str(quote_data.get("service_type", "town")).title()]
    ]
    
    qt = Table(quote_info, colWidths=[150, 350])
    qt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.black),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 11),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('GRID', (0,0), (-1,-1), 1, colors.grey)
    ]))
    elements.append(qt)
    elements.append(Spacer(1, 20))
    
    # Total Amount
    total_style = ParagraphStyle(
        'TotalStyle',
        parent=styles['Normal'],
        fontSize=14,
        fontName='Helvetica-Bold',
        alignment=2 # Right
    )
    elements.append(Paragraph(f"TOTAL AMOUNT: N${quote_data.get('final_price', 0):.2f}", total_style))
    elements.append(Spacer(1, 30))
    
    # Banking Details
    elements.append(Paragraph("Banking Details for Payment:", styles['Heading3']))
    bank_info = [
        ["Bank:", "First National Bank (FNB)"],
        ["Account Name:", "Tarasi Shuttle and Transfer Services CC"],
        ["Account Number:", "64289981259"],
        ["Branch:", "Maerua Mall"],
        ["Branch Code:", "282273"]
    ]
    bt = Table(bank_info, colWidths=[150, 350])
    bt.setStyle(TableStyle([
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('TEXTCOLOR', (0,0), (0,-1), colors.darkgrey),
    ]))
    elements.append(bt)
    
    elements.append(Spacer(1, 40))
    elements.append(Paragraph("Thank you for choosing Tarasi. We look forward to driving you.", styles['Italic']))
    
    doc.build(elements)
    return file_path
