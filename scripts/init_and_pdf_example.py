from pathlib import Path
from aqorath.storage import get_session, init_db
from aqorath.company import Company
from aqorath.core import generate_preview
from aqorath.reports_jinja import generate_pdf_from_preview

# inicializa la BD
init_db()

# crear company demo (si no existe)
with get_session() as s:
    existing = s.exec(select(Company)).scalars().first()
    if not existing:
        c = Company(name="Mi Empresa S.A. de C.V.", rfc="XAXX010101000", denominacion="Deno. Ejemplo", phrase="La fuerza interior nos impulsa")
        s.add(c)
        s.commit()
        s.refresh(c)
    else:
        c = existing

# generar preview ejemplo (usa template que ya exista)
preview = generate_preview("ingreso_venta", 1000.0, ctx={"account_codes": {"bank":"1000","sales":"4000","vat_tr":"2100"}, "vat_rate": 0.16, "desc":"Venta prueba"})

out = generate_pdf_from_preview(preview, company=c)
print("PDF generado en:", out)