"""Pure in-memory PDF renderer for coherent formal financial statements.

The renderer consumes only a supplied :class:`FinancialStatementsBundle`. It
owns presentation and pagination, not accounting semantics, authority discovery,
or persistence. Monetary values are rendered from ``Decimal`` objects via their
exact string representation; no float conversion or statement recalculation is
performed here.
"""

from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .financial_statements import FinancialStatementsBundle


_LEFT = 50
_CODE_X = 50
_NAME_X = 110
_SUBTYPE_X = 365
_AMOUNT_X = 562
_TOP = 742
_BOTTOM = 54
_ROW = 15


class _StatementWriter:
    def __init__(self, pdf):
        self.pdf = pdf
        self.y = _TOP
        self.title = ""
        self.as_of = None
        self.started = False

    def _header(self, *, continuation=False):
        title = self.title
        if continuation:
            title = f"{title} - continuacion"
        self.pdf.setFont("Helvetica-Bold", 15)
        self.pdf.drawString(_LEFT, self.y, title)
        self.y -= 22

        self.pdf.setFont("Helvetica", 10)
        cutoff = "" if self.as_of is None else str(self.as_of)
        self.pdf.drawString(_LEFT, self.y, f"Al: {cutoff}")
        self.y -= 22

        self.pdf.setFont("Helvetica-Bold", 9)
        self.pdf.drawString(_CODE_X, self.y, "Codigo")
        self.pdf.drawString(_NAME_X, self.y, "Cuenta")
        self.pdf.drawString(_SUBTYPE_X, self.y, "Subtipo")
        self.pdf.drawRightString(_AMOUNT_X, self.y, "Importe")
        self.y -= _ROW
        self.pdf.line(_LEFT, self.y + 5, _AMOUNT_X, self.y + 5)

    def start_statement(self, title, as_of):
        if self.started:
            self.pdf.showPage()
        self.started = True
        self.title = title
        self.as_of = as_of
        self.y = _TOP
        self._header()

    def _ensure(self, rows=1):
        if self.y - (_ROW * rows) >= _BOTTOM:
            return
        self.pdf.showPage()
        self.y = _TOP
        self._header(continuation=True)

    def section(self, label):
        self._ensure(2)
        self.y -= 5
        self.pdf.setFont("Helvetica-Bold", 10)
        self.pdf.drawString(_LEFT, self.y, label)
        self.y -= _ROW

    def line(self, code, name, subtype, amount):
        self._ensure(1)
        self.pdf.setFont("Helvetica", 9)
        self.pdf.drawString(_CODE_X, self.y, str(code))
        self.pdf.drawString(_NAME_X, self.y, str(name)[:48])
        self.pdf.drawString(_SUBTYPE_X, self.y, str(subtype or "")[:24])
        self.pdf.drawRightString(_AMOUNT_X, self.y, str(amount))
        self.y -= _ROW

    def total(self, label, amount, *, strong=False):
        self._ensure(1)
        self.pdf.setFont("Helvetica-Bold" if strong else "Helvetica", 9)
        self.pdf.drawString(_NAME_X, self.y, label)
        self.pdf.drawRightString(_AMOUNT_X, self.y, str(amount))
        self.y -= _ROW


def _render_income_statement(writer, view):
    writer.start_statement("Estado de Resultados", view.as_of)

    for label, section in (
        ("Ingresos", view.income),
        ("Costos", view.costs),
        ("Gastos", view.expenses),
    ):
        writer.section(label)
        for line in section.lines:
            amount = -line.ledger_balance if line.account_type == "Ingreso" else line.ledger_balance
            writer.line(
                line.account_code,
                line.account_name,
                line.account_subtype,
                amount,
            )
        writer.total(f"Total {label.lower()}", section.total)

    writer.section("Resultado")
    writer.total("Resultado del ejercicio", view.result, strong=True)


def _render_balance_sheet(writer, view):
    writer.start_statement("Balance General", view.as_of)

    for label, section in (
        ("Activo", view.assets),
        ("Pasivo", view.liabilities),
        ("Patrimonio registrado", view.recorded_equity),
    ):
        writer.section(label)
        for line in section.lines:
            writer.line(
                line.account_code,
                line.account_name,
                line.account_subtype,
                line.amount,
            )
        writer.total(f"Total {label.lower()}", section.total)

    writer.section("Patrimonio")
    writer.total("Resultado del ejercicio", view.current_result)
    writer.total("Total patrimonio", view.total_equity, strong=True)
    writer.total("Total pasivo y patrimonio", view.liabilities_and_equity, strong=True)


def render_financial_statements_pdf(bundle):
    """Return deterministic in-memory PDF bytes for one coherent formal bundle."""
    if not isinstance(bundle, FinancialStatementsBundle):
        raise TypeError("bundle must be a FinancialStatementsBundle")

    buffer = BytesIO()
    pdf = canvas.Canvas(
        buffer,
        pagesize=letter,
        pageCompression=0,
        invariant=1,
    )
    pdf.setTitle("Aqorath - Estados financieros")
    pdf.setAuthor("Aqorath")

    writer = _StatementWriter(pdf)
    _render_income_statement(writer, bundle.income_statement)
    _render_balance_sheet(writer, bundle.balance_sheet)

    pdf.save()
    return buffer.getvalue()
