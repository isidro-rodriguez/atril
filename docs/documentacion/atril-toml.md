# `atril.toml`

La configuración de la estación. Está en la raíz de la estación (la carpeta que lo contiene
**es** la estación) y se puede editar a mano o desde **Ajustes** en la ventana. `atril
validar` lo comprueba entero: las claves van en español y una clave desconocida es un error,
para detectar erratas.

## Ejemplo completo

Este es el ejemplo que validan las pruebas de atril, así que siempre está al día.

```toml title="atril.toml"
--8<-- "documentacion/ejemplos/atril.toml"
```

[Descargar el ejemplo](ejemplos/atril.toml){ .md-button }

Una estación nueva empieza con lo mínimo: `[deeptutor]` vacía y un destino en `[backup]`.

## Claves

| Tabla | Clave | Tipo | Defecto | Notas |
|---|---|---|---|---|
| `[deeptutor]` | `repo` | URL | `https://github.com/HKUDS/DeepTutor` | |
| | `rama` | texto | `"dev"` | |
| | `python` | texto | `"3.13"` | Versión para `app\.venv` |
| | `puertos` | `{ backend, frontend }` | `8001`, `3782` | Distintos, 1–65535 |
| | `parches` | lista de nombres | `[]` | Parches incluidos en atril ([`paginas-citas`, `arranque-sin-ventana`](conceptos.md#parches)) |
| | `paquetes` | lista de requisitos | `[]` | Extra en `app\.venv` (p. ej. `claude-agent-sdk`) |
| | `busqueda` | texto | — | Proveedor de búsqueda de DT (`duckduckgo`) |
| `[deeptutor.llm]` (opcional) | `proveedor` | texto | — | Junto con `modelo`; sin claves en el fichero |
| | `modelo` | texto | — | |
| `[ollama]` (opcional) | `url` | URL | `http://localhost:11434` | Sin `[ollama]` DeepTutor funciona (LLM en la nube), pero no se indexan fuentes: `kb indexar`, `reindexar` y `evaluar` lo piden |
| | `embedding` | texto | **obligatorio** en `[ollama]` | |
| | `dimension` | entero ≥ 1 | **obligatorio** en `[ollama]` | |
| | `contexto` | entero ≥ 1 | `8192` | = `OLLAMA_CONTEXT_LENGTH` y ventana en DT |
| `[indexado]` (opcional) | `parser` | `text_only` · `docling` · `mineru` · `markitdown` · `pymupdf4llm` · `liteparse` · `tika` | `"docling"` | DT usa `text_only` por defecto |
| | `chunk` | entero ≥ 1 | `1024` | |
| | `solape` | entero ≥ 0 | `150` | Menor que `chunk` |
| | `descargar_modelos` | booleano | `true` | Docling/MinerU descargan sus modelos |
| | `lote_embedding` | entero ≥ 1 | `10` | Fragmentos por petición de embedding; lotes pequeños = ráfagas de GPU cortas |
| | `pausa_embedding` | entero ≥ 0 | `0` | Milisegundos mínimos entre el inicio de dos peticiones de embedding; con un lote pequeño deja huecos libres a la GPU |
| | `hilos` | entero ≥ 0 | `0` | Hilos de CPU del parser y el troceado al indexar; `0` = sin límite. No cambia el resultado, solo el ritmo |
| `[backup]` | `destinos` | lista de rutas absolutas | **obligatorio** | Carpetas para las copias; fuera de la estación. Un disco desconectado se salta |
| | `formato` | `zip` · `tar.xz` | `"zip"` | `zip` (deflate 9) o `tar.xz` (xz 9: más compacto, bastante más lento) |
| | `conservar` | entero ≥ 1 | `7` | Copias que se guardan en cada destino; las más antiguas se borran |
| `[atril]` (opcional) | `buscar_actualizaciones` | booleano | `true` | Al abrir la ventana, consulta la última release en GitHub y ofrece actualizar (con el instalador de Windows) o ver las novedades. `atril estado` también lo comprueba y solo avisa |

!!! warning "Nunca hay claves de API en este fichero"
    El asistente se elige con `[deeptutor.llm]`, pero las claves de los proveedores en la nube
    se escriben en DeepTutor, nunca aquí.

## Qué hace falta tras un cambio

`atril instalar` traslada a DeepTutor `[deeptutor.llm]`, `busqueda`, `[ollama]` y los puertos
(`deeptutor config apply`), y `[indexado]` (parser, fragmentos y ritmo del embedding).
`atril kb indexar` vuelve a aplicar `[indexado]` antes de empezar.

Desde la ventana, al guardar, atril valida el fichero entero antes de sustituirlo (conserva
los comentarios) y dice qué hace falta:

| Cambio en | Hace falta |
|---|---|
| Asistente, búsqueda, puertos, Ollama, parser | Aplicar la configuración a DeepTutor (**Aplicar ahora**). |
| Parches | Aplicar los parches. |
| Repositorio, rama, Python, paquetes | Reinstalar DeepTutor (**Instalar o reparar**). |
| Modelo o dimensión de embedding, parser, fragmento, solape | Reindexar los temarios. |
| Copias, ritmo del indexado, actualizaciones | Nada: se leen en cada operación. |

## Ficheros de la ventana

| Ruta (bajo la estación) | Contenido |
|---|---|
| `data\atril\actividad.jsonl` | Historial de la ventana: una línea JSON por operación, las 500 últimas. Las líneas que no se entienden se ignoran. |
| `data\atril\ventana.json` | Temario activo (`{"temario": "<id>"}`), compartido por Temarios y Biblioteca. |
| `data\atril\ollama.json` | Ollama abierto por atril (`pid` e `inicio`): solo ese se puede parar desde atril. |
