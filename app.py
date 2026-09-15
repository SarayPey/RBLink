from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory # type: ignore
from database import obtener_conexion

app = Flask(__name__)

app.secret_key = "rblink_clave_secreta"



@app.route("/")
def index():
	return send_from_directory(".", "index.html")



@app.route("/registro", methods=["GET", "POST"])
def registro():

	if request.method == "POST":

		nombre = request.form["nombre"]
		correo = request.form["correo"]
		contrasena = request.form["contrasena"]
		rol = request.form["rol"]

		conexion = obtener_conexion()
		cursor = conexion.cursor()

		try:

			sql = """
				INSERT INTO usuarios
				(nombre, correo, contrasena, rol)
				VALUES (%s, %s, %s, %s)
			"""

			cursor.execute(
				sql,
				(nombre, correo, contrasena, rol)
			)

			conexion.commit()

			return redirect(url_for("login"))

		except Exception as error:

			print("ERROR AL REGISTRAR:", error)

			conexion.rollback()

			return render_template(
				"register.html",
				error="No se pudo registrar el usuario."
			)

		finally:

			cursor.close()
			conexion.close()

	return render_template("register.html")



@app.route("/login", methods=["GET", "POST"])
def login():

	if request.method == "POST":

		correo = request.form["correo"]
		contrasena = request.form["contrasena"]

		conexion = obtener_conexion()
		cursor = conexion.cursor(dictionary=True)

		try:

			sql = """
				SELECT *
				FROM usuarios
				WHERE correo = %s
				AND contrasena = %s
			"""

			cursor.execute(
				sql,
				(correo, contrasena)
			)

			usuario = cursor.fetchone()

			if usuario:

				session["usuario_id"] = usuario["id"]
				session["nombre"] = usuario["nombre"]
				session["correo"] = usuario["correo"]
				session["rol"] = usuario["rol"]

				return redirect(url_for("dashboard"))

			return render_template(
				"login.html",
				error="Correo o contraseña incorrectos."
			)

		except Exception as error:

			print("ERROR AL INICIAR SESIÓN:", error)

			return render_template(
				"login.html",
				error="Error al conectar con la base de datos."
			)

		finally:

			cursor.close()
			conexion.close()

	return render_template("login.html")



@app.route("/dashboard")
def dashboard():

	if "usuario_id" not in session:
		return redirect(url_for("login"))

	return render_template(
		"dashboard.html",
		nombre=session["nombre"],
		correo=session["correo"],
		rol=session["rol"]
	)

@app.route("/mis_reportes")
def mis_reportes():

	if "usuario_id" not in session:
		return redirect(url_for("login"))

	conexion = obtener_conexion()
	cursor = conexion.cursor(dictionary=True)

	try:

		sql = """
			SELECT *
			FROM reportes
			WHERE usuario_id = %s
			ORDER BY fecha_creacion DESC
		"""

		cursor.execute(
			sql,
			(session["usuario_id"],)
		)

		reportes = cursor.fetchall()

		return render_template(
			"mis_reportes.html",
			reportes=reportes
		)

	except Exception as error:

		print("ERROR AL CARGAR MIS REPORTES:", error)

		return render_template(
			"mis_reportes.html",
			reportes=[]
		)

	finally:

		cursor.close()
		conexion.close()


@app.route("/nuevo_reporte")
def nuevo_reporte():

	if "usuario_id" not in session:
		return redirect(url_for("login"))

	return render_template("nuevo_reporte.html")



@app.route("/perfil")
def perfil():

	if "usuario_id" not in session:
		return redirect(url_for("login"))

	return render_template(
		"perfil.html",
		nombre=session["nombre"],
		correo=session["correo"],
		rol=session["rol"]
	)

@app.route("/logout")
def logout():

	session.clear()

	return redirect(url_for("index"))


if __name__ == "__main__":
	app.run(debug=True)