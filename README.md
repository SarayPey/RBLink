# RBLink

*Para proyecto YUYITO, tres personas con tiempo libre y poca libertad de expresión decidieron hacer una locura que les salió cool:*

### [✨ RBLink ✨](https://saraypey.github.io/RBLink/)

### La herramienta que tu colegio **DESEA** tener.
<small>*(Las reparaciones se venden por separado).*</small>

## Version log

### v0.0.1 (alpha) — 31/Agosto/2026 (SarayPey)

- Creados `colorset.css`, `index.html` y `style.css`.
- Modificado `README.html`.

### v0.0.2 (alpha) — 31/Agosto/2026 (SarayPey)

- Creado `credits.md`.
- Modificado `colorset.css`, `index.html`, `style.css` y `README.md`.
- Nav agregado en `index.html`.
- Colores agregados en `colorset.css`.

### v0.0.3 (alpha) — 31/Agosto/2026 (SarayPey)

- Modificado `colorset.css`, `index.html`, `style.css` y `README.md`.
- Header agregado en `index.html`.

### v0.0.12 (alpha) — 14/Septiembre/2026 (SarayPey)

- Agregando animaciones.
- Ajustando errores.
- Moviendo `index.html` para que GitHub Pages lo muestre.

## Aplicación Flask

RBLink permite que estudiantes informen problemas de su establecimiento y que sus equipos los gestionen.

### Configuración local

1. Instala las dependencias del `Pipfile` (Flask y PyMySQL).
2. Configura MySQL. Por defecto, la aplicación usa `localhost`, base `rblink`, usuario `root` y contraseña `root`; puedes cambiar estos valores con `RBLINK_DB_HOST`, `RBLINK_DB_NAME`, `RBLINK_DB_USER` y `RBLINK_DB_PASSWORD`.
3. Ejecuta `database/database.sql` en MySQL. El script crea el esquema y agrega las tablas/campos que faltan en instalaciones anteriores; respalda la base antes de actualizar.
   Las cuentas preexistentes conservan su correo de acceso, pero el equipo debe completar su RUT validado para que puedan iniciar sesión con RUT.
4. Crea una cuenta desde `/registro`. Para designar al primer administrador, promueve una cuenta desde el equipo que administra la base:

   ```sql
   UPDATE usuarios
   SET rol = 'administrador', establecimiento_id = NULL
   WHERE rut = 'RUT-VALIDADO';
   ```

   Un administrador global puede crear administradores y funcionarios asociados a cada establecimiento. Los administradores con establecimiento asignado quedan limitados a ese establecimiento.
5. Define `RBLINK_SECRET_KEY` con una clave aleatoria antes de publicar la aplicación. Ejecuta con `python app.py`; `FLASK_DEBUG=1` activa el modo debug solo para desarrollo.
## Funcionalidades

- Registro de estudiantes con RUT chileno validado, establecimiento y contraseñas con hash. El inicio de sesión acepta RUT o correo; las cuentas antiguas con contraseña sin hash se actualizan al iniciar sesión.
- Establecimientos independientes. Las cuentas de estudiantes y funcionarios pertenecen a un establecimiento; sus reportes quedan aislados. Un administrador global puede cambiar el filtro de establecimiento.
- Estudiantes pueden crear, editar y borrar solo sus propios reportes. Funcionarios pueden consultar, cambiar estados y eliminar reportes de su establecimiento. Administradores pueden gestionar reportes, prioridades, responsables, usuarios y establecimientos según su alcance.
- Los reportes admiten varias imágenes, privadas detrás de comprobación de permisos, y quedan pendientes de revisión manual. Administradores y funcionarios pueden aprobar o rechazar el contenido después de verificar el texto y las fotografías.
- Asignaciones, comentarios, historial de acciones/estados y estadísticas por ámbito.
- El borrado de usuarios es una desactivación lógica para conservar sus reportes e historial.

La aplicación no incluye un modelo de inteligencia artificial ni análisis automático de imágenes: la revisión de contenido implementada es manual por el equipo autorizado del establecimiento.
