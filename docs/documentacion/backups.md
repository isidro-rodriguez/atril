# Copias de seguridad

Las copias son ficheros comprimidos normales, sin programas extra: un `zip` o un `tar.xz` por
copia, en las carpetas de `[backup] destinos` (un disco externo, la carpeta de Google Drive
para escritorio…).

## Qué se copia

| Se copia | No se copia |
|---|---|
| `atril.toml` | `app\` (DeepTutor se reinstala) |
| `data\` (ajustes, KB, índices, chats) | `data\atril\logs\` |
| `temarios\` (con PDF, histórico y evaluaciones) | Enlaces simbólicos y uniones |

Cada copia lleva además `atril-backup.json`: ruta de la estación, fecha, versión de atril,
claves vaciadas, si está completa y el inventario de ficheros con su tamaño.

!!! warning "Las claves de API van vacías"
    Las claves de `data\user\settings\model_catalog.json` se vacían dentro de la copia (el
    original no se toca). Tras restaurar, hay que volver a escribirlas en DeepTutor.

## Hacer una copia

`atril backup` (o **Hacer backup**):

1. Para DeepTutor, que guarda sus datos en SQLite.
2. Escribe la copia como `atril-AAAAMMDD-HHMMSS.zip.part` en el primer destino disponible.
3. La verifica (CRC del zip o el flujo xz entero, más el inventario) y le quita el `.part`.
4. La copia a los demás destinos y la verifica en cada uno.
5. Borra las más antiguas de cada destino hasta dejar `conservar`.
6. Vuelve a arrancar DeepTutor si estaba en marcha.

| Formato | Compresión | Velocidad |
|---|---|---|
| `zip` | deflate 9 | Rápido |
| `tar.xz` | xz 9 | Ocupa menos, bastante más lento |

Reglas de seguridad:

- Un destino cuya carpeta superior no existe es un **disco desconectado**: se salta con un
  aviso.
- Si algún fichero no se pudo leer, la copia se llama `atril-…-incompleta`: no se restaura ni
  cuenta para `conservar`.
- Solo se borran ficheros `atril-*`, y nada si algo ha fallado.

## Comprobar

`atril backup comprobar` (o **Comprobar**) lee entera la copia más reciente de cada destino,
exige `atril.toml`, `data\` y `temarios\`, y avisa si tiene más de una semana.

## Restaurar

`atril backup restaurar [copia]` (o **Restaurar…**). DeepTutor debe estar parado.

1. Extrae la copia en `<estación>.restaurar-<fecha>`, junto a la estación (rechaza rutas
   absolutas o con `..`).
2. Intercambia: lo actual pasa a `<estación>.previo-<fecha>` y lo restaurado ocupa su sitio.
3. Lo anterior **nunca se borra**: elimínalo tú cuando compruebes que todo está bien.

Si el intercambio falla, se deshace. Si ni siquiera se puede deshacer del todo, atril no borra
nada (tampoco la carpeta de extracción) y explica dónde está cada cosa.

!!! note "Copias de otra ruta"
    Las KB de DeepTutor guardan rutas absolutas. Una copia hecha desde otra ruta de estación
    exige `--nueva-ruta`; revisa después las KB.
