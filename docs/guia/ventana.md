# La ventana

La ventana de atril tiene seis apartados a la izquierda y, abajo, el estado de DeepTutor y
Ollama, la operación en curso y la versión.

## Inicio

El estado general en una frase («En marcha», «Necesita atención»…) y los botones para
arrancar, parar o abrir DeepTutor en el navegador. Debajo, cada herramienta con su estado y,
si hace falta, un botón para instalarla o arrancarla. Pulsar un logotipo abre la web de esa
herramienta.

![Inicio](../assets/images/capturas/inicio.png){ .at-shot }

## Temarios

El temario elegido arriba es el mismo en Temarios y en Biblioteca. Aquí ves sus **bases de
conocimiento** (KB) con cuántas fuentes tienen, cuántas están indexadas y cuántas faltan.

| Botón | Qué hace |
|---|---|
| Nuevo temario | Crea un temario vacío con una KB para todas sus fuentes. |
| Indexar | Añade a la KB las fuentes nuevas, una a una. Se puede cancelar y continuar después. |
| Reindexar | Sustituye las fuentes que han cambiado y quita las retiradas. |
| Renombrar… | Cambia el nombre visible (la carpeta no cambia). |
| Abrir carpeta | Abre la carpeta del temario. |
| Borrar temario | Lo borra para siempre, tras dos confirmaciones (la segunda pide escribir su nombre). |

![Temarios](../assets/images/capturas/temarios.png){ .at-shot }

## Biblioteca

Las fuentes (PDF) del temario, con su KB y su estado. Se puede buscar y ordenar pulsando la
cabecera de cada columna.

![Biblioteca](../assets/images/capturas/biblioteca.png){ .at-shot }

## Backups

Las copias de cada destino, con su fecha, tamaño y si están verificadas.

| Botón | Qué hace |
|---|---|
| Hacer backup | Comprime la estación (sin el programa de DeepTutor, que se reinstala) en cada destino y borra las más antiguas. |
| Comprobar | Lee la copia más reciente de cada destino para asegurar que está entera. |
| Restaurar… | Vuelve a una copia. Lo que había se conserva aparte, por si acaso. |
| Abrir destino | Abre la carpeta de las copias. |

![Backups](../assets/images/capturas/backups.png){ .at-shot }

!!! warning "Las claves no viajan en las copias"
    Si tu asistente usa una clave (de una API en la nube), la copia la guarda vacía. Tras
    restaurar, vuelve a escribirla en DeepTutor.

## Actividad

Todo lo que ha hecho la ventana, con su resultado. Al elegir una operación, abajo aparece su
detalle técnico. Si algo falla, aquí está la explicación.

![Actividad](../assets/images/capturas/actividad.png){ .at-shot }

## Ajustes

Todo lo que se puede configurar, en pestañas:

| Pestaña | Contenido |
|---|---|
| DeepTutor | El asistente (proveedor y modelo) y el buscador web. |
| Atril | Actualizaciones, destinos de las copias y, al final, Ollama y el ritmo del indexado. |
| Avanzado | Lo que obliga a reinstalar DeepTutor o a reindexar: repositorio, rama, Python, paquetes, parches, puertos y parámetros del indexado. |
| Herramientas | Instalar o reparar, actualizar DeepTutor, aplicar ajustes, diagnóstico, validar la configuración, copiar un informe para pedir ayuda y volver a una versión anterior de DeepTutor. |

![Ajustes, pestaña Atril](../assets/images/capturas/ajustes-atril.png){ .at-shot }

Al guardar, atril comprueba el fichero entero y te dice qué hace falta para que el cambio
surta efecto (aplicarlo, reinstalar o reindexar).

## Área de notificación

Si cierras la ventana con DeepTutor en marcha, atril se queda junto al reloj de Windows. Con
el botón derecho sobre su icono:

| Opción | Qué hace |
|---|---|
| Mostrar atril | Vuelve a la ventana (también con un clic en el icono). |
| Abrir DeepTutor | Lo abre en el navegador. |
| Arrancar o parar DeepTutor | Según su estado. |
| Hacer backup | Hace una copia sin abrir la ventana. |
| Ver actividad | Abre la ventana en Actividad. |
| Salir | Para DeepTutor y el Ollama que abrió atril, y cierra atril. |

Con la ventana oculta, atril te avisa con notificaciones de Windows al terminar cada operación
o si DeepTutor se para.
