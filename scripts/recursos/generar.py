"""Genera los recursos de la GUI a partir de sus fuentes (solo para desarrollo).

No forma parte del paquete. Necesita ``rsvg-convert`` y se ejecuta con::

    uv run --no-project --with fonttools --with brotli --with pillow
        python scripts/recursos/generar.py <lucide/icons> <fontsource/inter/files>

Entradas: ``atril.svg`` (logotipo, fuente maestra), los SVG de Lucide (ISC) y los
``.woff2`` latinos de Inter (OFL) de ``@fontsource/inter``. Salidas, en
``src/atril/gui/recursos/``: logotipo en PNG e ``.ico``, iconos recoloreados en
1x, 1,5x y 2x, fuentes ``.ttf`` con su licencia y la imagen de las tarjetas.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

HERE = Path(__file__).parent
OUT = HERE.parent.parent / "src" / "atril" / "gui" / "recursos"

SCALES = (1.0, 1.5, 2.0)
"""Escalas de los PNG: 100 %, 150 % y 200 % de pantalla."""

NAV, SELECTED, ACCENT = "#3d4f6e", "#0f5ec9", "#0f5ec9"
ICONS: dict[str, tuple[int, tuple[tuple[str, str], ...]]] = {
    # nombre Lucide: (tamaño base, ((variante, color), ...))
    "house": (22, (("nav", NAV), ("sel", SELECTED))),
    "book-open": (22, (("nav", NAV), ("sel", SELECTED), ("acc", ACCENT))),
    "library": (22, (("nav", NAV), ("sel", SELECTED))),
    "server": (22, (("nav", NAV), ("sel", SELECTED))),
    "shield-check": (22, (("nav", NAV), ("sel", SELECTED))),
    "stethoscope": (22, (("nav", NAV), ("sel", SELECTED))),
    "settings": (22, (("nav", NAV), ("sel", SELECTED))),
    "circle-plus": (22, (("acc", ACCENT),)),
    "folder-open": (22, (("acc", ACCENT),)),
    "wrench": (22, (("acc", ACCENT),)),
    "circle-check": (18, (("ok", "#1a8f3c"),)),
    "info": (18, (("info", "#0f5ec9"),)),
    "triangle-alert": (18, (("aviso", "#d97706"),)),
    "circle-x": (18, (("error", "#c42b1c"),)),
    "loader-circle": (18, (("info", "#0f5ec9"),)),
    "panel-right-close": (18, (("nav", NAV),)),
    "panel-right-open": (18, (("nav", NAV),)),
}

FONTS = {
    "400": "Inter-Regular.ttf",
    "600": "Inter-SemiBold.ttf",
    "700": "Inter-Bold.ttf",
}

CARD_RADIUS = 10
"""Radio de las esquinas de las tarjetas (px a 100 %)."""


def main(lucide: Path, fontsource: Path) -> None:
    """Genera todo en ``OUT``."""
    (OUT / "iconos").mkdir(parents=True, exist_ok=True)
    (OUT / "fuentes").mkdir(parents=True, exist_ok=True)
    logo()
    icons(lucide)
    fonts(fontsource)
    card()
    shutil.copy(lucide.parent / "LICENSE", OUT / "iconos" / "LICENSE-lucide.txt")
    print(f"Recursos generados en {OUT}")


def render(svg: Path, size: int, target: Path) -> None:
    """SVG → PNG con ``rsvg-convert``."""
    subprocess.run(
        ["rsvg-convert", "-w", str(size), "-h", str(size), str(svg), "-o", str(target)],
        check=True,
    )


def logo() -> None:
    """Logotipo en varios tamaños y el ``.ico`` de Windows."""
    shutil.copy(HERE / "atril.svg", OUT / "atril.svg")
    for size in (32, 48, 64, 96, 128, 256):
        render(HERE / "atril.svg", size, OUT / f"logo-{size}.png")
    for old in OUT.glob("icono-*.png"):
        old.unlink()
    big = Image.open(OUT / "logo-256.png")
    big.save(OUT / "atril.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])


def icons(lucide: Path) -> None:
    """Iconos de Lucide recoloreados, en cada escala."""
    with tempfile.TemporaryDirectory() as folder:
        for name, (base, variants) in ICONS.items():
            source = (lucide / f"{name}.svg").read_text(encoding="utf-8")
            for variant, color in variants:
                svg = Path(folder) / f"{name}-{variant}.svg"
                svg.write_text(source.replace("currentColor", color), encoding="utf-8")
                for scale in SCALES:
                    size = round(base * scale)
                    target = OUT / "iconos" / f"{name}-{variant}-{size}.png"
                    render(svg, size, target)


def fonts(fontsource: Path) -> None:
    """Inter latina (Regular, SemiBold, Bold) de ``.woff2`` a ``.ttf``."""
    for weight, filename in FONTS.items():
        font = TTFont(fontsource / f"inter-latin-{weight}-normal.woff2")
        font.flavor = None
        font.save(OUT / "fuentes" / filename)
    shutil.copy(fontsource.parent / "LICENSE", OUT / "fuentes" / "OFL.txt")


def card() -> None:
    """Imagen 9-slice de las tarjetas: blanca, borde fino y esquinas redondeadas."""
    for scale, suffix in ((1, ""), (2, "@2x")):
        radius = CARD_RADIUS * scale
        size = radius * 2 + 2 * scale + 8 * scale
        image = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (0, 0, size * 4 - 1, size * 4 - 1),
            radius=radius * 4,
            fill=(255, 255, 255, 255),
            outline=(223, 229, 238, 255),
            width=4 * scale,
        )
        image.resize((size, size), Image.Resampling.LANCZOS).save(
            OUT / f"tarjeta{suffix}.png"
        )


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
