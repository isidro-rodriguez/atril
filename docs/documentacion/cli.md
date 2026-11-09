# Línea de comandos

Todo lo que hace la ventana se puede hacer desde la consola con `atril`. La ayuda de cada
comando está en `atril <comando> --help`. Los comandos terminan con código `1` si algo ha
ido mal, así que sirven en guiones.

```text
atril --version
atril --help
```

## Atril

| Comando | Qué hace |
|---|---|
| `atril gui` | Abre la ventana y devuelve la consola al momento. Si ya está abierta (o en el área de notificación), la muestra. |
| `atril validar` | Valida `atril.toml` y el `temario.toml` de cada temario. |
| `atril backup` | Copia la estación en cada destino ([detalles](backups.md)). |
| `atril backup comprobar` | Lista las copias de cada destino y verifica la más reciente. |
| `atril backup restaurar [copia]` | Restaura una copia (por defecto, la más reciente). |

Opciones:

| Opción | Comando | Efecto |
|---|---|---|
| `--sin-arrancar` | `backup` | No vuelve a arrancar DeepTutor al terminar. |
| `--si` | `backup restaurar` | No pide confirmación. |
| `--nueva-ruta` | `backup restaurar` | Acepta una copia hecha desde otra ruta de estación. |

## DeepTutor

| Comando | Qué hace |
|---|---|
| `atril instalar` | Instala DeepTutor en `app\` o completa una instalación a medias. Se puede repetir. |
| `atril actualizar` | Actualiza DeepTutor a la última versión de su rama y reaplica configuración y parches. |
| `atril arrancar` | Aplica los parches pendientes, arranca Ollama si hace falta, arranca DeepTutor y abre el navegador. |
| `atril parar` | Detiene DeepTutor y cierra sus procesos huérfanos. |
| `atril estado` | DeepTutor, parches, Ollama, espacio libre, última copia y si hay una versión nueva de atril. |
| `atril parches` | Aplica los parches de `atril.toml` (con `--comprobar`, solo los revisa). |

Opciones:

| Opción | Comandos | Efecto |
|---|---|---|
| `--sin-docling` | `instalar`, `actualizar` | No instala el lector de PDF Docling (descarga grande, con PyTorch). |
| `--sin-arrancar` | `actualizar` | No vuelve a arrancar DeepTutor al terminar. |
| `--commit <sha>` | `actualizar` | Va a ese commit (hash completo): vuelta atrás si la versión nueva da problemas. |
| `--sin-navegador` | `arrancar` | No abre el navegador. |
| `--espera <s>` | `arrancar` | Segundos de espera (por defecto, 600; tras actualizar se compila la web). |

!!! example "Volver a la versión anterior de DeepTutor"
    `atril actualizar` muestra el hash de la versión que había. Si la nueva falla:

    ```text
    atril actualizar --commit 3f2a…c91e
    ```

## Temarios

| Comando | Qué hace |
|---|---|
| `atril temario lista` | Temarios con sus KB y el estado de sus fuentes. |
| `atril temario crear <nombre> [--id <id>]` | Crea un temario con una KB para todas sus fuentes. |
| `atril temario cobertura <t>` | KB a KB, qué fuentes están en disco y cuándo se comprobaron. |
| `atril fuentes añadir <t> <pdf\|url>` | Copia un PDF local o declara una URL. Opciones: `--id`, `--titulo`, `--kb`. |
| `atril fuentes descargar <t> [fuentes…]` | Descarga las fuentes que faltan; no toca las que ya están. |
| `atril fuentes comprobar <t> [fuentes…]` | Busca versiones nuevas según su frecuencia (`--todas`: todas las que tienen URL). |

## Bases de conocimiento

| Comando | Qué hace |
|---|---|
| `atril kb estado [t] [kb] [--detalle]` | Qué fuentes están indexadas y el estado del último indexado. Solo lee. |
| `atril kb indexar <t> [kb]` | Añade a las KB las fuentes nuevas, una a una. Si se interrumpe, repetirlo continúa. |
| `atril kb reindexar <kb>` | Sustituye las fuentes cambiadas y quita las retiradas. |
| `atril kb evaluar <kb> [-k 5] [--dataset f.jsonl] [--detalle]` | Mide la recuperación y la compara con el informe anterior. |

Más detalles en [Indexado y evaluación](indexado.md).

## Ejemplo: de cero a estudiar

```text
uv tool install atril
atril validar                                  # la primera vez, elige la estación
atril instalar
atril temario crear "Física"
atril fuentes añadir fisica "D:\Apuntes\Tema 1 - Campo gravitatorio.pdf"
atril fuentes añadir fisica https://www.boe.es/buscar/pdf/2022/BOE-A-2022-6008-consolidado.pdf --titulo "Real Decreto 243/2022"
atril fuentes descargar fisica
atril kb indexar fisica
atril arrancar
```
