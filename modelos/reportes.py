# modelos/reportes.py
"""
Generador de reportes PDF usando ReportLab.

Funciones:
- export_report(libro, tipo, output_path, fecha_inicio=None, fecha_fin=None, cuentas=None)
  tipo: 'balance' | 'mayor' | 'estado_resultados'
"""
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import cm
from datetime import datetime
import pandas as pd
from typing import Optional, List
import os

def _df_to_table_data(df: "pd.DataFrame") -> List[List[str]]:
    # Convertir DataFrame a una lista de filas (strings) aptas para ReportLab Table
    headers = list(df.columns)
    rows = [headers]
    for _, r in df.iterrows():
        row = []
        for c in headers:
            v = r[c]
            # formatear float con 2 decimales
            if isinstance(v, float):
                row.append(f"{v:,.2f}")
            elif pd.isnull(v):
                row.append("")
            else:
                row.append(str(v))
        rows.append(row)
    return rows

def export_report(libro, tipo: str, output_path: str, fecha_inicio: Optional[str] = None, fecha_fin: Optional[str] = None, cuentas: Optional[List[str]] = None):
    """
    Exporta un reporte PDF desde el objeto Libro.
    - libro: instancia de Libro
    - tipo: 'balance' | 'mayor' | 'estado_resultados'
    - output_path: ruta del PDF a generar
    - fecha_inicio / fecha_fin: strings ISO (opcional, por si se quiere filtrar en el futuro)
    - cuentas: lista de códigos de cuenta para filtrar (solo para 'mayor')
    """
    tipo = (tipo or "").lower()
    if tipo not in ("balance", "mayor", "estado_resultados"):
        raise ValueError("Tipo desconocido. Usa 'balance', 'mayor' o 'estado_resultados'.")

    # Preparar documento
    dirname = os.path.dirname(output_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    # Título
    t = f"SistemaContable - Reporte: {tipo.replace('_', ' ').title()}"
    story.append(Paragraph(t, styles["Title"]))
    meta = f"Generado: {datetime.now().isoformat(sep=' ', timespec='seconds')}"
    story.append(Paragraph(meta, styles["Normal"]))
    story.append(Spacer(1, 12))

    if tipo == "balance":
        df = libro.compute_balance()
        if df.empty:
            story.append(Paragraph("No hay datos para el Balance.", styles["Normal"]))
        else:
            table_data = _df_to_table_data(df)
            tstyle = TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
                ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
            ])
            table = Table(table_data, hAlign='LEFT')
            table.setStyle(tstyle)
            story.append(table)

    elif tipo == "mayor":
        df = libro.compute_libro_mayor()
        if cuentas:
            df = df[df["Codigo"].isin(cuentas)]
        if df.empty:
            story.append(Paragraph("No hay datos para el Libro Mayor.", styles["Normal"]))
        else:
            # Convertir Saldo numérico a formato con separador
            table_data = _df_to_table_data(df)
            tstyle = TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
                ('ALIGN', (3,0), (-1,-1), 'RIGHT'),
            ])
            table = Table(table_data, hAlign='LEFT')
            table.setStyle(tstyle)
            story.append(table)

    elif tipo == "estado_resultados":
        df = libro.compute_estado_resultados()
        if df.empty:
            story.append(Paragraph("No hay datos para el Estado de Resultados.", styles["Normal"]))
        else:
            table_data = _df_to_table_data(df)
            tstyle = TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
                ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
            ])
            table = Table(table_data, hAlign='LEFT', colWidths=None)
            table.setStyle(tstyle)
            story.append(table)

    # Pie
    story.append(Spacer(1, 12))
    nota = "Reporte generado por SistemaContable (AC). Este documento es una representación interna de los datos contables."
    story.append(Paragraph(nota, styles["Italic"]))

    doc.build(story)
    return {"status": "ok", "path": output_path}