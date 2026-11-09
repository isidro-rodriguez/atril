# Contribuir

## Entorno

Requisitos: Python 3.13+ y [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/isidro-rodriguez/atril.git
cd atril
uv sync                        # un único venv y uv.lock en la raíz, con el grupo dev
uv run pre-commit install      # hooks de pre-commit y pre-push (recomendado)
```

- Dependencias de ejecución: `uv add <paquete>`. De desarrollo: `uv add --dev <paquete>`.
- Nunca `pip install`. Antes de añadir una dependencia, comprueba si la biblioteca estándar lo
  resuelve.

| Grupo | Paquetes |
|---|---|
| Ejecución | `acodo`, `typer`, `psutil`, `tomlkit`, `sv-ttk` |
| Desarrollo | `ruff`, `ty`, `pytest`, `pytest-cov`, `pre-commit`, `zensical` |

## Calidad

Siempre desde la raíz (es lo mismo que la integración continua):

```bash
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
```

Con [Poe the Poet](https://poethepoet.natn.io/) instalado globalmente: `poe check`, `poe fix`
y `poe serve`. No es dependencia del proyecto.

Las pruebas no usan la red ni servicios reales (`tests/conftest.py` hace fallar cualquier
descarga que una prueba no sustituya) y pasan en Linux y Windows. Las de la ventana se saltan
si no hay pantalla.

## Estructura

| Carpeta | Contenido |
|---|---|
| `src/atril/commands/` | Línea de comandos (Typer + Rich): solo lee opciones, muestra y sale. |
| `src/atril/ops/` | Casos de uso compartidos por la consola y la ventana. |
| `src/atril/gui/` | Ventana (tkinter + sv-ttk), sin lógica de negocio. |
| `src/atril/config/` | Esquemas de `atril.toml` y `temario.toml`. |
| `instalador/` | Instalador de Windows (Inno Setup). |
| `docs/` | Este sitio (Zensical). Los ejemplos de `docs/documentacion/ejemplos/` los validan las pruebas. |

Las reglas detalladas están en [`CLAUDE.md`](https://github.com/isidro-rodriguez/atril/blob/main/CLAUDE.md)
y las decisiones de diseño, en
[`DECISIONES.md`](https://github.com/isidro-rodriguez/atril/blob/main/DECISIONES.md).

## Documentación

```bash
uv run zensical serve   # vista previa en http://localhost:8000
uv run zensical build   # genera el sitio en site/
```

El sitio se publica en GitHub Pages con cada cambio en `main` (`.github/workflows/docs.yml`).

### Capturas

Las capturas de la ventana no se versionan: `docs.yml` las genera en Windows con la ventana
real del mismo commit y la construcción falla si falta alguna o si la versión no coincide con
la de `pyproject.toml`. Para generarlas en local (antes de `zensical serve`):

```bash
uv run --with pillow python scripts/capturas.py
```

El script tiene tres pasos separados: prepara una estación de ejemplo (2.º de Bachillerato,
fechas fijas), abre la ventana con los servicios simulados y captura cada apartado en
`docs/assets/images/capturas/`. En Windows usa `D:\Estudio` y `D:\Copias\Atril`, y se niega
si existen y no las creó él. En Linux usa una carpeta temporal (solo para revisar el aspecto).

## Versiones y publicación

- Commits en español con [Conventional Commits](https://www.conventionalcommits.org/es/).
- Cada cambio del paquete sube la versión en `pyproject.toml` (SemVer) y añade su entrada en
  `CHANGELOG.md`.
- Al subir a `main`, `publish.yml` publica en PyPI, crea la release de GitHub y le adjunta el
  instalador de Windows.
