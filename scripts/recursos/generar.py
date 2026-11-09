"""Genera los recursos de la GUI a partir de sus fuentes (solo para desarrollo).

No forma parte del paquete. Necesita ``rsvg-convert`` y se ejecuta con::

    uv run --no-project --with fonttools --with brotli --with pillow
        python scripts/recursos/generar.py <lucide/icons> <fontsource/inter/files>

Entradas: ``atril.svg`` (logotipo, fuente maestra), ``marcas/`` (logotipos de las
herramientas), los SVG de Lucide (ISC) y los
``.woff2`` latinos de Inter (OFL) de ``@fontsource/inter``. Salidas, en
``src/atril/gui/recursos/``: logotipo en PNG e ``.ico``, iconos recoloreados en
1x, 1,5x y 2x, fuentes ``.ttf`` con su licencia y las imágenes de las tarjetas.
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

NAV, SELECTED = "#3d4f6e", "#0f5ec9"
BRAND = 28
"""Lado de los logotipos de las herramientas a 100 %."""
ICONS: dict[str, tuple[int, tuple[tuple[str, str], ...]]] = {
    # nombre Lucide: (tamaño base, ((variante, color), ...))
    "house": (22, (("nav", NAV), ("sel", SELECTED))),
    "book-open": (22, (("nav", NAV), ("sel", SELECTED))),
    "library": (22, (("nav", NAV), ("sel", SELECTED))),
    "shield-check": (22, (("nav", NAV), ("sel", SELECTED))),
    "activity": (22, (("nav", NAV), ("sel", SELECTED))),
    "settings": (22, (("nav", NAV), ("sel", SELECTED))),
    "bot": (BRAND, (("marca", NAV),)),
    "chevron-up": (14, (("nav", NAV),)),
    "chevron-down": (14, (("nav", NAV),)),
    "circle-check": (18, (("ok", "#1a8f3c"),)),
    "info": (18, (("info", "#0f5ec9"),)),
    "triangle-alert": (18, (("aviso", "#d97706"),)),
    "circle-x": (18, (("error", "#c42b1c"),)),
    "loader-circle": (18, (("info", "#0f5ec9"),)),
}

HERO_ICONS: dict[str, tuple[str, str]] = {
    # Iconos de nivel grandes para el «Estado general» de Inicio (base 44).
    "circle-check": ("ok", "#1a8f3c"),
    "info": ("info", "#0f5ec9"),
    "triangle-alert": ("aviso", "#d97706"),
    "circle-x": ("error", "#c42b1c"),
}
HERO_ICON = 44
"""Lado de los iconos de :data:`HERO_ICONS` a 100 %."""

FONTS = {
    "400": "Inter-Regular.ttf",
    "600": "Inter-SemiBold.ttf",
    "700": "Inter-Bold.ttf",
}

CARD_RADIUS = 10
"""Radio de las esquinas de las tarjetas (px a 100 %)."""
HERO = (244, 248, 254, 255)
"""Fondo del bloque destacado de Inicio (``#f4f8fe``)."""
HERO_LINE = (200, 218, 244, 255)
"""Borde del bloque destacado (``#c8daf4``)."""
LINE = (223, 229, 238, 255)
"""Borde de las tarjetas (``#dfe5ee``)."""
FIELD = (250, 250, 250, 255)
"""Fondo de las tablas de sv-ttk (``#fafafa``), para los recuadros de texto."""
CARD_SIZE = 640
"""Lado de la imagen de tarjeta a 100 %: grande para que ``ttk`` la repita poco."""


def main(lucide: Path, fontsource: Path) -> None:
    """Genera todo en ``OUT``."""
    (OUT / "iconos").mkdir(parents=True, exist_ok=True)
    (OUT / "fuentes").mkdir(parents=True, exist_ok=True)
    logo()
    icons(lucide)
    brands()
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
        for name, (variant, color) in HERO_ICONS.items():
            source = (lucide / f"{name}.svg").read_text(encoding="utf-8")
            svg = Path(folder) / f"{name}-{variant}-grande.svg"
            svg.write_text(source.replace("currentColor", color), encoding="utf-8")
            for scale in SCALES:
                size = round(HERO_ICON * scale)
                render(svg, size, OUT / "iconos" / f"{name}-{variant}-{size}.png")


def brands() -> None:
    """Logotipos de las herramientas (``marcas/``), cuadrados y en cada escala.

    Son marcas de sus dueños y solo identifican cada herramienta (ver
    ``MARCAS.txt``). Se respetan sus proporciones y colores originales.
    """
    target = OUT / "marcas"
    target.mkdir(exist_ok=True)
    for old in target.glob("*.png"):
        old.unlink()
    with tempfile.TemporaryDirectory() as folder:
        for source in sorted((HERE / "marcas").glob("*.[ps][nv]g")):
            if source.suffix == ".svg":
                image_path = Path(folder) / f"{source.stem}.png"
                subprocess.run(
                    ["rsvg-convert", "-h", "512", str(source), "-o", str(image_path)],
                    check=True,
                )
            else:
                image_path = source
            image = Image.open(image_path).convert("RGBA")
            image = image.crop(image.getbbox())
            for scale in SCALES:
                size = round(BRAND * scale)
                fitted = image.copy()
                fitted.thumbnail((size, size), Image.Resampling.LANCZOS)
                square = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                square.paste(
                    fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2)
                )
                square.save(target / f"{source.stem}-{size}.png", optimize=True)
    shutil.copy(HERE / "marcas" / "MARCAS.txt", target / "MARCAS.txt")


def fonts(fontsource: Path) -> None:
    """Inter latina (Regular, SemiBold, Bold) de ``.woff2`` a ``.ttf``."""
    for weight, filename in FONTS.items():
        font = TTFont(fontsource / f"inter-latin-{weight}-normal.woff2")
        font.flavor = None
        font.save(OUT / "fuentes" / filename)
    shutil.copy(fontsource.parent / "LICENSE", OUT / "fuentes" / "OFL.txt")


def card() -> None:
    """Imágenes 9-slice con borde fino y esquinas redondeadas.

    ``tarjeta`` es blanca (tarjetas y baldosas), ``campo`` tiene el fondo de
    las tablas (textos largos dentro de una tarjeta) y ``destacado``, el azul
    muy claro del «Estado general» de Inicio.
    """
    for name, fill, line in (
        ("tarjeta", (255, 255, 255, 255), LINE),
        ("campo", FIELD, LINE),
        ("destacado", HERO, HERO_LINE),
    ):
        _card(name, fill, line)


def _card(
    name: str, fill: tuple[int, int, int, int], line: tuple[int, int, int, int]
) -> None:
    """Imagen 9-slice ``name`` a 1x y 2x con relleno ``fill``."""
    for scale, suffix in ((1, ""), (2, "@2x")):
        radius = CARD_RADIUS * scale
        size = radius * 2 + 2 * scale + 8 * scale
        image = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (0, 0, size * 4 - 1, size * 4 - 1),
            radius=radius * 4,
            fill=fill,
            outline=line,
            width=4 * scale,
        )
        small = image.resize((size, size), Image.Resampling.LANCZOS)
        _expand(small, radius + scale, CARD_SIZE * scale).save(
            OUT / f"{name}{suffix}.png", optimize=True
        )


def _expand(image: Image.Image, border: int, size: int) -> Image.Image:
    """Agranda una imagen 9-slice estirando sus bordes y su centro (uniformes).

    ``ttk`` rellena el interior repitiendo la imagen: con una imagen pequeña,
    una tarjeta grande son miles de copias en cada repintado.
    """
    small = image.size[0]
    big = Image.new("RGBA", (size, size))
    inner_small, inner_big = small - 2 * border, size - 2 * border
    for sx, bx, sw, bw in (
        (0, 0, border, border),
        (border, border, inner_small, inner_big),
        (small - border, size - border, border, border),
    ):
        for sy, by, sh, bh in (
            (0, 0, border, border),
            (border, border, inner_small, inner_big),
            (small - border, size - border, border, border),
        ):
            piece = image.crop((sx, sy, sx + sw, sy + sh))
            big.paste(piece.resize((bw, bh), Image.Resampling.NEAREST), (bx, by))
    return big


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
