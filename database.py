import mysql.connector # type: ignore


DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "database": "rblink",
}


def obtener_conexion():
    return mysql.connector.connect(**DB_CONFIG)
