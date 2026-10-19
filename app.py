from pathlib import Path
from uuid import uuid4

from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory # type: ignore
from database import obtener_conexion

app = Flask(__name__)
app.secret_key = 'rblink_clave_secreta'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

CARPETA_CARGAS = Path(app.static_folder) / 'uploads'
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


def guardar_imagen(archivo, tipo):
	if not archivo or not archivo.filename:
		return None

	extension = Path(archivo.filename).suffix.lower()
	if extension not in EXTENSIONES_IMAGEN:
		raise ValueError('La imagen debe estar en formato JPG, JPEG o PNG.')

	nombre_archivo = f'{uuid4().hex}{extension}'
	carpeta_relativa = Path(tipo)
	carpeta = CARPETA_CARGAS / carpeta_relativa
	carpeta.mkdir(parents=True, exist_ok=True)
	archivo.save(carpeta / nombre_archivo)
	return (carpeta_relativa / nombre_archivo).as_posix()



@app.route('/')
def index():
	return send_from_directory('.', 'index.html')



@app.route('/registro', methods=['GET', 'POST'])
def registro():

	if request.method == 'POST':

		nombre = request.form['nombre']
		correo = request.form['correo']
		contrasena = request.form['contrasena']
		rol = request.form['rol']

		conexion = obtener_conexion()
		cursor = conexion.cursor()

		try:

			sql = '''
				INSERT INTO usuarios
				(nombre, correo, contrasena, rol)
				VALUES (%s, %s, %s, %s)
			'''

			cursor.execute(
				sql,
				(nombre, correo, contrasena, rol)
			)

			conexion.commit()

			return redirect(url_for('login'))

		except Exception as error:

			print('ERROR AL REGISTRAR:', error)

			conexion.rollback()

			return render_template(
				'register.html',
				error='No se pudo registrar el usuario.'
			)

		finally:

			cursor.close()
			conexion.close()

	return render_template('register.html')



@app.route('/login', methods=['GET', 'POST'])
def login():

	if request.method == 'POST':

		correo = request.form['correo']
		contrasena = request.form['contrasena']

		conexion = obtener_conexion()
		cursor = conexion.cursor(dictionary=True)

		try:

			sql = '''
				SELECT *
				FROM usuarios
				WHERE correo = %s
				AND contrasena = %s
			'''

			cursor.execute(
				sql,
				(correo, contrasena))

			usuario = cursor.fetchone()

			if usuario:

				session['usuario_id'] = usuario['id']
				session['nombre'] = usuario['nombre']
				session['correo'] = usuario['correo']
				session['rol'] = usuario['rol']

				return redirect(url_for('dashboard'))

			return render_template('login.html', error='Correo o contraseña incorrectos.')

		except Exception as error:

			print('ERROR AL INICIAR SESIÓN:', error)

			return render_template(
				'login.html',
				error='Error al conectar con la base de datos.'
			)

		finally:

			cursor.close()
			conexion.close()

	return render_template('login.html')


@app.route('/dashboard')
def dashboard():

	if 'usuario_id' not in session:
		return redirect(url_for('login'))

	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = conexion.cursor(dictionary=True)
		cursor.execute(
			'''
			SELECT
				COUNT(*) AS total,
				COALESCE(SUM(estado = 'en_revision'), 0) AS en_revision,
				COALESCE(SUM(estado = 'en_proceso'), 0) AS en_proceso,
				COALESCE(SUM(estado = 'resuelto'), 0) AS resueltos
			FROM reportes
			WHERE usuario_id = %s
			''',
			(session['usuario_id'],)
		)
		resumen = cursor.fetchone()

		cursor.execute(
			'''
			SELECT *
			FROM reportes
			WHERE usuario_id = %s
			ORDER BY fecha_creacion DESC
			LIMIT 5
			''',
			(session['usuario_id'],)
		)
		reportes = cursor.fetchall()

		return render_template(
			'dashboard.html',
			nombre=session['nombre'],
			correo=session['correo'],
			rol=session['rol'],
			reportes=reportes,
			total=resumen['total'],
			en_revision=resumen['en_revision'],
			en_proceso=resumen['en_proceso'],
			resueltos=resumen['resueltos'],
			error=None
		)
	except Exception as error:
		print('ERROR AL CARGAR EL DASHBOARD:', error)
		return render_template(
			'dashboard.html',
			nombre=session['nombre'],
			correo=session['correo'],
			rol=session['rol'],
			reportes=[],
			total=0,
			en_revision=0,
			en_proceso=0,
			resueltos=0,
			error='No se pudieron cargar tus reportes.'
		), 500
	finally:
		if cursor:
			cursor.close()
		if conexion:
			conexion.close()

@app.route('/mis_reportes')
def mis_reportes():

	if 'usuario_id' not in session:
		return redirect(url_for('login'))

	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = conexion.cursor(dictionary=True)
		sql = '''
			SELECT *
			FROM reportes
			WHERE usuario_id = %s
			ORDER BY fecha_creacion DESC
		'''

		cursor.execute(
			sql,
			(session['usuario_id'],)
		)

		reportes = cursor.fetchall()

		return render_template(
			'mis_reportes.html',
			reportes=reportes,
			creado=request.args.get('creado')
		)

	except Exception as error:

		print('ERROR AL CARGAR MIS REPORTES:', error)

		return render_template(
			'mis_reportes.html',
			reportes=[],
			error='No se pudieron cargar tus reportes.'
		), 500

	finally:

		if cursor:
			cursor.close()
		if conexion:
			conexion.close()


@app.route('/nuevo_reporte', methods=['GET', 'POST'])
def nuevo_reporte():

	if 'usuario_id' not in session:
		return redirect(url_for('login'))

	if request.method == 'POST':
		titulo = request.form.get('titulo', '').strip()
		categoria = request.form.get('categoria', '').strip()
		ubicacion = request.form.get('ubicacion', '').strip()
		descripcion = request.form.get('descripcion', '').strip()

		if not titulo or len(titulo) > 150:
			return render_template('nuevo_reporte.html', error='Ingresa un título de hasta 150 caracteres.')
		if categoria not in CATEGORIAS_REPORTE:
			return render_template('nuevo_reporte.html', error='Selecciona una categoría válida.')
		if not ubicacion or len(ubicacion) > 200:
			return render_template('nuevo_reporte.html', error='Ingresa una ubicación de hasta 200 caracteres.')
		if not descripcion:
			return render_template('nuevo_reporte.html', error='La descripción es obligatoria.')

		try:
			imagen = guardar_imagen(request.files.get('imagen'), 'reports')
		except ValueError as error:
			return render_template('nuevo_reporte.html', error=str(error))

		conexion = None
		cursor = None
		try:
			conexion = obtener_conexion()
			cursor = conexion.cursor()
			cursor.execute(
				'''
				INSERT INTO reportes
					(usuario_id, titulo, categoria, descripcion, ubicacion, imagen)
				VALUES (%s, %s, %s, %s, %s, %s)
				''',
				(session['usuario_id'], titulo, categoria, descripcion, ubicacion, imagen)
			)
			conexion.commit()
			return redirect(url_for('mis_reportes', creado=1))
		except Exception as error:
			print('ERROR AL GUARDAR EL REPORTE:', error)
			if conexion:
				conexion.rollback()
			if imagen:
				(CARPETA_CARGAS / imagen).unlink(missing_ok=True)
			return render_template(
				'nuevo_reporte.html',
				error='No se pudo guardar el reporte. Inténtalo nuevamente.'
			), 500
		finally:
			if cursor:
				cursor.close()
			if conexion:
				conexion.close()

	return render_template('nuevo_reporte.html')



@app.route('/perfil')
def perfil():

	if 'usuario_id' not in session:
		return redirect(url_for('login'))

	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = conexion.cursor(dictionary=True)
		cursor.execute(
			'SELECT foto_perfil FROM usuarios WHERE id = %s',
			(session['usuario_id'],)
		)
		usuario = cursor.fetchone()
		if not usuario:
			session.clear()
			return redirect(url_for('login'))

		return render_template(
			'perfil.html',
			nombre=session['nombre'],
			correo=session['correo'],
			rol=session['rol'],
			foto_perfil=usuario['foto_perfil']
		)
	except Exception as error:
		print('ERROR AL CARGAR EL PERFIL:', error)
		return render_template(
			'perfil.html',
			nombre=session['nombre'],
			correo=session['correo'],
			rol=session['rol'],
			foto_perfil=None,
			error='No se pudo cargar la información de tu perfil.'
		), 500
	finally:
		if cursor:
			cursor.close()
		if conexion:
			conexion.close()


@app.route('/perfil/foto', methods=['POST'])
def actualizar_foto_perfil():
	if 'usuario_id' not in session:
		return redirect(url_for('login'))

	try:
		foto_perfil = guardar_imagen(request.files.get('foto_perfil'), 'avatars')
		if not foto_perfil:
			raise ValueError('Selecciona una fotografía antes de guardar.')
	except ValueError as error:
		return redirect(url_for('perfil', error=str(error)))

	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = conexion.cursor()
		cursor.execute(
			'UPDATE usuarios SET foto_perfil = %s WHERE id = %s',
			(foto_perfil, session['usuario_id'])
		)
		if cursor.rowcount == 0:
			raise RuntimeError('No se encontró el usuario del perfil.')
		conexion.commit()
		return redirect(url_for('perfil', actualizado=1))
	except Exception as error:
		print('ERROR AL ACTUALIZAR LA FOTO DE PERFIL:', error)
		if conexion:
			conexion.rollback()
		(CARPETA_CARGAS / foto_perfil).unlink(missing_ok=True)
		return redirect(url_for('perfil', error='No se pudo actualizar la fotografía.'))
	finally:
		if cursor:
			cursor.close()
		if conexion:
			conexion.close()


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
	return send_from_directory(CARPETA_CARGAS, filename)


@app.route('/reporte/<int:reporte_id>')
def reporte(reporte_id):
	if 'usuario_id' not in session:
		return redirect(url_for('login'))

	conexion = None
	cursor = None
	try:
		conexion = obtener_conexion()
		cursor = conexion.cursor(dictionary=True)
		cursor.execute(
			'SELECT * FROM reportes WHERE id = %s AND usuario_id = %s',
			(reporte_id, session['usuario_id'])
		)
		reporte = cursor.fetchone()
		if not reporte:
			return redirect(url_for('mis_reportes'))
		return render_template('reporte.html', reporte=reporte)
	except Exception as error:
		print('ERROR AL CARGAR EL REPORTE:', error)
		return render_template('mis_reportes.html', reportes=[], error='No se pudo cargar el reporte.'), 500
	finally:
		if cursor:
			cursor.close()
		if conexion:
			conexion.close()

@app.route('/logout')
def logout():

	session.clear()

	return redirect(url_for('index'))


if __name__ == '__main__':
	app.run(debug=True)