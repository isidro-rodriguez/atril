---
template: home.html
title: Atril
hero:
  lead: >-
    Tu tutor con inteligencia artificial para estudiar tus propios apuntes, en
    tu ordenador. Atril instala y cuida DeepTutor por ti: tú añades tus PDF y
    empiezas a preguntar.
  actions:
    - title: Descargar para Windows
      url: https://github.com/isidro-rodriguez/atril/releases/latest
      primary: true
    - title: Primeros pasos
      url: guia/primeros-pasos/
  images:
    - src: assets/images/capturas/inicio.png
      alt: >-
        Ventana de atril: apartado Inicio con DeepTutor en marcha y todas las
        herramientas instaladas
---

Gratis y de código abierto. Windows 10 u 11, sin permisos de administrador.
[DeepTutor](https://github.com/HKUDS/DeepTutor) es el tutor; atril, la ventana que lo
instala y lo mantiene.

## ¿Qué es atril?

Un **atril** es donde apoyas el libro para estudiar. Este atril sostiene a DeepTutor, un tutor
con IA que lee tus temarios y te responde citando la página exacta. DeepTutor es muy potente,
pero instalarlo y mantenerlo exige consola, Python, Node.js y bastante paciencia. Atril se
encarga de todo eso con botones.

<div class="tx-cards" markdown>

- :material-book-open-page-variant: **Estudia con tus apuntes**

    Sube los PDF de cada asignatura y pregunta lo que no entiendas. Las respuestas salen de tu
    temario, no de internet.

- :material-laptop: **Todo en tu ordenador**

    Tus temarios, tus chats y tus índices se quedan en una carpeta tuya. Haz copias de seguridad
    con un clic.

- :material-gesture-tap-button: **Sin pelearte con la consola**

    Instalar, arrancar, actualizar e indexar se hace desde una ventana sencilla. La consola sigue
    ahí si te gusta.

- :material-update: **Se cuida solo**

    Avisa cuando hay una versión nueva y se actualiza. Si algo falla, te dice qué pasa y cómo
    arreglarlo.

</div>

## Cómo funciona

1. **Instala atril** con el instalador de Windows. Es una descarga pequeña.
2. **Elige una carpeta** para tu estación de estudio. Ahí vivirá todo.
3. **Instala DeepTutor** con un botón. La primera vez tarda un rato: descarga varios GB.
4. **Crea un temario**, añade tus PDF y pulsa **Indexar**.
5. **Pulsa Arrancar** y estudia en el navegador con tu tutor.

[Ver la guía paso a paso](guia/instalacion.md){ .md-button .md-button--primary }

## ¿Qué hay en esta web?

| Sección | Para quién | Qué encontrarás |
|---|---|---|
| [Guía](guia/instalacion.md) | Todo el mundo | Instalar, primeros pasos, la ventana apartado a apartado y preguntas frecuentes. |
| [Documentación](documentacion/conceptos.md) | Quien quiere ir más allá | Conceptos, línea de comandos, `atril.toml` y `temario.toml` con ejemplos, indexado, copias y actualizaciones. |
| [Desarrollo](desarrollo/contribuir.md) | Quien quiere colaborar | Entorno, calidad, pruebas y publicación. |

El código, las versiones publicadas y el historial de cambios están en
[GitHub](https://github.com/isidro-rodriguez/atril). Atril también está en
[PyPI](https://pypi.org/project/atril/).
