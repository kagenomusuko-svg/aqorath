"""
app.py - orquestador / punto de integración con UI o CLI futura.
Contendrá funciones para:
- iniciar/abrir libro (elegir OSC/Comercial)
- agregar registro via API
- ejecutar reportes
- finalizar ejercicio
"""

from modelos.libro import Libro

class App:
    def __init__(self):
        self.libro: Libro = None

    def nuevo_libro(self, contabilidad_tipo: str, ejercicio: int):
        self.libro = Libro(contabilidad_tipo=contabilidad_tipo, ejercicio=ejercicio)
        return self.libro

    def abrir_libro_desde_xlsx(self, path: str, contabilidad_tipo: str = "OSC"):
        self.libro = Libro.load_xlsx(path, contabilidad_tipo=contabilidad_tipo)
        return self.libro

    # aquí se exponen métodos que la UI/CLI llamará (add_registro, generate_reports, finalize, etc.)