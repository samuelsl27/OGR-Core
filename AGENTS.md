# OGR Core

Núcleo compartido de la suite: geometría, materiales, modelo de proyecto, cargas, soportes,
hidráulica, estadística, anotaciones, DXF, informes, y la malla y la filtración por elementos
finitos.

**Dos niveles de nombre**: *OpenGeoRock* (u *OGR Suite*) es el paraguas de los programas de la
suite; **OGR Core** es la biblioteca que comparten. La distribución se llama `ogr-core` y el paquete
de importación, `ogr_core`. La usan **OGR Slip2D** (equilibrio límite) y, más adelante, **OGR
FEM2D** (elementos finitos).

Autor y titular del copyright: Samuel Sáez López (UPCT). Licencia AGPL-3.0-or-later.

> Este archivo es el **contrato de trabajo** con cualquier agente de IA. Se consulta antes de cada
> acción. Deriva del `AGENTS.md` de OGR Slip2D, de donde sale el código.

> **Estado (2026-10-27):** el código llegó de OGR Slip2D (commit `2d68c29`, fase F1 de su spec
> `spec/features/009-extraer-ogr-core/`). Slip2D aún no depende de este repositorio: lo hará en la
> fase F3. Hasta entonces, un cambio en `ogr_core` hay que hacerlo en los dos sitios.

---

## Stack

- **Lenguaje**: Python 3.11+, con anotaciones de tipo donde aclaren.
- **Numérico**: NumPy, SciPy. **Geometría**: Shapely. **CAD**: ezdxf. **Informes**: reportlab.
  **Resultados**: h5py.
- **Sin Qt** y sin gráficas: el núcleo se importa desde un script, un cuaderno o un test sin
  arrastrar ninguna interfaz.
- **Tests**: el runner de la suite, que vive aquí (`ogr_core/testing/runner.py`) y que usan también
  los programas; aporta un `pytest` simulado. **No** hay pytest real instalado.

## Comandos

```bash
python tests/_runner.py          # toda la suite
python tests/_runner.py geometry # solo los archivos que contengan eso
python tests/_runner.py -k erfc  # solo los tests con ese nombre
pip install -e .                 # instalar en editable
```

Para desarrollar un programa contra este núcleo, se instalan los dos en editable: primero este
repositorio y después el del programa. El runner del programa dice en su cabecera de qué árbol, de
qué commit y de qué versión sale `ogr_core`, y se niega a ejecutar si esa versión no es la que el
programa fija.

## Capas

`ogr_core` **no importa ningún programa ni ninguna capa superior**: ni `ogr_slip2d`, ni `ogr_fem2d`
(el programa 03), ni `ogr_api`, `ogr_gui`, `ogr_cli`, `ogr_mcp`, `PySide6` o `mcp`. Lo comprueba un
test, que lee el código y también mira `sys.modules` en tiempo de ejecución.

El núcleo **contiene un solver**: el de filtración, en `ogr_core/fem/`, porque lo usan los dos
programas (decisión P1 de la especificación 009). Lo que solo usa un programa vive en ese programa.

Una regla que necesitan dos programas vive aquí, y los programas la preguntan; copiarla es cómo
acaban diciendo cosas distintas.

---

## Las siete reglas de la suite

Son las de OGR Slip2D. Cada una existe porque su ausencia causó un problema real.

1. **El trabajo numérico se valida contra algo EXTERNO**: un caso publicado, una solución cerrada o
   una identidad analítica. Nunca una captura de lo que el código imprime hoy.
2. **El núcleo no traduce.** Todo mensaje que vaya a ver el usuario sale como un código con su
   plantilla inglesa (`ogr_core.messages`), y la interfaz de cada programa lo traduce. Ningún texto
   del núcleo se compone a mano con los números dentro.
3. **Toda acción debe ser alcanzable desde un menú.** Aquí no hay menús: la cumple cada programa con
   lo que ofrece del núcleo.
4. **Cada archivo lleva su cabecera de licencia** (SPDX AGPL-3.0-or-later y copyright).
5. **Los tests no filtran estado**: lo global (unidades, cachés de módulo) se restaura.
6. **Las anomalías se reportan ANTES de corregirlas**, con la evidencia.
7. **Ningún ajuste puede no hacer nada**: toda opción lleva el test que demuestra que mueve el
   número.

## Reglas propias del núcleo

8. **Un cambio aquí se prueba también en los programas.** Antes de etiquetar una versión: la suite
   completa de este repositorio y la de cada programa que vaya a fijarla, sin argumentos.
9. **Versiones**: serie propia desde 0.1.0. El número va en dos sitios, `pyproject.toml` y
   `ogr_core/__init__.py`, y un test falla si discrepan. Cada versión lleva su etiqueta `vX.Y.Z` y
   su changelog; los programas fijan la etiqueta, nunca una rama.
10. **Un cambio que obliga a cambiar un programa** se anota en el changelog con lo que ese programa
    tiene que cambiar.

---

## Flujo de trabajo

- **Antes de una tarea no trivial, propón un plan y espera el OK del propietario.**
- **Una tarea a la vez.** Al terminar, di qué cambiaste y qué probaste.
- **Si no estás seguro al 80 %, pregunta. No inventes**, sobre todo en fórmulas.
- Cada versión con su changelog en `docs/changelog/`, registrando **qué se encontró**, no solo qué
  se escribió.

## No hagas

- **No instales dependencias sin preguntar**, y comprueba su licencia (compatible con AGPL-3.0).
- **No uses `pytest` directamente**: el runner aporta uno simulado.
- **No cambies `LICENSE`, `CLA.md` ni las cabeceras SPDX** sin pedirlo.
- **No añadas telemetría ni llamadas de red** que no se hayan pedido.
- **No toques un test de validación** para hacer pasar un cambio: si falla, el fallo está en el
  código o en el valor de referencia, y averiguar cuál es el trabajo.

## Documentación de referencia

La documentación de programas comerciales sirve para entender **qué** hace una función y **cómo**
se comporta. **El código no puede contener ninguna referencia a esos productos ni a sus marcas**, ni
copiar su texto. Las fórmulas se citan por su **fuente científica original** (autor y año).

---

© 2026 Samuel Sáez López — UPCT — AGPL-3.0-or-later
