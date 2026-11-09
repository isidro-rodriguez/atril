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
| Desarrollo | `ruff`, `ty`, `pytest`, `pytest-cov`, `pre-commit`, `zensical`, `pillow` (pruebas del generador de capturas) |

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

El sitio se publica en GitHub Pages **con cada versión**: al crear la release, `publish.yml`
llama a `docs.yml` con su tag, y la web se construye con el código de ese tag. Un cambio que
solo toca `docs/` se ve en la web con la siguiente versión: no hay publicación manual.

### Capturas

Las capturas de la ventana no se versionan ni se reutilizan. `docs.yml` las genera en Windows
con `scripts/capturas.py`, que forma parte de la publicación (no es una herramienta de uso
manual), en tres pasos separados:

1. Prepara una estación de ejemplo (2.º de Bachillerato de Ciencias, fechas fijas) en
   `D:\Estudio`, con las copias en `D:\Copias\Atril`. Falla si ya existen, y las borra al
   terminar.
2. Abre la ventana real con los servicios simulados.
3. Espera a que cada apartado haya cargado (como mucho 60 s), lo captura y valida todas las
   imágenes (las seis, PNG de 1024×700 y un tamaño mínimo) antes de entregarlas.

Cualquier fallo termina con código de error, y entonces no se publica la web. Su ejecución
real en cada publicación es la prueba de integración; `tests/test_capturas.py` solo cubre la
validación de las imágenes, el aislamiento de carpetas y que un fallo no sustituya las
capturas. Fuera de la CI
usa una carpeta temporal; sirve para revisar el aspecto antes de `zensical serve`:

```bash
uv run --with pillow python scripts/capturas.py docs/assets/images/capturas
```

## Versiones y publicación

- Commits en español con [Conventional Commits](https://www.conventionalcommits.org/es/).
- Cada cambio del paquete sube la versión en `pyproject.toml` (SemVer) y añade su entrada en
  `CHANGELOG.md`.
- Al subir a `main`, `publish.yml` publica en PyPI, crea la release de GitHub y le adjunta el
  instalador de Windows.
