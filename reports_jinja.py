from pathlib import Path
from typing import Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML, CSS

from .core import generate_preview
from .company import Company
from .storage import get_session
from .models import JournalEntry
from sqlmodel import select

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"])
)

CSS_PATH = TEMPLATES_DIR / "report.css"
AC_SEAL_PATH = Path(__file__).resolve().parent / "static" / "ac_seal.png"


def generate_pdf_from_preview(preview: dict, company: Optional[Company] = None, out_path: Optional[Path] = None) -> Path:
    """
    Render preview (dict from generate_preview) into HTML using Jinja2 and convert to PDF via WeasyPrint.
    """
    if out_path is None:
        out_path = Path("/tmp") / f"aqorath_report_{preview['template']}.pdf"

    template = env.get_template("report_template.html")
    html_str = template.render(preview=preview, company=company, ac_seal=str(AC_SEAL_PATH))
    html = HTML(string=html_str, base_url=str(TEMPLATES_DIR))
    css = CSS(filename=str(CSS_PATH)) if CSS_PATH.exists() else None
    if css:
        html.write_pdf(target=str(out_path), stylesheets=[css])
    else:
        html.write_pdf(target=str(out_path))
    return out_path


def generate_pdf_for_entry(entry_id: int, company_id: Optional[int] = None) -> Path:
    with get_session() as s:
        company = None
        if company_id:
            company = s.get(Company, company_id)
        je = s.get(JournalEntry, entry_id)
        if not je:
            raise ValueError("Entry not found")
        # If you have template-based preview call generate_preview(template_key, amount, ctx)
        # But here we'll produce a simple preview-like dict from DB
        lines = s.exec(select(je.__class__)).scalars().all()  # placeholder, better to query JournalLine
        # Use generate_preview externally when possible
    # For real use, prefer:
    # preview = generate_preview("ingreso_venta", amount, ctx)
    raise NotImplementedError("Use generate_pdf_from_preview(preview, company)")