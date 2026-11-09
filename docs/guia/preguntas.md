# Preguntas frecuentes

¿Windows dice que el editor es desconocido?
:   El instalador aún no está firmado digitalmente. Pulsa **Más información** y **Ejecutar de
    todas formas**. Solo pasa al instalar a mano; las actualizaciones desde la ventana no
    preguntan.

¿Necesito Ollama?
:   Solo para **indexar** tus PDF. Sin Ollama, DeepTutor funciona (por ejemplo, con un
    asistente en la nube), pero no puede buscar en tus apuntes.

¿Dónde están mis temarios y mis chats?
:   En la carpeta de tu estación, la que elegiste la primera vez. Atril nunca guarda nada tuyo
    en la carpeta del programa, así que desinstalar no borra tus datos.

¿Cómo cambio de carpeta de estación?
:   Atril usa una sola estación por ordenador, guardada en la variable de usuario
    `ATRIL_ESTACION`. Bórrala (Configuración de Windows > Variables de entorno) y, al abrir
    atril, te volverá a preguntar.

He cerrado la ventana y DeepTutor sigue funcionando. ¿Es normal?
:   Sí. Atril se queda en el **área de notificación**, junto al reloj. Para cerrarlo todo, usa
    **Salir** en el menú de su icono.

¿Cómo actualizo atril?
:   Al abrirse, atril te avisa si hay una versión nueva y se actualiza solo. Puedes desactivar
    la búsqueda en **Ajustes > Atril**.

¿Y DeepTutor?
:   En **Ajustes > Herramientas > Actualizar DeepTutor**. Si la versión nueva da problemas,
    desde la misma pestaña puedes volver a la anterior (atril te dice cuál era).

Indexar va muy lento o el ordenador se queda sin respuesta.
:   En **Ajustes > Atril > Indexado**, baja los **Hilos** (por ejemplo, a la mitad de los
    núcleos), baja el **Tamaño de lote** o sube la **Pausa**. El resultado es el mismo, solo
    cambia el ritmo.

He cancelado un indexado a medias.
:   Vuelve a pulsar **Indexar**: continúa por la fuente en la que iba.

Algo falla y no sé por qué.
:   Mira **Actividad**: cada operación guarda su detalle técnico. Si necesitas ayuda, en
    **Ajustes > Herramientas > Copiar informe** tienes un resumen para pegarlo en una
    [incidencia de GitHub](https://github.com/isidro-rodriguez/atril/issues). El informe no
    incluye claves.

¿Mis claves de API están seguras?
:   Atril nunca guarda claves en su configuración ni las muestra. Las copias de seguridad las
    guardan vacías: tras restaurar, hay que volver a escribirlas en DeepTutor.
