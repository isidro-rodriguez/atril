"""Interfaz gráfica de atril (tkinter + sv-ttk), sobre los casos de uso de la CLI.

Se abre con ``atril-gui``: en Windows, sin ventana de consola (``pythonw``).
"""


def main() -> None:
    """Abre la ventana principal de atril."""
    from atril.gui.app import run

    run()
