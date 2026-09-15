CREATE DATABASE IF NOT EXISTS rblink;
USE rblink;

CREATE TABLE IF NOT EXISTS usuarios (
	id INT AUTO_INCREMENT PRIMARY KEY,
	nombre VARCHAR(100) NOT NULL,
	correo VARCHAR(150) NOT NULL UNIQUE,
	contrasena VARCHAR(255) NOT NULL,
	rol ENUM('estudiante', 'funcionario', 'administrador') DEFAULT 'estudiante',
	fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reportes (
	id INT AUTO_INCREMENT PRIMARY KEY,
	usuario_id INT NOT NULL,
	titulo VARCHAR(150) NOT NULL,
	categoria VARCHAR(100) NOT NULL,
	descripcion TEXT NOT NULL,
	ubicacion VARCHAR(200) NOT NULL,
	imagen VARCHAR(255) NULL,
	prioridad ENUM('baja', 'media', 'alta') DEFAULT 'media',
	estado ENUM('pendiente', 'en_revision', 'en_proceso', 'resuelto') DEFAULT 'pendiente',
	fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT fk_reportes_usuario
		FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
		ON DELETE CASCADE
);

ALTER TABLE usuarios MODIFY COLUMN rol ENUM('estudiante', 'funcionario', 'administrador') DEFAULT 'estudiante';

-- admin prueba
INSERT INTO usuarios (nombre, correo, contrasena, rol)
SELECT 'Administrador', 'admin@rblink.cl', 'admin123', 'administrador'
WHERE NOT EXISTS (
	SELECT 1 FROM usuarios WHERE correo = 'admin@rblink.cl'
);