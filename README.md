# atril

CLI para gestionar una instalación local de [DeepTutor](https://github.com/HKUDS/DeepTutor)
y sus temarios: fuentes, bases de conocimiento (KB), evaluación y backup.

## 🚀 Guía rápida

```bash
uv tool install atril            # instalar (o actualizar: uv tool upgrade atril)
cd D:\Desarrollo\DeepTutor       # la estación: la carpeta con atril.toml
atril validar                    # comprueba atril.toml y los temarios
atril instalar                   # instala DeepTutor en app\
atril arrancar                   # arranca DeepTutor y abre el navegador
```

Fuera de la estación, indica su ruta con `--estacion <ruta>` o la variable `ATRIL_ESTACION`.
Ayuda de cada comando: `atril <comando> --help`.

### Configuración

```bash
atril validar                    # valida atril.toml y el temario.toml de cada temario
```

### DeepTutor

```bash
atril instalar                   # instala DeepTutor en app\ o completa la instalación
atril actualizar                 # trae la última versión de la rama y reaplica ajustes y parches
atril arrancar                   # arranca DeepTutor (y Ollama si hace falta)
atril parar                      # detiene DeepTutor y cierra sus procesos huérfanos
atril estado                     # estado de DeepTutor, sus parches y Ollama
atril parches [--comprobar]      # aplica los parches de atril.toml sobre app\
```

### Temarios y fuentes

```bash
atril temario lista              # temarios, KB y fuentes presentes, manuales y pendientes
atril temario cobertura <t>      # fuentes de cada KB: fichero, estado y última comprobación
atril fuentes descargar <t>      # descarga las fuentes que faltan
atril fuentes comprobar <t>      # busca versiones nuevas; la anterior va al histórico
```

### Bases de conocimiento

```bash
atril kb estado [t] [kb]         # qué fuentes están indexadas (solo lee)
atril kb indexar <t> [kb]        # añade a las KB las fuentes nuevas, una a una
atril kb reindexar <kb>          # sustituye fuentes cambiadas y purga las retiradas
atril kb evaluar <kb> [-k 5]     # mide la recuperación y la compara con el informe anterior
```

### Backup

```bash
atril backup [-d destino]        # copia la estación con restic (sin app\) y aplica la retención
atril backup comprobar           # verifica los repositorios y lista sus últimos snapshots
atril backup restaurar -d <d>    # restaura un snapshot; lo actual queda en <estación>.previo-*
```

La contraseña de restic va en `RESTIC_PASSWORD` (o `_FILE` / `_COMMAND`), nunca en
`atril.toml`.

Configuración: [`docs/esquemas.md`](https://github.com/isidro-rodriguez/atril/blob/main/docs/esquemas.md) · ejemplos en [`docs/ejemplos/`](https://github.com/isidro-rodriguez/atril/blob/main/docs/ejemplos/).

## 🛠️ Desarrollo

```bash
git clone https://github.com/isidro-rodriguez/atril.git
cd atril
uv sync
```

Calidad (lo mismo que la CI):

```bash
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
```

Con [Poe the Poet](https://poethepoet.natn.io/): `poe check` · `poe fix` · `poe backup`.

## Enlaces

- Decisiones de diseño: [`docs/decisiones.md`](https://github.com/isidro-rodriguez/atril/blob/main/docs/decisiones.md)
- Plantilla base: <https://github.com/isidro-rodriguez/acodo-template>
- Acodo: <https://github.com/isidro-rodriguez/acodo>

## Licencia

[MIT](https://github.com/isidro-rodriguez/atril/blob/main/LICENSE).
