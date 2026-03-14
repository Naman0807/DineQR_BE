"""
PDF Generator for Bills — Jinja2 + xhtml2pdf
"""
import io
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

IST = timezone(timedelta(hours=5, minutes=30))

# Resolve the templates directory relative to this file
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
)


def generate_bill_pdf(
    restaurant_name: str,
    restaurant_address: str,
    restaurant_phone: str,
    table_number: int,
    bill_date: datetime,
    orders: List[dict],
    subtotal: Decimal,
    tax_amount: Decimal,
    discount_amount: Decimal,
    final_total: Decimal,
    payment_status: str,
    payment_method: str = None,
) -> bytes:
    """Generate a PDF bill and return bytes."""

    template = _jinja_env.get_template("invoice_template.html")

    html_string = template.render(
        restaurant_name=restaurant_name,
        restaurant_address=restaurant_address,
        restaurant_phone=restaurant_phone,
        table_number=table_number,
        bill_date=bill_date.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S"),
        orders=orders,
        subtotal=float(subtotal),
        tax_amount=float(tax_amount),
        discount_amount=float(discount_amount),
        final_total=float(final_total),
        payment_status=payment_status.upper(),
        payment_method=payment_method.upper() if payment_method else None,
        generated_at=datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
    )

    buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(
        io.BytesIO(html_string.encode("utf-8")),
        dest=buffer,
        encoding="utf-8"
    )

    if pisa_status.err:
        raise RuntimeError(f"xhtml2pdf failed to generate PDF: {pisa_status.err} error(s)")

    buffer.seek(0)
    return buffer.getvalue()
