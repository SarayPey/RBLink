import unittest
from unittest.mock import Mock, patch

from flask import session
from werkzeug.security import check_password_hash

from app import app, ambito_reportes, normalizar_rut


class RutValidationTests(unittest.TestCase):
	def test_formats_a_valid_rut(self):
		self.assertEqual(normalizar_rut('12.345.678-5'), '12345678-5')

	def test_accepts_k_verifier(self):
		self.assertEqual(normalizar_rut('6-k'), '6-K')

	def test_rejects_invalid_ruts(self):
		self.assertIsNone(normalizar_rut('12.345.678-9'))
		self.assertIsNone(normalizar_rut('texto'))
		self.assertIsNone(normalizar_rut('123456789012345-0'))


class ReportScopeTests(unittest.TestCase):
	def test_student_scope_is_limited_to_their_own_reports(self):
		with app.test_request_context('/'):
			session.update(rol='estudiante', usuario_id=15, usuario_establecimiento_id=2)
			condition, parameters = ambito_reportes()
		self.assertEqual(condition, 'r.usuario_id = %s AND r.establecimiento_id = %s')
		self.assertEqual(parameters, [15, 2])

	def test_staff_scope_is_limited_to_their_establishment(self):
		with app.test_request_context('/'):
			session.update(rol='funcionario', usuario_id=15, usuario_establecimiento_id=2)
			condition, parameters = ambito_reportes()
		self.assertEqual(condition, 'r.establecimiento_id = %s')
		self.assertEqual(parameters, [2])

	def test_global_admin_can_filter_or_see_all_establishments(self):
		with app.test_request_context('/'):
			session.update(rol='administrador', usuario_establecimiento_id=None, establecimiento_id=3)
			filtered_condition, filtered_parameters = ambito_reportes()
			session['establecimiento_id'] = None
			all_condition, all_parameters = ambito_reportes()
		self.assertEqual(filtered_condition, 'r.establecimiento_id = %s')
		self.assertEqual(filtered_parameters, [3])
		self.assertEqual(all_condition, '1 = 1')
		self.assertEqual(all_parameters, [])


class AccessControlTests(unittest.TestCase):
	def setUp(self):
		app.config.update(TESTING=True, SECRET_KEY='test')
		self.client = app.test_client()

	def test_student_cannot_open_management_panel(self):
		with self.client.session_transaction() as stored_session:
			stored_session['usuario_id'] = 4
			stored_session['rol'] = 'estudiante'
		with patch('app.obtener_conexion'), patch('app.obtener_cursor') as cursor_factory:
			cursor_factory.return_value.fetchone.return_value = {
				'id': 4, 'nombre': 'Estudiante', 'correo': 'estudiante@example.cl',
				'rut': '12345678-5', 'rol': 'estudiante', 'establecimiento_id': 2, 'activo': 1,
			}
			self.assertEqual(self.client.get('/admin').status_code, 403)

	def test_anonymous_user_is_redirected_from_reports(self):
		response = self.client.get('/reporte/1')
		self.assertEqual(response.status_code, 302)
		self.assertIn('/login', response.headers['Location'])

	def test_legacy_report_images_are_not_publicly_served(self):
		self.assertEqual(self.client.get('/static/uploads/reports/example.jpg').status_code, 404)

	def test_student_cannot_create_another_user(self):
		with self.client.session_transaction() as stored_session:
			stored_session['usuario_id'] = 4
			stored_session['rol'] = 'estudiante'
		with patch('app.obtener_conexion'), patch('app.obtener_cursor') as cursor_factory:
			cursor_factory.return_value.fetchone.return_value = {
				'id': 4, 'nombre': 'Estudiante', 'correo': 'estudiante@example.cl',
				'rut': '12345678-5', 'rol': 'estudiante', 'establecimiento_id': 2, 'activo': 1,
			}
			self.assertEqual(self.client.post('/admin/usuarios').status_code, 403)

	def test_legacy_plaintext_password_can_login_and_is_upgraded(self):
		conexion = Mock()
		cursor = Mock()
		cursor.fetchone.return_value = {
			'id': 1, 'nombre': 'Administrador', 'rut': '111-1',
			'correo': 'admin@example.cl', 'contrasena': 'clave-legada',
			'rol': 'administrador', 'establecimiento_id': None, 'activo': 1,
		}
		with patch('app.obtener_conexion', return_value=conexion), patch('app.obtener_cursor', return_value=cursor):
			response = self.client.post('/login', data={
				'identificador': 'admin@example.cl',
				'contrasena': 'clave-legada',
			})
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.headers['Location'], '/dashboard')
		with self.client.session_transaction() as stored_session:
			self.assertEqual(stored_session['rol'], 'administrador')
		actualizar = next(call for call in cursor.execute.call_args_list if 'UPDATE usuarios SET contrasena' in call.args[0])
		self.assertTrue(actualizar.args[1][0].startswith(('scrypt:', 'pbkdf2:')))
		conexion.commit.assert_called_once()

	def test_establishment_selection_does_not_redirect_off_site(self):
		with self.client.session_transaction() as stored_session:
			stored_session['usuario_id'] = 1
			stored_session['rol'] = 'administrador'
			stored_session['usuario_establecimiento_id'] = None
		with patch('app.obtener_conexion'), patch('app.obtener_cursor') as cursor_factory:
			cursor_factory.return_value.fetchone.return_value = {
				'id': 1, 'nombre': 'Admin', 'correo': 'admin@example.cl',
				'rut': None, 'rol': 'administrador', 'establecimiento_id': None, 'activo': 1,
			}
			response = self.client.post(
				'/establecimiento',
				data={'establecimiento_id': '', 'volver': 'https://example.com'},
			)
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.headers['Location'], '/dashboard')

	def test_deactivated_user_session_is_revoked(self):
		with self.client.session_transaction() as stored_session:
			stored_session['usuario_id'] = 4
		with patch('app.obtener_conexion'), patch('app.obtener_cursor') as cursor_factory:
			cursor_factory.return_value.fetchone.return_value = {
				'id': 4, 'nombre': 'Estudiante', 'correo': 'estudiante@example.cl',
				'rut': None, 'rol': 'estudiante', 'establecimiento_id': 2, 'activo': 0,
			}
			response = self.client.get('/perfil')
		self.assertEqual(response.status_code, 302)
		self.assertIn('/login', response.headers['Location'])

	def test_registration_shows_duplicate_account_instead_of_server_error(self):
		conexion = Mock()
		cursor = Mock()
		cursor.fetchall.return_value = [{'id': 2, 'nombre': 'Liceo'}]
		cursor.fetchone.return_value = {'id': 9}
		with patch('app.obtener_conexion', return_value=conexion), patch('app.obtener_cursor', return_value=cursor):
			response = self.client.post('/registro', data={
				'nombre': 'Estudiante',
				'rut': '12.345.678-5',
				'correo': 'existente@example.cl',
				'establecimiento_id': '2',
				'contrasena': 'contraseña-segura',
			})
		self.assertEqual(response.status_code, 409)
		self.assertIn('Ya existe una cuenta', response.get_data(as_text=True))
		self.assertFalse(any('INSERT INTO usuarios' in str(call) for call in cursor.execute.call_args_list))
		conexion.rollback.assert_not_called()

	def test_all_templates_are_valid_jinja(self):
		for name in app.jinja_env.list_templates():
			with self.subTest(template=name):
				app.jinja_env.get_template(name)


class PasswordRecoveryDisabledTests(unittest.TestCase):
	def setUp(self):
		app.config.update(TESTING=True, SECRET_KEY='test')
		self.client = app.test_client()

	def test_recovery_is_unavailable_from_login_and_direct_routes(self):
		response = self.client.get('/login')
		self.assertEqual(response.status_code, 200)
		self.assertNotIn('/recuperar-contrasena', response.get_data(as_text=True))
		self.assertEqual(self.client.get('/recuperar-contrasena').status_code, 404)
		self.assertEqual(self.client.get('/restablecer-contrasena/token').status_code, 404)
		self.assertEqual(self.client.post('/recuperar-contrasena').status_code, 404)


if __name__ == '__main__':
	unittest.main()
