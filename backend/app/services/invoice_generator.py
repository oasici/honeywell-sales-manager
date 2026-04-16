"""PDF invoice generation using Jinja2 and WeasyPrint."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.core.config import settings

logger = logging.getLogger(__name__)

INVOICES_DIR: str = "data/invoices"

_ENGLISH_MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_TURKISH_MONTHS = [
    "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]


def _format_bilingual_date(date_obj: datetime) -> str:
    """Format date as 'March 30, 2026 - 30 Mart 2026'."""
    en_month = _ENGLISH_MONTHS[date_obj.month]
    tr_month = _TURKISH_MONTHS[date_obj.month]
    en_part = f"{en_month} {date_obj.day}, {date_obj.year}"
    tr_part = f"{date_obj.day} {tr_month} {date_obj.year}"
    return f"{en_part} - {tr_part}"


_LABELS = {
    "tr": {
        "title": "FATURA",
        "invoice_number": "Fatura No",
        "date": "Tarih",
        "due_date": "Son Ödeme",
        "customer": "Müşteri",
        "company": "Firma",
        "item_no": "S.No",
        "description": "Açıklama",
        "quantity": "Miktar",
        "unit_price": "Birim Fiyat",
        "line_total": "Toplam",
        "subtotal": "Ara Toplam",
        "tax": "KDV",
        "grand_total": "Genel Toplam",
        "notes": "Notlar",
        "currency": "Para Birimi",
        "payment_note": "Lütfen son ödeme tarihine kadar ödeme yapınız.",
    },
    "en": {
        "title": "INVOICE",
        "invoice_number": "Invoice No",
        "date": "Date",
        "due_date": "Due Date",
        "customer": "Customer",
        "company": "Company",
        "item_no": "No",
        "description": "Description",
        "quantity": "Qty",
        "unit_price": "Unit Price",
        "line_total": "Total",
        "subtotal": "Subtotal",
        "tax": "Tax",
        "grand_total": "Grand Total",
        "notes": "Notes",
        "currency": "Currency",
        "payment_note": "Please make payment by the due date.",
    },
}

_DEFAULT_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: 'Helvetica Neue', Arial, sans-serif; margin: 40px; color: #333; font-size: 12px; }
  .header { display: flex; justify-content: space-between; border-bottom: 3px solid #c8102e; padding-bottom: 15px; margin-bottom: 20px; }
  .company-info { text-align: right; font-size: 11px; color: #666; }
  .company-name { font-size: 18px; font-weight: bold; color: #c8102e; }
  .invoice-meta { margin-bottom: 20px; }
  .invoice-meta table { border-collapse: collapse; }
  .invoice-meta td { padding: 3px 12px 3px 0; }
  .invoice-meta td:first-child { font-weight: bold; }
  table.items { width: 100%; border-collapse: collapse; margin: 20px 0; }
  table.items th { background: #c8102e; color: white; padding: 8px; text-align: left; font-size: 11px; }
  table.items td { padding: 6px 8px; border-bottom: 1px solid #ddd; }
  table.items tr:nth-child(even) { background: #f9f9f9; }
  .totals { margin-left: auto; width: 300px; }
  .totals table { width: 100%; border-collapse: collapse; }
  .totals td { padding: 4px 8px; }
  .totals .grand-total { font-weight: bold; font-size: 14px; border-top: 2px solid #333; }
  .notes { margin-top: 30px; padding: 10px; background: #f5f5f5; border-left: 3px solid #c8102e; }
  .footer { margin-top: 40px; font-size: 10px; color: #999; text-align: center; border-top: 1px solid #ddd; padding-top: 10px; }
</style>
</head>
<body>
  <div class="header">
    <div>
      <div class="company-name">{{ company_name }}</div>
      <div>{{ company_address }}</div>
      <div>{{ company_phone }}</div>
    </div>
    <div class="company-info">
      <h1 style="margin:0; color:#c8102e;">{{ labels.title }}</h1>
    </div>
  </div>

  <div class="invoice-meta">
    <table>
      <tr><td>{{ labels.invoice_number }}:</td><td>{{ invoice_number }}</td></tr>
      <tr><td>{{ labels.date }}:</td><td>{{ issue_date }}</td></tr>
      {% if due_date %}<tr><td>{{ labels.due_date }}:</td><td>{{ due_date }}</td></tr>{% endif %}
      <tr><td>{{ labels.currency }}:</td><td>{{ currency }}</td></tr>
      {% if customer_name %}<tr><td>{{ labels.customer }}:</td><td>{{ customer_name }}</td></tr>{% endif %}
      {% if customer_company %}<tr><td>{{ labels.company }}:</td><td>{{ customer_company }}</td></tr>{% endif %}
    </table>
  </div>

  <table class="items">
    <thead>
      <tr>
        <th>{{ labels.item_no }}</th>
        <th>{{ labels.description }}</th>
        <th>{{ labels.quantity }}</th>
        <th>{{ labels.unit_price }}</th>
        <th>{{ labels.line_total }}</th>
      </tr>
    </thead>
    <tbody>
      {% for item in items %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>{{ item.description or '-' }}</td>
        <td>{{ item.quantity }}</td>
        <td>{{ "%.2f"|format(item.unit_price) }}</td>
        <td>{{ "%.2f"|format(item.total) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <div class="totals">
    <table>
      <tr><td>{{ labels.subtotal }}:</td><td style="text-align:right">{{ "%.2f"|format(subtotal) }} {{ currency }}</td></tr>
      <tr><td>{{ labels.tax }} ({{ "%.0f"|format(tax_rate) }}%):</td><td style="text-align:right">{{ "%.2f"|format(tax_amount) }} {{ currency }}</td></tr>
      <tr class="grand-total"><td>{{ labels.grand_total }}:</td><td style="text-align:right">{{ "%.2f"|format(grand_total) }} {{ currency }}</td></tr>
    </table>
  </div>

  {% if notes %}
  <div class="notes">
    <strong>{{ labels.notes }}:</strong><br>
    {{ notes }}
  </div>
  {% endif %}

  <div class="footer">
    {{ labels.payment_note }}<br>
    {{ company_name }} | {{ company_address }} | {{ company_phone }}
  </div>
</body>
</html>
"""


async def generate_invoice_pdf(invoice_data: dict, language: str = "tr") -> str:
    """Generate PDF invoice using Jinja2 + WeasyPrint.

    Args:
        invoice_data: Dict containing invoice_number, items, subtotal, etc.
        language: 'tr' or 'en'.

    Returns:
        File path of generated PDF (or HTML as fallback).
    """
    labels = _LABELS.get(language, _LABELS["en"])

    issue_date = invoice_data.get("issue_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    try:
        issue_dt = datetime.strptime(issue_date[:10], "%Y-%m-%d")
        bilingual_date = _format_bilingual_date(issue_dt)
    except (ValueError, TypeError):
        bilingual_date = issue_date

    template_context = {
        "labels": labels,
        "company_name": settings.COMPANY_NAME,
        "company_address": settings.COMPANY_ADDRESS,
        "company_phone": settings.COMPANY_PHONE,
        "invoice_number": invoice_data.get("invoice_number", ""),
        "issue_date": issue_date,
        "due_date": invoice_data.get("due_date", ""),
        "bilingual_date": bilingual_date,
        "currency": invoice_data.get("currency", settings.DEFAULT_CURRENCY),
        "customer_name": invoice_data.get("customer_name", ""),
        "customer_company": invoice_data.get("customer_company", ""),
        "items": invoice_data.get("items", []),
        "subtotal": invoice_data.get("subtotal", 0),
        "tax_rate": invoice_data.get("tax_rate", settings.DEFAULT_TAX_RATE),
        "tax_amount": invoice_data.get("tax_amount", 0),
        "grand_total": invoice_data.get("grand_total", 0),
        "notes": invoice_data.get("notes", ""),
    }

    html_content = _render_template(template_context)

    invoices_dir = Path(INVOICES_DIR)
    invoices_dir.mkdir(parents=True, exist_ok=True)

    invoice_number = invoice_data.get("invoice_number", "DRAFT")
    safe_name = invoice_number.replace("/", "-").replace("\\", "-")

    try:
        import asyncio

        from weasyprint import HTML as WeasyHTML

        pdf_path = str(invoices_dir / f"{safe_name}.pdf")
        await asyncio.to_thread(WeasyHTML(string=html_content).write_pdf, pdf_path)
        logger.info("Generated PDF invoice: %s", pdf_path)
        return pdf_path
    except ImportError:
        logger.warning("WeasyPrint not available, falling back to HTML output")
    except Exception as exc:
        logger.error("WeasyPrint PDF generation failed: %s", exc)

    html_path = str(invoices_dir / f"{safe_name}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info("Generated HTML invoice (PDF fallback): %s", html_path)
    return html_path


def _render_template(context: dict) -> str:
    """Render the invoice HTML template, falling back to the built-in default."""
    templates_dir = Path(settings.TEMPLATES_DIR)
    language = "tr"  # default; caller may pass pre-resolved labels
    for lang in ("tr", "en"):
        candidate = templates_dir / f"honeywell_invoice_{lang}.html"
        if candidate.exists():
            env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
            return env.get_template(f"honeywell_invoice_{lang}.html").render(**context)

    template_file = templates_dir / "invoice_template.html"
    if template_file.exists():
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
        return env.get_template("invoice_template.html").render(**context)

    env = Environment(autoescape=True)
    return env.from_string(_DEFAULT_HTML_TEMPLATE).render(**context)
