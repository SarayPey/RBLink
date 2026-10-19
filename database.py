import os

import pymysql
from pymysql.cursors import DictCursor


DB_CONFIG = {
	'host': os.environ.get('RBLINK_DB_HOST', 'localhost'),
	'user': os.environ.get('RBLINK_DB_USER', 'root'),
	'password': os.environ.get('RBLINK_DB_PASSWORD', 'root'),
	'database': os.environ.get('RBLINK_DB_NAME', 'rblink'),
	'charset': 'utf8mb4',
}


def obtener_conexion():
	return pymysql.connect(**DB_CONFIG)


def obtener_cursor(conexion, dictionary=False):
	return conexion.cursor(DictCursor if dictionary else None)
