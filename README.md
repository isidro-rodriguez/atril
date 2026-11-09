# atril

Ventana y CLI para gestionar una instalación local de
[DeepTutor](https://github.com/HKUDS/DeepTutor) y sus temarios: fuentes, bases de conocimiento
(KB), evaluación y backup. Pensado para Windows; la CLI funciona también en Linux y macOS.
Guía para empezar y documentación completa en la [web](https://isidro-rodriguez.github.io/atril/).

## 🚀 Guía rápida

En Windows, lo más sencillo es el instalador `atril-X.Y.Z-setup.exe` de las
[releases](https://github.com/isidro-rodriguez/atril/releases): no pide administrador, instala
atril con su propio Python y crea el acceso directo. Con la consola:

```bash
uv tool install atril            # instalar (o actualizar: uv tool upgrade atril)
atril validar                    # comprueba atril.toml y los temarios (la 1.ª vez, elige la estación)
atril instalar                   # instala DeepTutor en app\ (Ollama es opcional: solo para indexar)
atril arrancar                   # arranca DeepTutor y abre el navegador
atril gui                        # abre la ventana y devuelve la consola (o atril-gui)
```

Hay una sola estación por equipo. En la primera ejecución atril ofrece la carpeta actual si
tiene `atril.toml`; si no, pregunta la ruta y, si allí no hay `atril.toml`, ofrece crearla. La
guarda en la variable de usuario `ATRIL_ESTACION` y después funciona desde cualquier carpeta.
Ayuda de cada comando: `atril <comando> --help`.

### Ventana

`atril-gui` (o `atril gui` desde la consola) abre una ventana para usar atril sin consola:

| Apartado | Qué hace |
|---|---|
| Inicio | Estado de DeepTutor, Ollama y las herramientas; arrancar, parar e instalar |
| Temarios | Temario activo, sus KB y fuentes; crear, indexar, reindexar y borrar |
| Biblioteca | Fuentes del temario activo; añadir, descargar y buscar versiones nuevas |
| Backups | Copias de cada destino; hacer, comprobar y restaurar |
| Actividad | Historial de operaciones con su detalle técnico |
| Ajustes | Todas las claves de `atril.toml` y herramientas (actualizar, diagnóstico...) |

En Windows, cerrar la ventana con DeepTutor en marcha deja atril en el área de notificación,
con un menú para mostrarla, abrir DeepTutor, arrancarlo o pararlo, hacer un backup o salir
(«Salir» para DeepTutor y el Ollama que abrió atril). Sin DeepTutor en marcha, se cierra del
todo. Abrir `atril-gui` de nuevo muestra la ventana existente.

Al abrirse, la ventana busca una versión nueva de atril. Si lo instalaste con el instalador, se
actualiza sola tras confirmarlo. Se desactiva en Ajustes > Atril
(`[atril] buscar_actualizaciones = false`), que también decide si `atril estado` lo comprueba.

### Atril

```bash
atril gui                        # abre la ventana y devuelve la consola
atril validar                    # valida atril.toml y el temario.toml de cada temario
atril backup ...                 # copias de la estación (ver «Backup» más abajo)
```

### DeepTutor

```bash
atril instalar                   # instala DeepTutor en app\ o completa la instalación
atril actualizar [--commit <sha>]  # última versión de la rama (o vuelta a un commit) y reaplica ajustes
atril arrancar                   # aplica parches pendientes y arranca DeepTutor (y Ollama si hace falta)
atril parar                      # detiene DeepTutor y cierra sus procesos huérfanos
atril estado                     # DeepTutor, parches, Ollama, espacio, última copia y versión nueva
atril parches [--comprobar]      # aplica los parches de atril.toml sobre app\
```

### Temarios y fuentes

```bash
atril temario lista              # temarios, KB y fuentes presentes, manuales y pendientes
atril temario crear <nombre>     # temario nuevo con una KB para todas sus fuentes
atril temario cobertura <t>      # fuentes de cada KB: fichero, estado y última comprobación
atril fuentes añadir <t> <pdf|url>  # copia un PDF o declara una URL (conserva comentarios)
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
atril backup                     # comprime la estación (sin app\) en cada destino y borra las antiguas
atril backup comprobar           # verifica la copia más reciente de cada destino y su antigüedad
atril backup restaurar [copia]   # restaura (por defecto, la más reciente); lo actual queda en <estación>.previo-*
```

Las copias son ficheros `atril-AAAAMMDD-HHMMSS.zip` (o `.tar.xz`) en las carpetas de
`[backup] destinos`: un disco externo o la carpeta de Google Drive para escritorio. No hace falta
instalar nada más. Las claves de API de DeepTutor se copian vacías: tras restaurar hay que
volver a escribirlas.

Configuración, con ejemplos: [`atril.toml`](https://isidro-rodriguez.github.io/atril/documentacion/atril-toml/) · [`temario.toml`](https://isidro-rodriguez.github.io/atril/documentacion/temario-toml/).

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

Con [Poe the Poet](https://poethepoet.natn.io/): `poe check` · `poe fix` · `poe serve` (la web).

## Enlaces

- Web y documentación: <https://isidro-rodriguez.github.io/atril/>
- Repositorio: <https://github.com/isidro-rodriguez/atril>
- PyPI: <https://pypi.org/project/atril/>

## Licencia

[MIT](https://github.com/isidro-rodriguez/atril/blob/main/LICENSE).
