from pathlib import Path
import csv
from openpyxl import Workbook

CSV_PATH = Path("assets/catalogo.csv")
XLSX_PATH = Path("assets/Catálogo.xlsx")

def csv_to_xlsx(csv_path: Path = CSV_PATH, xlsx_path: Path = XLSX_PATH):
    if not csv_path.exists():
        raise SystemExit(f"CSV no encontrado: {csv_path.resolve()}")
    wb = Workbook()
    ws = wb.active
    ws.title = "Catalogo"
    with csv_path.open(newline='', encoding='utf-8') as f:
        # detect delimiter (tab or comma)
        sample = f.read(2048)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
        reader = csv.reader(f, dialect)
        for r_idx, row in enumerate(reader, start=1):
            for c_idx, cell in enumerate(row, start=1):
                # strip BOM if present
                if isinstance(cell, str):
                    cell = cell.strip('\ufeff')
                ws.cell(row=r_idx, column=c_idx, value=cell)
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(xlsx_path))
    print(f"Wrote {xlsx_path.resolve()}")

if __name__ == "__main__":
    csv_to_xlsx()