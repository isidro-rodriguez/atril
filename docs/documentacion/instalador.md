# Instalador y actualizaciones

## El instalador de Windows

Cada versión publicada trae `atril-X.Y.Z-setup.exe` en su
[release de GitHub](https://github.com/isidro-rodriguez/atril/releases). Lo construye y lo
prueba la integración continua (instalar, comprobar `atril --version`, actualizar con un
entorno en uso y desinstalar).

| Aspecto | Detalle |
|---|---|
| Permisos | Por usuario, sin administrador. |
| Carpeta | `%LOCALAPPDATA%\Programs\Atril` |
| Contenido | `uv.exe` (versión fija, con su SHA-256 comprobado), el icono y la licencia. |
| Al instalar | `uv tool install atril==X.Y.Z` con un Python 3.13 propio. Todo queda en la carpeta del programa, sin caché. La salida va a `instalacion.log`. |
| Entornos | Uno por versión, en `herramientas\<versión>`: actualizar nunca borra el que está en uso, y los anteriores se borran después. |
| Accesos | Menú Inicio (y escritorio, opcional), con el mismo identificador que la ventana para que Windows los agrupe. |
| Consola | `bin\` se añade al final del PATH del usuario: `atril` funciona en cualquier terminal nueva. |
| Atril abierto | Instalar o desinstalar pide cerrar atril antes. |
| Desinstalar | Borra la carpeta del programa y su entrada del PATH. **Nunca** la estación, las copias ni `ATRIL_ESTACION`. |

!!! note "Aviso de SmartScreen"
    El instalador aún no está firmado, así que Windows avisa de un editor desconocido al
    abrirlo descargado del navegador.

### Parámetros

Además de los de Inno Setup (`/SILENT`, `/VERYSILENT`, `/LOG=…`), el instalador entiende:

| Parámetro | Efecto |
|---|---|
| `/esperar=<pid>` | Espera a que termine ese proceso antes de instalar (la ventana pasa el suyo al actualizarse). |
| `/abrir=si` | En modo silencioso, vuelve a abrir la ventana al terminar. |

## Actualizaciones de atril

Al abrirse, la ventana consulta la última release de GitHub, salvo que
`[atril] buscar_actualizaciones = false`.

| Instalado con | Qué pasa |
|---|---|
| El instalador | Pregunta. Si aceptas, descarga el instalador nuevo, comprueba su SHA-256 contra el publicado, lo lanza en silencio y se cierra; el instalador espera a que la ventana termine, instala y la vuelve a abrir. |
| `uv tool` u otro medio | Ofrece abrir la página de novedades: actualiza por el mismo medio. |

Sin conexión no dice nada. Si la release aún no tiene instalador (se publica unos minutos
después), lo ofrecerá la próxima vez.

La consola no se actualiza sola (Windows no deja sustituir `atril.exe` mientras se ejecuta):
`atril estado` avisa de la versión nueva y dice cómo instalarla.

## Actualizaciones de DeepTutor

`atril actualizar` (o **Ajustes > Herramientas > Actualizar DeepTutor**):

1. Para DeepTutor si está en marcha.
2. Comprueba que `app\` sigue el repositorio y la rama de `atril.toml` y que no tiene cambios.
3. Deshace los parches y trae la versión nueva (`fetch --depth 1` + `reset --hard`).
4. Reinstala dependencias: Python si hay cambios o si la versión de Python no coincide; la web
   solo si cambia su fichero de bloqueo.
5. Vuelve a aplicar configuración, parches y ajustes del indexado, y pasa el diagnóstico.
6. Vuelve a arrancar DeepTutor si estaba en marcha.

El comando muestra el hash de la versión anterior: `atril actualizar --commit <hash>` vuelve a
ella si la nueva da problemas.
