import hmac
import os
import re
from pathlib import Path
from uuid import uuid4

from flask import (
	Flask,
	abort,
	redirect,
	render_template,
	request,
	send_from_directory,
	session,
	url_for,
)
from pymysql.err import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from database import obtener_conexion, obtener_cursor

app = Flask(__name__)
app.secret_key = os.environ.get('RBLINK_SECRET_KEY') or os.urandom(32)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.config['TEMPLATES_AUTO_RELOAD'] = True

CARPETA_CARGAS = Path(app.instance_path) / 'uploads'
EXTENSIONES_IMAGEN = {'.jpg', '.jpeg', '.png'}
CATEGORIAS_REPORTE = {
	'Infraestructura',
	'Electricidad',
	'Agua y sanitarios',
	'Mobiliario',
	'Limpieza',
	'Seguridad',
	'Otro',
}
ESTADOS_REPORTE = {'pendiente', 'en_revision', 'en_proceso', 'resuelto'}
PRIORIDADES = {'baja', 'media', 'alta'}
ESTADOS_MODERACION = {'pendiente', 'aprobado', 'rechazado'}
ROLES = {'estudiante', 'funcionario', 'administrador'}


def normalizar_rut(rut):
	if rut and not re.fullmatch(r'[0-9.kK\s-]+', rut):
		return None
	digitos = re.sub(r'[^0-9Kk]', '', rut or '').upper()
	if len(digitos) < 2:
		return None

	cuerpo, digito_verificador = digitos[:-1], digitos[-1]
	if not cuerpo.isdigit() or len(cuerpo) > 10 or int(cuerpo) == 0:
		return None

	suma = sum(int(digito) * factor for digito, factor in zip(reversed(cuerpo), (2, 3, 4, 5, 6, 7) * len(cuerpo)))
	resultado = 11 - suma % 11
	calculado = '0' if resultado == 11 else 'K' if resultado == 10 else str(resultado)
	if digito_verificador != calculado:
		return None
	return f'{int(cuerpo)}-{calculado}'


def guardar_imagen(archivo, tipo='reports'):
	if not archivo or not archivo.filename:
		return None

	extension = Path(archivo.filename).suffix.lower()
	if extension not in EXTENSIONES_IMAGEN:
		raise ValueError('La imagen debe estar en formato JPG, JPEG o PNG.')

	contenido = archivo.stream.read(8)
	archivo.stream.seek(0)
	es_jpeg = contenido.startswith(b'\xff\xd8\xff')
	es_png = contenido.startswith(b'\x89PNG\r\n\x1a\n')
	if not ((extension in {'.jpg', '.jpeg'} and es_jpeg) or (extension == '.png' and es_png)):
		raise ValueError('El archivo seleccionado no parece ser una imagen JPG o PNG válida.')

	nombre_archivo = f'{uuid4().hex}{extension}'
	carpeta = CARPETA_CARGAS / tipo
	carpeta.mkdir(parents=True, exist_ok=True)
	archivo.save(carpeta / nombre_archivo)
	return f'{tipo}/{nombre_archivo}'


def eliminar_archivo(ruta):
	if ruta:
		ruta_relativa = Path(ruta)
		if ruta_relativa.is_absolute() or '..' in ruta_relativa.parts:
			raise ValueError('La ruta de la imagen almacenada no es válida.')
		for carpeta in (CARPETA_CARGAS, Path(app.static_folder) / 'uploads'):
			archivo = carpeta / ruta_relativa
			if archivo.is_file():
				archivo.unlink()
				return


def requiere_inicio_sesion():
	if 'usuario_id' not in session:
		return redirect(url_for('login'))

	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion, dictionary=True)
		cursor.execute(
			'''
			SELECT id, nombre, correo, rut, rol, establecimiento_id, activo
			FROM usuarios WHERE id = %s
			''',
			(session['usuario_id'],),
		)
		usuario = cursor.fetchone()
		if not usuario or not usuario['activo'] or usuario['rol'] not in ROLES:
			session.clear()
			return redirect(url_for('login'))
		if session.get('usuario_establecimiento_id') != usuario['establecimiento_id']:
			session['establecimiento_id'] = usuario['establecimiento_id']
		session['nombre'] = usuario['nombre']
		session['correo'] = usuario['correo']
		session['rut'] = usuario['rut']
		session['rol'] = usuario['rol']
		session['usuario_establecimiento_id'] = usuario['establecimiento_id']
	except Exception as error:
		print('ERROR AL VALIDAR LA SESIÓN:', error)
		return render_template('login.html', error='No se pudo validar la sesión con la base de datos.'), 500
	finally:
		cerrar_recursos(cursor, conexion)
	return None


def es_administrador():
	return session.get('rol') == 'administrador'


def es_personal():
	return session.get('rol') in {'administrador', 'funcionario'}


def ambito_reportes(alias='r'):
	condiciones = []
	parametros = []
	rol = session.get('rol')

	if rol == 'estudiante':
		condiciones.append(f'{alias}.usuario_id = %s')
		parametros.append(session['usuario_id'])
		condiciones.append(f'{alias}.establecimiento_id = %s')
		parametros.append(session.get('usuario_establecimiento_id'))

	if rol == 'funcionario' or (rol == 'administrador' and session.get('usuario_establecimiento_id')):
		establecimiento_id = session.get('usuario_establecimiento_id')
		condiciones.append(f'{alias}.establecimiento_id = %s')
		parametros.append(establecimiento_id)
	elif rol == 'administrador' and session.get('establecimiento_id'):
		condiciones.append(f'{alias}.establecimiento_id = %s')
		parametros.append(session['establecimiento_id'])

	return (' AND '.join(condiciones) if condiciones else '1 = 1'), parametros


def obtener_reporte(cursor, reporte_id):
	cursor.execute(
		'''
		SELECT r.*, u.nombre AS autor_nombre, u.rut AS autor_rut,
			e.nombre AS establecimiento_nombre, responsable.nombre AS responsable_nombre
		FROM reportes r
		LEFT JOIN usuarios u ON u.id = r.usuario_id
		JOIN establecimientos e ON e.id = r.establecimiento_id
		LEFT JOIN usuarios responsable ON responsable.id = r.responsable_usuario_id
		WHERE r.id = %s
		''',
		(reporte_id,),
	)
	reporte = cursor.fetchone()
	if not reporte:
		abort(404)

	condicion, parametros = ambito_reportes('r')
	cursor.execute(
		f'SELECT r.id FROM reportes r WHERE r.id = %s AND ({condicion})',
		(reporte_id, *parametros),
	)
	if not cursor.fetchone():
		abort(403)
	return reporte


def registrar_historial(cursor, reporte_id, accion, detalle, estado_anterior=None, estado_nuevo=None):
	cursor.execute(
		'''
		INSERT INTO historial_reportes
			(reporte_id, usuario_id, accion, estado_anterior, estado_nuevo, comentario)
		VALUES (%s, %s, %s, %s, %s, %s)
		''',
		(reporte_id, session['usuario_id'], accion, estado_anterior, estado_nuevo, detalle[:500]),
	)


def cerrar_recursos(cursor, conexion):
	if cursor:
		cursor.close()
	if conexion:
		conexion.close()


def obtener_establecimientos(cursor, solo_activos=True):
	condicion = 'WHERE activo = 1' if solo_activos else ''
	cursor.execute(f'SELECT id, nombre, activo FROM establecimientos {condicion} ORDER BY nombre')
	return cursor.fetchall()


@app.route('/')
def index():
	return send_from_directory(app.root_path, 'index.html')


@app.route('/registro', methods=['GET', 'POST'])
def registro():
	conexion = None
	cursor = None
	establecimientos = []
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion, dictionary=True)
		establecimientos = obtener_establecimientos(cursor)
		if request.method == 'POST':
			nombre = request.form.get('nombre', '').strip()
			correo = request.form.get('correo', '').strip().lower()
			rut = normalizar_rut(request.form.get('rut', ''))
			contrasena = request.form.get('contrasena', '')
			establecimiento_id = request.form.get('establecimiento_id', type=int)

			if not nombre or len(nombre) > 100:
				raise ValueError('Ingresa tu nombre (máximo 100 caracteres).')
			if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', correo) or len(correo) > 150:
				raise ValueError('Ingresa un correo válido (máximo 150 caracteres).')
			if not rut:
				raise ValueError('El RUT ingresado no es válido.')
			if len(contrasena) < 8:
				raise ValueError('La contraseña debe tener al menos 8 caracteres.')
			if establecimiento_id not in {item['id'] for item in establecimientos}:
				raise ValueError('Selecciona un establecimiento válido.')

			cursor.execute(
				'SELECT id FROM usuarios WHERE correo = %s OR rut = %s LIMIT 1',
				(correo, rut),
			)
			if cursor.fetchone():
				return render_template(
					'register.html',
					error='Ya existe una cuenta con ese RUT o correo. Inicia sesión o verifica los datos.',
					establecimientos=establecimientos,
				), 409

			cursor.execute(
				'''
				INSERT INTO usuarios (nombre, rut, correo, contrasena, rol, establecimiento_id)
				VALUES (%s, %s, %s, %s, 'estudiante', %s)
				''',
				(nombre, rut, correo, generate_password_hash(contrasena), establecimiento_id),
			)
			conexion.commit()
			return redirect(url_for('login', registrado=1))
	except ValueError as error:
		if conexion:
			conexion.rollback()
		return render_template('register.html', error=str(error), establecimientos=establecimientos), 400
	except IntegrityError as error:
		if conexion:
			conexion.rollback()
		if error.args and error.args[0] == 1062:
			return render_template(
				'register.html',
				error='Ya existe una cuenta con ese RUT o correo. Inicia sesión o verifica los datos.',
				establecimientos=establecimientos,
			), 409
		print('ERROR DE INTEGRIDAD AL REGISTRAR:', error)
		return render_template(
			'register.html',
			error='No se pudo guardar la cuenta por un conflicto con los datos.',
			establecimientos=establecimientos,
		), 500
	except Exception as error:
		print('ERROR AL REGISTRAR:', error)
		if conexion:
			conexion.rollback()
		return render_template(
			'register.html',
			error='No se pudo registrar la cuenta. Verifica que el RUT y correo no estén registrados.',
			establecimientos=establecimientos if cursor else [],
		), 500
	finally:
		cerrar_recursos(cursor, conexion)

	return render_template('register.html', establecimientos=establecimientos)


@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'POST':
		identificador = request.form.get('identificador', '').strip()
		contrasena = request.form.get('contrasena', '')
		rut = normalizar_rut(identificador)
		conexion = None
		cursor = None
		try:
			conexion = obtener_conexion()
			cursor = obtener_cursor(conexion, dictionary=True)
			cursor.execute(
				'''
				SELECT id, nombre, rut, correo, contrasena, rol, establecimiento_id, activo
				FROM usuarios
				WHERE rut = %s OR LOWER(correo) = LOWER(%s)
				LIMIT 1
				''',
				(rut or '', identificador),
			)
			usuario = cursor.fetchone()
			clave_valida = False
			if usuario:
				if usuario['contrasena'].startswith(('scrypt:', 'pbkdf2:')):
					clave_valida = check_password_hash(usuario['contrasena'], contrasena)
				else:
					clave_valida = hmac.compare_digest(
						str(usuario['contrasena']).encode('utf-8'),
						contrasena.encode('utf-8'),
					)

			if not usuario or not clave_valida or not usuario['activo']:
				return render_template('login.html', error='RUT/correo o contraseña incorrectos.')

			if not usuario['contrasena'].startswith(('scrypt:', 'pbkdf2:')):
				cursor.execute(
					'UPDATE usuarios SET contrasena = %s WHERE id = %s',
					(generate_password_hash(contrasena), usuario['id']),
				)
				conexion.commit()

			session.clear()
			session['usuario_id'] = usuario['id']
			session['nombre'] = usuario['nombre']
			session['correo'] = usuario['correo']
			session['rut'] = usuario['rut']
			session['rol'] = usuario['rol']
			session['usuario_establecimiento_id'] = usuario['establecimiento_id']
			session['establecimiento_id'] = usuario['establecimiento_id']
			return redirect(url_for('dashboard'))
		except Exception as error:
			print('ERROR AL INICIAR SESIÓN:', error)
			return render_template('login.html', error='No se pudo iniciar sesión por un error de conexión.')
		finally:
			cerrar_recursos(cursor, conexion)
	return render_template('login.html', registrado=request.args.get('registrado'))


@app.route('/establecimiento', methods=['POST'])
def seleccionar_establecimiento():
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	if not es_administrador() or session.get('usuario_establecimiento_id'):
		abort(403)

	seleccion = request.form.get('establecimiento_id', '')
	if seleccion and not seleccion.isdigit():
		abort(400)
	if seleccion:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion)
		try:
			cursor.execute('SELECT id FROM establecimientos WHERE id = %s AND activo = 1', (int(seleccion),))
			if not cursor.fetchone():
				abort(400)
		finally:
			cerrar_recursos(cursor, conexion)
	session['establecimiento_id'] = int(seleccion) if seleccion else None
	destino = url_for('admin_panel') if request.form.get('volver') == url_for('admin_panel') else url_for('dashboard')
	return redirect(destino)


@app.route('/dashboard')
def dashboard():
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta

	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion, dictionary=True)
		condicion, parametros = ambito_reportes()
		cursor.execute(
			f'''
			SELECT COUNT(*) AS total,
				COALESCE(SUM(r.estado = 'en_revision'), 0) AS en_revision,
				COALESCE(SUM(r.estado = 'en_proceso'), 0) AS en_proceso,
				COALESCE(SUM(r.estado = 'resuelto'), 0) AS resueltos,
				COALESCE(SUM(r.moderacion_estado = 'pendiente'), 0) AS por_revisar
			FROM reportes r WHERE {condicion}
			''',
			parametros,
		)
		resumen = cursor.fetchone()
		cursor.execute(
			f'''
			SELECT r.*, e.nombre AS establecimiento_nombre, u.nombre AS autor_nombre
			FROM reportes r
			JOIN establecimientos e ON e.id = r.establecimiento_id
			LEFT JOIN usuarios u ON u.id = r.usuario_id
			WHERE {condicion}
			ORDER BY r.fecha_creacion DESC LIMIT 5
			''',
			parametros,
		)
		reportes = cursor.fetchall()
		if es_administrador() and not session.get('usuario_establecimiento_id'):
			establecimientos = obtener_establecimientos(cursor, solo_activos=False)
		else:
			cursor.execute(
				'SELECT id, nombre, activo FROM establecimientos WHERE id = %s',
				(session.get('usuario_establecimiento_id'),),
			)
			establecimientos = cursor.fetchall()
		establecimiento_actual = next(
			(establecimiento['nombre'] for establecimiento in establecimientos
				if establecimiento['id'] == session.get('establecimiento_id')),
			None,
		)
		return render_template(
			'dashboard.html',
			nombre=session['nombre'],
			rol=session['rol'],
			reportes=reportes,
			resumen=resumen,
			establecimientos=establecimientos,
			establecimiento_actual_nombre=establecimiento_actual,
			establecimiento_actual=session.get('establecimiento_id'),
			establecimiento_fijo=session.get('usuario_establecimiento_id'),
			error=None,
		)
	except Exception as error:
		print('ERROR AL CARGAR EL DASHBOARD:', error)
		return render_template(
			'dashboard.html',
			nombre=session['nombre'],
			rol=session['rol'],
			reportes=[],
			resumen={'total': 0, 'en_revision': 0, 'en_proceso': 0, 'resueltos': 0, 'por_revisar': 0},
			establecimientos=[],
			establecimiento_actual_nombre=None,
			establecimiento_actual=None,
			establecimiento_fijo=None,
			error='No se pudieron cargar los reportes.',
		), 500
	finally:
		cerrar_recursos(cursor, conexion)


@app.route('/mis_reportes')
def mis_reportes():
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	return redirect(url_for('admin_panel') if es_personal() else url_for('lista_reportes'))


@app.route('/reportes')
def lista_reportes():
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion, dictionary=True)
		condicion, parametros = ambito_reportes()
		cursor.execute(
			f'''
			SELECT r.*, e.nombre AS establecimiento_nombre, u.nombre AS autor_nombre
			FROM reportes r
			JOIN establecimientos e ON e.id = r.establecimiento_id
			LEFT JOIN usuarios u ON u.id = r.usuario_id
			WHERE {condicion}
			ORDER BY r.fecha_creacion DESC
			''',
			parametros,
		)
		return render_template('mis_reportes.html', reportes=cursor.fetchall(), creado=request.args.get('creado'))
	except Exception as error:
		print('ERROR AL CARGAR REPORTES:', error)
		return render_template('mis_reportes.html', reportes=[], error='No se pudieron cargar los reportes.'), 500
	finally:
		cerrar_recursos(cursor, conexion)


@app.route('/nuevo_reporte', methods=['GET', 'POST'])
def nuevo_reporte():
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	if session.get('rol') != 'estudiante':
		return redirect(url_for('admin_panel'))

	if request.method == 'POST':
		titulo = request.form.get('titulo', '').strip()
		categoria = request.form.get('categoria', '').strip()
		ubicacion = request.form.get('ubicacion', '').strip()
		descripcion = request.form.get('descripcion', '').strip()
		if not titulo or len(titulo) > 150:
			return render_template('nuevo_reporte.html', error='Ingresa un título de hasta 150 caracteres.'), 400
		if categoria not in CATEGORIAS_REPORTE:
			return render_template('nuevo_reporte.html', error='Selecciona una categoría válida.'), 400
		if not ubicacion or len(ubicacion) > 200 or not descripcion:
			return render_template('nuevo_reporte.html', error='La ubicación y la descripción son obligatorias.'), 400

		imagenes = []
		conexion = None
		cursor = None
		try:
			for archivo in request.files.getlist('imagenes'):
				if archivo.filename:
					ruta = guardar_imagen(archivo)
					if ruta:
						imagenes.append(ruta)
			conexion = obtener_conexion()
			cursor = obtener_cursor(conexion)
			cursor.execute(
				'''
				INSERT INTO reportes
					(usuario_id, establecimiento_id, titulo, categoria, descripcion, ubicacion, imagen)
				VALUES (%s, %s, %s, %s, %s, %s, %s)
				''',
				(session['usuario_id'], session['usuario_establecimiento_id'], titulo, categoria, descripcion, ubicacion, imagenes[0] if imagenes else None),
			)
			reporte_id = cursor.lastrowid
			for imagen in imagenes:
				cursor.execute('INSERT INTO imagenes (reporte_id, ruta) VALUES (%s, %s)', (reporte_id, imagen))
			registrar_historial(cursor, reporte_id, 'creacion', 'Reporte enviado; pendiente de revisión manual.')
			conexion.commit()
			return redirect(url_for('reporte', reporte_id=reporte_id, creado=1))
		except ValueError as error:
			if conexion:
				conexion.rollback()
			for imagen in imagenes:
				eliminar_archivo(imagen)
			return render_template('nuevo_reporte.html', error=str(error)), 400
		except Exception as error:
			print('ERROR AL GUARDAR EL REPORTE:', error)
			if conexion:
				conexion.rollback()
			for imagen in imagenes:
				eliminar_archivo(imagen)
			return render_template('nuevo_reporte.html', error='No se pudo guardar el reporte.'), 500
		finally:
			cerrar_recursos(cursor, conexion)

	return render_template('nuevo_reporte.html')


@app.route('/reporte/<int:reporte_id>')
def reporte(reporte_id):
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta

	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion, dictionary=True)
		datos = obtener_reporte(cursor, reporte_id)
		cursor.execute('SELECT id, ruta FROM imagenes WHERE reporte_id = %s ORDER BY id', (reporte_id,))
		imagenes = cursor.fetchall()
		if not imagenes and datos.get('imagen'):
			imagenes = [{'id': None, 'ruta': datos['imagen']}]
		cursor.execute(
			'''
			SELECT c.*, u.nombre AS autor_nombre, u.rol AS autor_rol
			FROM comentarios c JOIN usuarios u ON u.id = c.usuario_id
			WHERE c.reporte_id = %s ORDER BY c.fecha
			''',
			(reporte_id,),
		)
		comentarios = cursor.fetchall()
		cursor.execute(
			'''
			SELECT h.*, u.nombre AS usuario_nombre
			FROM historial_reportes h LEFT JOIN usuarios u ON u.id = h.usuario_id
			WHERE h.reporte_id = %s ORDER BY h.fecha DESC
			''',
			(reporte_id,),
		)
		historial = cursor.fetchall()
		cursor.execute(
			'''
			SELECT id, nombre FROM usuarios
			WHERE activo = 1 AND rol IN ('funcionario', 'administrador')
				AND establecimiento_id = %s
			ORDER BY nombre
			''',
			(datos['establecimiento_id'],),
		)
		responsables = cursor.fetchall()
		return render_template(
			'reporte.html',
			reporte=datos,
			imagenes=imagenes,
			comentarios=comentarios,
			historial=historial,
			responsables=responsables,
			puede_editar=es_administrador() or session['usuario_id'] == datos['usuario_id'],
			puede_eliminar=es_personal() or session['usuario_id'] == datos['usuario_id'],
			creado=request.args.get('creado'),
		)
	except Exception as error:
		if getattr(error, 'code', None) in {403, 404}:
			raise
		print('ERROR AL CARGAR EL REPORTE:', error)
		return render_template('mis_reportes.html', reportes=[], error='No se pudo cargar el reporte.'), 500
	finally:
		cerrar_recursos(cursor, conexion)


@app.route('/reporte/<int:reporte_id>/evidencia/<int:imagen_id>')
def evidencia_reporte(reporte_id, imagen_id):
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion, dictionary=True)
		obtener_reporte(cursor, reporte_id)
		cursor.execute(
			'SELECT ruta FROM imagenes WHERE id = %s AND reporte_id = %s',
			(imagen_id, reporte_id),
		)
		imagen = cursor.fetchone()
		if not imagen:
			abort(404)
		ruta_archivo = CARPETA_CARGAS / imagen['ruta']
		carpeta = CARPETA_CARGAS if ruta_archivo.is_file() else Path(app.static_folder) / 'uploads'
		return send_from_directory(carpeta, imagen['ruta'])
	finally:
		cerrar_recursos(cursor, conexion)


@app.route('/reporte/<int:reporte_id>/evidencia')
def evidencia_heredada(reporte_id):
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion, dictionary=True)
		reporte_existente = obtener_reporte(cursor, reporte_id)
		ruta = reporte_existente.get('imagen')
		if not ruta:
			abort(404)
		ruta_archivo = CARPETA_CARGAS / ruta
		carpeta = CARPETA_CARGAS if ruta_archivo.is_file() else Path(app.static_folder) / 'uploads'
		return send_from_directory(carpeta, ruta)
	finally:
		cerrar_recursos(cursor, conexion)


@app.route('/reporte/<int:reporte_id>/editar', methods=['GET', 'POST'])
def editar_reporte(reporte_id):
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion, dictionary=True)
		datos = obtener_reporte(cursor, reporte_id)
		if not es_administrador() and datos['usuario_id'] != session['usuario_id']:
			abort(403)
		cursor.execute('SELECT id, ruta FROM imagenes WHERE reporte_id = %s ORDER BY id', (reporte_id,))
		imagenes = cursor.fetchall()

		if request.method == 'POST':
			titulo = request.form.get('titulo', '').strip()
			categoria = request.form.get('categoria', '').strip()
			ubicacion = request.form.get('ubicacion', '').strip()
			descripcion = request.form.get('descripcion', '').strip()
			if not titulo or len(titulo) > 150 or categoria not in CATEGORIAS_REPORTE:
				raise ValueError('Revisa el título y selecciona una categoría válida.')
			if not ubicacion or len(ubicacion) > 200 or not descripcion:
				raise ValueError('La ubicación y la descripción son obligatorias.')

			archivos = []
			for archivo in request.files.getlist('imagenes'):
				if archivo.filename:
					archivos.append(guardar_imagen(archivo))

			eliminar_ids = {int(valor) for valor in request.form.getlist('eliminar_imagen') if valor.isdigit()}
			rutas_eliminadas = [imagen['ruta'] for imagen in imagenes if imagen['id'] in eliminar_ids]
			for imagen in imagenes:
				if imagen['id'] in eliminar_ids:
					cursor.execute('DELETE FROM imagenes WHERE id = %s', (imagen['id'],))
			for ruta in archivos:
				cursor.execute('INSERT INTO imagenes (reporte_id, ruta) VALUES (%s, %s)', (reporte_id, ruta))

			cursor.execute(
				'''
				UPDATE reportes SET titulo = %s, categoria = %s, ubicacion = %s,
					descripcion = %s, imagen = (
						SELECT ruta FROM imagenes WHERE reporte_id = %s ORDER BY id LIMIT 1
					), moderacion_estado = 'pendiente',
					fecha_actualizacion = CURRENT_TIMESTAMP
				WHERE id = %s
				''',
				(titulo, categoria, ubicacion, descripcion, reporte_id, reporte_id),
			)
			registrar_historial(cursor, reporte_id, 'edicion', 'Se actualizaron los datos o evidencias del reporte.')
			conexion.commit()
			for ruta in rutas_eliminadas:
				eliminar_archivo(ruta)
			return redirect(url_for('reporte', reporte_id=reporte_id))

		return render_template('editar_reporte.html', reporte=datos, imagenes=imagenes)
	except ValueError as error:
		if conexion:
			conexion.rollback()
		if 'archivos' in locals():
			for ruta in archivos:
				eliminar_archivo(ruta)
		return render_template('editar_reporte.html', reporte=datos, imagenes=imagenes, error=str(error)), 400
	except Exception as error:
		if getattr(error, 'code', None) in {403, 404}:
			raise
		print('ERROR AL EDITAR EL REPORTE:', error)
		if conexion:
			conexion.rollback()
		if 'archivos' in locals():
			for ruta in archivos:
				eliminar_archivo(ruta)
		return render_template('editar_reporte.html', reporte=datos, imagenes=imagenes, error='No se pudo guardar el cambio.'), 500
	finally:
		cerrar_recursos(cursor, conexion)


@app.route('/reporte/<int:reporte_id>/gestionar', methods=['POST'])
def gestionar_reporte(reporte_id):
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	if not es_personal():
		abort(403)
	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion, dictionary=True)
		datos = obtener_reporte(cursor, reporte_id)
		estado = request.form.get('estado', datos['estado'])
		prioridad = request.form.get('prioridad', datos['prioridad'])
		moderacion = request.form.get('moderacion_estado', datos['moderacion_estado'])
		responsable_id = request.form.get('responsable_usuario_id', '')
		observacion = request.form.get('observacion', '').strip()

		if estado not in ESTADOS_REPORTE or moderacion not in ESTADOS_MODERACION:
			raise ValueError('Selecciona un estado de reporte y revisión válido.')
		if es_administrador():
			if prioridad not in PRIORIDADES:
				raise ValueError('Selecciona una prioridad válida.')
			if responsable_id and not responsable_id.isdigit():
				raise ValueError('El responsable seleccionado no es válido.')
			if responsable_id:
				cursor.execute(
					'''
					SELECT id FROM usuarios WHERE id = %s AND activo = 1
						AND rol IN ('funcionario', 'administrador') AND establecimiento_id = %s
					''',
					(int(responsable_id), datos['establecimiento_id']),
				)
				if not cursor.fetchone():
					raise ValueError('El responsable debe pertenecer al establecimiento del reporte.')
		else:
			prioridad = datos['prioridad']
			responsable_id = datos['responsable_usuario_id']

		cursor.execute(
			'''
			UPDATE reportes SET estado = %s, prioridad = %s, moderacion_estado = %s,
				moderacion_observacion = %s, responsable_usuario_id = %s,
				fecha_actualizacion = CURRENT_TIMESTAMP WHERE id = %s
			''',
			(
				estado,
				prioridad,
				moderacion,
				observacion or None,
				int(responsable_id) if responsable_id else None,
				reporte_id,
			),
		)
		if estado != datos['estado']:
			registrar_historial(cursor, reporte_id, 'cambio_estado', observacion or 'Se actualizó el estado.', datos['estado'], estado)
		if prioridad != datos['prioridad']:
			registrar_historial(cursor, reporte_id, 'cambio_prioridad', f'Prioridad: {prioridad}.')
		if moderacion != datos['moderacion_estado']:
			registrar_historial(cursor, reporte_id, 'revision', f'Revisión de contenido: {moderacion}. {observacion}')
		if (int(responsable_id) if responsable_id else None) != datos['responsable_usuario_id']:
			cursor.execute(
				'''
				INSERT INTO asignaciones (reporte_id, usuario_id, asignado_por, observacion)
				VALUES (%s, %s, %s, %s)
				''',
				(reporte_id, int(responsable_id) if responsable_id else None, session['usuario_id'], observacion or None),
			)
			registrar_historial(cursor, reporte_id, 'asignacion', 'Se cambió el responsable del reporte.')
		conexion.commit()
		return redirect(url_for('reporte', reporte_id=reporte_id))
	except ValueError as error:
		if conexion:
			conexion.rollback()
		return redirect(url_for('reporte', reporte_id=reporte_id, error=str(error)))
	except Exception as error:
		if getattr(error, 'code', None) in {403, 404}:
			raise
		print('ERROR AL GESTIONAR EL REPORTE:', error)
		if conexion:
			conexion.rollback()
		return redirect(url_for('reporte', reporte_id=reporte_id, error='No se pudo actualizar el reporte.'))
	finally:
		cerrar_recursos(cursor, conexion)


@app.route('/reporte/<int:reporte_id>/comentarios', methods=['POST'])
def agregar_comentario(reporte_id):
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion, dictionary=True)
		obtener_reporte(cursor, reporte_id)
		comentario = request.form.get('comentario', '').strip()
		if not comentario or len(comentario) > 1000:
			raise ValueError('El comentario es obligatorio y admite hasta 1000 caracteres.')
		cursor.execute(
			'INSERT INTO comentarios (reporte_id, usuario_id, comentario) VALUES (%s, %s, %s)',
			(reporte_id, session['usuario_id'], comentario),
		)
		registrar_historial(cursor, reporte_id, 'comentario', 'Se agregó un comentario.')
		conexion.commit()
		return redirect(url_for('reporte', reporte_id=reporte_id))
	except ValueError as error:
		if conexion:
			conexion.rollback()
		return redirect(url_for('reporte', reporte_id=reporte_id, error=str(error)))
	except Exception as error:
		if getattr(error, 'code', None) in {403, 404}:
			raise
		print('ERROR AL GUARDAR COMENTARIO:', error)
		if conexion:
			conexion.rollback()
		return redirect(url_for('reporte', reporte_id=reporte_id, error='No se pudo guardar el comentario.'))
	finally:
		cerrar_recursos(cursor, conexion)


@app.route('/reporte/<int:reporte_id>/eliminar', methods=['POST'])
def eliminar_reporte(reporte_id):
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion, dictionary=True)
		datos = obtener_reporte(cursor, reporte_id)
		if not es_personal() and datos['usuario_id'] != session['usuario_id']:
			abort(403)
		cursor.execute('SELECT ruta FROM imagenes WHERE reporte_id = %s', (reporte_id,))
		rutas = [fila['ruta'] for fila in cursor.fetchall()]
		if datos.get('imagen') and datos['imagen'] not in rutas:
			rutas.append(datos['imagen'])
		cursor.execute('DELETE FROM reportes WHERE id = %s', (reporte_id,))
		conexion.commit()
		for ruta in rutas:
			eliminar_archivo(ruta)
		return redirect(url_for('admin_panel') if es_personal() else url_for('lista_reportes', eliminado=1))
	except Exception as error:
		if getattr(error, 'code', None) in {403, 404}:
			raise
		print('ERROR AL ELIMINAR EL REPORTE:', error)
		if conexion:
			conexion.rollback()
		return redirect(url_for('lista_reportes', error='No se pudo eliminar el reporte.'))
	finally:
		cerrar_recursos(cursor, conexion)


@app.route('/admin')
def admin_panel():
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	if not es_personal():
		abort(403)

	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion, dictionary=True)
		condicion, parametros = ambito_reportes()
		cursor.execute(
			f'''
			SELECT r.*, e.nombre AS establecimiento_nombre, u.nombre AS autor_nombre,
				responsable.nombre AS responsable_nombre
			FROM reportes r
			JOIN establecimientos e ON e.id = r.establecimiento_id
			LEFT JOIN usuarios u ON u.id = r.usuario_id
			LEFT JOIN usuarios responsable ON responsable.id = r.responsable_usuario_id
			WHERE {condicion} ORDER BY r.fecha_creacion DESC
			''',
			parametros,
		)
		reportes = cursor.fetchall()
		cursor.execute(
			f'''
			SELECT COUNT(*) AS total,
				COALESCE(SUM(r.estado = 'pendiente'), 0) AS pendientes,
				COALESCE(SUM(r.estado = 'en_proceso'), 0) AS en_proceso,
				COALESCE(SUM(r.estado = 'resuelto'), 0) AS resueltos,
				COALESCE(SUM(r.moderacion_estado = 'pendiente'), 0) AS por_revisar
			FROM reportes r WHERE {condicion}
			''',
			parametros,
		)
		resumen = cursor.fetchone()
		cursor.execute(
			'''
			SELECT u.id, u.nombre, u.rut, u.correo, u.rol, u.activo, e.nombre AS establecimiento_nombre
			FROM usuarios u LEFT JOIN establecimientos e ON e.id = u.establecimiento_id
			WHERE u.establecimiento_id = %s OR %s IS NULL ORDER BY u.nombre
			''',
			(session.get('usuario_establecimiento_id'), session.get('usuario_establecimiento_id')),
		)
		usuarios = cursor.fetchall()
		if es_administrador() and not session.get('usuario_establecimiento_id'):
			establecimientos = obtener_establecimientos(cursor, solo_activos=False)
		elif session.get('usuario_establecimiento_id'):
			cursor.execute(
				'SELECT id, nombre, activo FROM establecimientos WHERE id = %s',
				(session['usuario_establecimiento_id'],),
			)
			establecimientos = cursor.fetchall()
		else:
			establecimientos = []
		return render_template(
			'admin.html',
			reportes=reportes,
			resumen=resumen,
			usuarios=usuarios,
			establecimientos=establecimientos,
			establecimiento_actual=session.get('establecimiento_id'),
			establecimiento_fijo=session.get('usuario_establecimiento_id'),
			puede_administrar=es_administrador(),
			puede_gestionar_establecimientos=es_administrador() and not session.get('usuario_establecimiento_id'),
		)
	except Exception as error:
		print('ERROR AL CARGAR ADMINISTRACIÓN:', error)
		return render_template('admin.html', reportes=[], resumen={}, usuarios=[], establecimientos=[], error='No se pudo cargar el panel de administración.'), 500
	finally:
		cerrar_recursos(cursor, conexion)


@app.route('/admin/usuarios', methods=['POST'])
def crear_usuario():
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	if not es_administrador():
		abort(403)
	conexion = None
	cursor = None
	try:
		nombre = request.form.get('nombre', '').strip()
		rut = normalizar_rut(request.form.get('rut', ''))
		correo = request.form.get('correo', '').strip().lower()
		rol = request.form.get('rol', '')
		contrasena = request.form.get('contrasena', '')
		establecimiento_id = request.form.get('establecimiento_id', type=int)
		if not nombre or len(nombre) > 100 or not rut or rol not in ROLES or len(contrasena) < 8 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', correo) or len(correo) > 150:
			raise ValueError('Completa los datos con un nombre, RUT válido, rol y contraseña de al menos 8 caracteres.')
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion)
		cursor.execute(
			'SELECT id FROM establecimientos WHERE id = %s AND activo = 1',
			(establecimiento_id,),
		)
		if not cursor.fetchone():
			raise ValueError('Selecciona un establecimiento activo.')
		if session.get('usuario_establecimiento_id') and establecimiento_id != session['usuario_establecimiento_id']:
			abort(403)
		cursor.execute(
			'''
			INSERT INTO usuarios (nombre, rut, correo, contrasena, rol, establecimiento_id)
			VALUES (%s, %s, %s, %s, %s, %s)
			''',
			(nombre, rut, correo, generate_password_hash(contrasena), rol, establecimiento_id),
		)
		conexion.commit()
		return redirect(url_for('admin_panel', usuario_creado=1))
	except ValueError as error:
		if conexion:
			conexion.rollback()
		return redirect(url_for('admin_panel', error=str(error)))
	except Exception as error:
		if getattr(error, 'code', None) == 403:
			raise
		print('ERROR AL CREAR USUARIO:', error)
		if conexion:
			conexion.rollback()
		return redirect(url_for('admin_panel', error='No se pudo crear el usuario. Verifica que el RUT o correo no estén repetidos.'))
	finally:
		cerrar_recursos(cursor, conexion)


@app.route('/admin/usuarios/<int:usuario_id>/estado', methods=['POST'])
def cambiar_estado_usuario(usuario_id):
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	if not es_administrador():
		abort(403)
	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion, dictionary=True)
		cursor.execute('SELECT id, rol, activo, establecimiento_id FROM usuarios WHERE id = %s', (usuario_id,))
		usuario = cursor.fetchone()
		if not usuario:
			abort(404)
		if session.get('usuario_establecimiento_id') and usuario['establecimiento_id'] != session['usuario_establecimiento_id']:
			abort(403)
		if usuario['activo'] and usuario_id == session['usuario_id']:
			abort(403)
		if usuario['activo'] and usuario['rol'] == 'administrador':
			cursor.execute(
				'SELECT COUNT(*) AS total FROM usuarios WHERE rol = %s AND activo = 1 AND id <> %s AND establecimiento_id <=> %s',
				('administrador', usuario_id, usuario['establecimiento_id']),
			)
			if cursor.fetchone()['total'] == 0:
				return redirect(url_for('admin_panel', error='No se puede desactivar al último administrador de este establecimiento.'))
		cursor.execute('UPDATE usuarios SET activo = %s WHERE id = %s', (not usuario['activo'], usuario_id))
		conexion.commit()
		return redirect(url_for('admin_panel'))
	except Exception as error:
		if getattr(error, 'code', None) in {403, 404}:
			raise
		print('ERROR AL CAMBIAR ESTADO DEL USUARIO:', error)
		if conexion:
			conexion.rollback()
		return redirect(url_for('admin_panel', error='No se pudo actualizar el estado del usuario.'))
	finally:
		cerrar_recursos(cursor, conexion)


@app.route('/admin/establecimientos', methods=['POST'])
def crear_establecimiento():
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	if not es_administrador() or session.get('usuario_establecimiento_id'):
		abort(403)
	nombre = request.form.get('nombre', '').strip()
	descripcion = request.form.get('descripcion', '').strip()
	if not nombre or len(nombre) > 150:
		return redirect(url_for('admin_panel', error='El nombre del establecimiento es obligatorio (máximo 150 caracteres).'))
	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion)
		cursor.execute(
			'INSERT INTO establecimientos (nombre, descripcion) VALUES (%s, %s)',
			(nombre, descripcion or None),
		)
		conexion.commit()
		return redirect(url_for('admin_panel', establecimiento_creado=1))
	except Exception as error:
		print('ERROR AL CREAR ESTABLECIMIENTO:', error)
		if conexion:
			conexion.rollback()
		return redirect(url_for('admin_panel', error='No se pudo crear el establecimiento. Revisa que el nombre no esté repetido.'))
	finally:
		cerrar_recursos(cursor, conexion)


@app.route('/admin/establecimientos/<int:establecimiento_id>/estado', methods=['POST'])
def cambiar_estado_establecimiento(establecimiento_id):
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	if not es_administrador() or session.get('usuario_establecimiento_id'):
		abort(403)
	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion, dictionary=True)
		cursor.execute('SELECT activo FROM establecimientos WHERE id = %s', (establecimiento_id,))
		establecimiento = cursor.fetchone()
		if not establecimiento:
			abort(404)
		cursor.execute('UPDATE establecimientos SET activo = %s WHERE id = %s', (not establecimiento['activo'], establecimiento_id))
		conexion.commit()
		return redirect(url_for('admin_panel'))
	except Exception as error:
		if getattr(error, 'code', None) == 404:
			raise
		print('ERROR AL ACTUALIZAR ESTABLECIMIENTO:', error)
		if conexion:
			conexion.rollback()
		return redirect(url_for('admin_panel', error='No se pudo actualizar el establecimiento.'))
	finally:
		cerrar_recursos(cursor, conexion)


@app.route('/perfil')
def perfil():
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion, dictionary=True)
		cursor.execute('SELECT foto_perfil FROM usuarios WHERE id = %s', (session['usuario_id'],))
		usuario = cursor.fetchone()
		return render_template(
			'perfil.html',
			nombre=session['nombre'],
			correo=session['correo'],
			rut=session.get('rut'),
			rol=session['rol'],
			foto_perfil=usuario['foto_perfil'] if usuario else None,
		)
	finally:
		cerrar_recursos(cursor, conexion)


@app.route('/perfil/foto', methods=['POST'])
def actualizar_foto_perfil():
	respuesta = requiere_inicio_sesion()
	if respuesta:
		return respuesta
	try:
		ruta = guardar_imagen(request.files.get('foto_perfil'), 'avatars')
	except ValueError as error:
		return redirect(url_for('perfil', error=str(error)))
	if not ruta:
		return redirect(url_for('perfil', error='Selecciona una fotografía antes de guardar.'))
	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = obtener_cursor(conexion)
		cursor.execute('UPDATE usuarios SET foto_perfil = %s WHERE id = %s', (ruta, session['usuario_id']))
		conexion.commit()
		return redirect(url_for('perfil', actualizado=1))
	except Exception as error:
		print('ERROR AL ACTUALIZAR FOTO DE PERFIL:', error)
		if conexion:
			conexion.rollback()
		eliminar_archivo(ruta)
		return redirect(url_for('perfil', error='No se pudo actualizar la fotografía.'))
	finally:
		cerrar_recursos(cursor, conexion)


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
	if not filename.startswith('avatars/'):
		abort(404)
	carpeta = CARPETA_CARGAS if (CARPETA_CARGAS / filename).is_file() else Path(app.static_folder) / 'uploads'
	return send_from_directory(carpeta, filename)


@app.route('/static/uploads/<path:_filename>')
def bloquear_evidencia_publica(_filename):
	app.logger.debug('Bloqueo de acceso público a uploads estáticos: %s', _filename)
	abort(404)


@app.route('/logout')
def logout():
	session.clear()
	return redirect(url_for('index'))


if __name__ == '__main__':
	app.run(debug=os.environ.get('FLASK_DEBUG') == '1')
