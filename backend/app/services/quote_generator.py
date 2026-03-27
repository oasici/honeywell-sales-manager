"""PDF quote generation using Jinja2 and WeasyPrint."""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.core.config import settings

logger = logging.getLogger(__name__)

# Labels for bilingual support
_LABELS = {
    "tr": {
        "title": "TEKLİF",
        "quote_number": "Teklif No",
        "date": "Tarih",
        "valid_until": "Geçerlilik",
        "customer": "Müşteri",
        "company": "Firma",
        "item_no": "S.No",
        "part_code": "Parça Kodu",
        "description": "Açıklama",
        "quantity": "Miktar",
        "unit_price": "Birim Fiyat",
        "discount": "İndirim %",
        "line_total": "Toplam",
        "subtotal": "Ara Toplam",
        "discount_total": "İndirim Toplamı",
        "tax": "KDV",
        "grand_total": "Genel Toplam",
        "notes": "Notlar",
        "currency": "Para Birimi",
        "prepared_by": "Hazırlayan",
        "validity_note": "Bu teklif {days} gün geçerlidir.",
    },
    "en": {
        "title": "QUOTATION",
        "quote_number": "Quote No",
        "date": "Date",
        "valid_until": "Valid Until",
        "customer": "Customer",
        "company": "Company",
        "item_no": "No",
        "part_code": "Part Code",
        "description": "Description",
        "quantity": "Qty",
        "unit_price": "Unit Price",
        "discount": "Disc. %",
        "line_total": "Total",
        "subtotal": "Subtotal",
        "discount_total": "Discount Total",
        "tax": "Tax",
        "grand_total": "Grand Total",
        "notes": "Notes",
        "currency": "Currency",
        "prepared_by": "Prepared By",
        "validity_note": "This quotation is valid for {days} days.",
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
  .quote-meta { margin-bottom: 20px; }
  .quote-meta table { border-collapse: collapse; }
  .quote-meta td { padding: 3px 12px 3px 0; }
  .quote-meta td:first-child { font-weight: bold; }
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

  <div class="quote-meta">
    <table>
      <tr><td>{{ labels.quote_number }}:</td><td>{{ quote_number }}</td></tr>
      <tr><td>{{ labels.date }}:</td><td>{{ created_date }}</td></tr>
      <tr><td>{{ labels.valid_until }}:</td><td>{{ valid_until }}</td></tr>
      <tr><td>{{ labels.currency }}:</td><td>{{ currency }}</td></tr>
      {% if customer_name %}<tr><td>{{ labels.customer }}:</td><td>{{ customer_name }}</td></tr>{% endif %}
      {% if customer_company %}<tr><td>{{ labels.company }}:</td><td>{{ customer_company }}</td></tr>{% endif %}
    </table>
  </div>

  <table class="items">
    <thead>
      <tr>
        <th>{{ labels.item_no }}</th>
        <th>{{ labels.part_code }}</th>
        <th>{{ labels.description }}</th>
        <th>{{ labels.quantity }}</th>
        <th>{{ labels.unit_price }}</th>
        <th>{{ labels.discount }}</th>
        <th>{{ labels.line_total }}</th>
      </tr>
    </thead>
    <tbody>
      {% for item in items %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>{{ item.honeywell_code or '-' }}</td>
        <td>{{ item.description or '-' }}</td>
        <td>{{ item.quantity }}</td>
        <td>{{ "%.2f"|format(item.unit_price) }}</td>
        <td>{{ "%.1f"|format(item.discount_pct) }}%</td>
        <td>{{ "%.2f"|format(item.line_total) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <div class="totals">
    <table>
      <tr><td>{{ labels.subtotal }}:</td><td style="text-align:right">{{ "%.2f"|format(subtotal) }} {{ currency }}</td></tr>
      {% if discount_total > 0 %}
      <tr><td>{{ labels.discount_total }}:</td><td style="text-align:right">-{{ "%.2f"|format(discount_total) }} {{ currency }}</td></tr>
      {% endif %}
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
    {{ validity_note }}<br>
    {{ company_name }} | {{ company_address }} | {{ company_phone }}
  </div>
</body>
</html>
"""


async def generate_quote_pdf(quote_data: dict, language: str = "tr") -> str:
    """Generate PDF quote using Jinja2 + WeasyPrint.

    Args:
        quote_data: Dict containing quote_number, items, subtotal, etc.
        language: 'tr' or 'en'.

    Returns:
        File path of generated PDF (or HTML as fallback).
    """
    labels = _LABELS.get(language, _LABELS["en"])

    # Calculate valid_until
    valid_days = quote_data.get("valid_days", settings.QUOTE_VALIDITY_DAYS)
    created_date = quote_data.get("created_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    try:
        created_dt = datetime.strptime(created_date, "%Y-%m-%d")
        valid_until = (created_dt + timedelta(days=valid_days)).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        valid_until = ""

    validity_note = labels["validity_note"].format(days=valid_days)

    template_context = {
        "labels": labels,
        "company_name": settings.COMPANY_NAME,
        "company_address": settings.COMPANY_ADDRESS,
        "company_phone": settings.COMPANY_PHONE,
        "quote_number": quote_data.get("quote_number", ""),
        "created_date": created_date,
        "valid_until": valid_until,
        "currency": quote_data.get("currency", settings.DEFAULT_CURRENCY),
        "customer_name": quote_data.get("customer_name", ""),
        "customer_company": quote_data.get("customer_company", ""),
        "items": quote_data.get("items", []),
        "subtotal": quote_data.get("subtotal", 0),
        "discount_total": quote_data.get("discount_total", 0),
        "tax_rate": quote_data.get("tax_rate", settings.DEFAULT_TAX_RATE),
        "tax_amount": quote_data.get("tax_amount", 0),
        "grand_total": quote_data.get("grand_total", 0),
        "notes": quote_data.get("notes", ""),
        "validity_note": validity_note,
    }

    # Try to load custom template, fall back to built-in
    html_content = _render_template(template_context)

    # Ensure output directory exists
    quotes_dir = Path(settings.QUOTES_DIR)
    quotes_dir.mkdir(parents=True, exist_ok=True)

    quote_number = quote_data.get("quote_number", "DRAFT")
    safe_name = quote_number.replace("/", "-").replace("\\", "-")

    # Try WeasyPrint for PDF
    try:
        from weasyprint import HTML as WeasyHTML

        pdf_path = str(quotes_dir / f"{safe_name}.pdf")
        WeasyHTML(string=html_content).write_pdf(pdf_path)
        logger.info("Generated PDF quote: %s", pdf_path)
        return pdf_path
    except ImportError:
        logger.warning("WeasyPrint not available, falling back to HTML output")
    except Exception as exc:
        logger.error("WeasyPrint PDF generation failed: %s", exc)

    # Fallback: save as HTML
    html_path = str(quotes_dir / f"{safe_name}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info("Generated HTML quote (PDF fallback): %s", html_path)
    return html_path


def _render_template(context: dict) -> str:
    """Render the quote HTML template."""
    templates_dir = Path(settings.TEMPLATES_DIR)
    template_file = templates_dir / "quote_template.html"

    if template_file.exists():
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=True,
        )
        template = env.get_template("quote_template.html")
        return template.render(**context)

    # Use built-in default template
    env = Environment(autoescape=True)
    template = env.from_string(_DEFAULT_HTML_TEMPLATE)
    return template.render(**context)
