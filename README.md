# atril

CLI para gestionar una instalación local de [DeepTutor](https://github.com/HKUDS/DeepTutor)
y sus temarios (fuentes, bases de conocimiento, evaluación y backup).

> Estado: fase 1 completa. Implementados `validar` y todo el grupo DeepTutor.

## 🚀 Instalación

```bash
uv tool install atril          # uso diario
```

Desarrollo:

```bash
git clone https://github.com/isidro-rodriguez/atril.git
cd atril
uv sync
```

## 🛠️ Uso

```bash
atril --estacion D:\Desarrollo\DeepTutor validar   # o ATRIL_ESTACION, o desde la estación
```

| Grupo | Comandos | Fase |
|---|---|---|
| Configuración | `validar` | 0 ✅ |
| DeepTutor | `instalar` · `actualizar` · `arrancar` · `parar` · `estado` · `parches` | 1 ✅ |
| Temarios | `temario lista` · `temario cobertura <t>` | 2 |
| Fuentes | `fuentes descargar <t>` · `fuentes comprobar <t>` | 2 |
| KB | `kb indexar <t> [kb]` · `kb reindexar <kb>` · `kb evaluar <kb>` | 2 |
| Backup | `backup` · `backup comprobar` · `backup restaurar` | 3 |
| Otros | `accesos` | 5 |

Configuración: [`docs/esquemas.md`](docs/esquemas.md) · ejemplos en [`docs/ejemplos/`](docs/ejemplos/).

## ✅ Calidad

```bash
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
```

Con [Poe the Poet](https://poethepoet.natn.io/): `poe check` · `poe fix` · `poe backup`.

## Enlaces

- Decisiones de diseño: [`docs/decisiones.md`](docs/decisiones.md)
- Plantilla base: <https://github.com/isidro-rodriguez/acodo-template>
- Acodo: <https://github.com/isidro-rodriguez/acodo>

## Licencia

[MIT](LICENSE).
