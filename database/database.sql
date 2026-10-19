CREATE DATABASE IF NOT EXISTS rblink CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE rblink;

CREATE TABLE IF NOT EXISTS establecimientos (
	id INT AUTO_INCREMENT PRIMARY KEY,
	nombre VARCHAR(150) NOT NULL UNIQUE,
	descripcion VARCHAR(500) NULL,
	activo TINYINT(1) NOT NULL DEFAULT 1,
	fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO establecimientos (nombre, descripcion)
SELECT 'Establecimiento principal', 'Establecimiento inicial de RBLink'
WHERE NOT EXISTS (SELECT 1 FROM establecimientos);

CREATE TABLE IF NOT EXISTS usuarios (
	id INT AUTO_INCREMENT PRIMARY KEY,
	nombre VARCHAR(100) NOT NULL,
	rut VARCHAR(12) NULL,
	correo VARCHAR(150) NOT NULL UNIQUE,
	contrasena VARCHAR(255) NOT NULL,
	rol ENUM('estudiante', 'funcionario', 'administrador') NOT NULL DEFAULT 'estudiante',
	establecimiento_id INT NULL,
	activo TINYINT(1) NOT NULL DEFAULT 1,
	foto_perfil VARCHAR(255) NULL,
	fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	CONSTRAINT fk_usuarios_establecimiento
		FOREIGN KEY (establecimiento_id) REFERENCES establecimientos(id)
);

SET @sql = IF(
	(SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'usuarios' AND COLUMN_NAME = 'rut') = 0,
	'ALTER TABLE usuarios ADD COLUMN rut VARCHAR(12) NULL',
	'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF(
	(SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'usuarios' AND COLUMN_NAME = 'establecimiento_id') = 0,
	'ALTER TABLE usuarios ADD COLUMN establecimiento_id INT NULL',
	'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF(
	(SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'usuarios' AND COLUMN_NAME = 'activo') = 0,
	'ALTER TABLE usuarios ADD COLUMN activo TINYINT(1) NOT NULL DEFAULT 1',
	'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF(
	(SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'usuarios' AND COLUMN_NAME = 'foto_perfil') = 0,
	'ALTER TABLE usuarios ADD COLUMN foto_perfil VARCHAR(255) NULL',
	'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
	(SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'usuarios' AND INDEX_NAME = 'uq_usuarios_rut') = 0,
	'ALTER TABLE usuarios ADD UNIQUE INDEX uq_usuarios_rut (rut)',
	'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @establecimiento_principal = (SELECT id FROM establecimientos ORDER BY id LIMIT 1);
UPDATE usuarios SET establecimiento_id = @establecimiento_principal WHERE establecimiento_id IS NULL;

SET @sql = IF(
	(SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'usuarios' AND CONSTRAINT_NAME = 'fk_usuarios_establecimiento') = 0,
	'ALTER TABLE usuarios ADD CONSTRAINT fk_usuarios_establecimiento FOREIGN KEY (establecimiento_id) REFERENCES establecimientos(id)',
	'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS reportes (
	id INT AUTO_INCREMENT PRIMARY KEY,
	usuario_id INT NOT NULL,
	establecimiento_id INT NULL,
	responsable_usuario_id INT NULL,
	titulo VARCHAR(150) NOT NULL,
	categoria VARCHAR(100) NOT NULL,
	descripcion TEXT NOT NULL,
	ubicacion VARCHAR(200) NOT NULL,
	imagen VARCHAR(255) NULL,
	prioridad ENUM('baja', 'media', 'alta') DEFAULT 'media',
	estado ENUM('pendiente', 'en_revision', 'en_proceso', 'resuelto') DEFAULT 'pendiente',
	moderacion_estado ENUM('pendiente', 'aprobado', 'rechazado') NOT NULL DEFAULT 'pendiente',
	moderacion_observacion VARCHAR(500) NULL,
	fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT fk_reportes_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
	CONSTRAINT fk_reportes_establecimiento FOREIGN KEY (establecimiento_id) REFERENCES establecimientos(id),
	CONSTRAINT fk_reportes_responsable FOREIGN KEY (responsable_usuario_id) REFERENCES usuarios(id)
);

SET @sql = IF(
	(SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'reportes' AND COLUMN_NAME = 'establecimiento_id') = 0,
	'ALTER TABLE reportes ADD COLUMN establecimiento_id INT NULL',
	'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF(
	(SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'reportes' AND COLUMN_NAME = 'responsable_usuario_id') = 0,
	'ALTER TABLE reportes ADD COLUMN responsable_usuario_id INT NULL',
	'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF(
	(SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'reportes' AND COLUMN_NAME = 'moderacion_estado') = 0,
	"ALTER TABLE reportes ADD COLUMN moderacion_estado ENUM('pendiente', 'aprobado', 'rechazado') NOT NULL DEFAULT 'pendiente'",
	'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF(
	(SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'reportes' AND COLUMN_NAME = 'moderacion_observacion') = 0,
	'ALTER TABLE reportes ADD COLUMN moderacion_observacion VARCHAR(500) NULL',
	'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE reportes r
JOIN usuarios u ON u.id = r.usuario_id
SET r.establecimiento_id = COALESCE(r.establecimiento_id, u.establecimiento_id)
WHERE r.establecimiento_id IS NULL;

SET @sql = IF(
	(SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'reportes' AND CONSTRAINT_NAME = 'fk_reportes_establecimiento') = 0,
	'ALTER TABLE reportes ADD CONSTRAINT fk_reportes_establecimiento FOREIGN KEY (establecimiento_id) REFERENCES establecimientos(id)',
	'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF(
	(SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'reportes' AND CONSTRAINT_NAME = 'fk_reportes_responsable') = 0,
	'ALTER TABLE reportes ADD CONSTRAINT fk_reportes_responsable FOREIGN KEY (responsable_usuario_id) REFERENCES usuarios(id)',
	'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS imagenes (
	id INT AUTO_INCREMENT PRIMARY KEY,
	reporte_id INT NOT NULL,
	ruta VARCHAR(500) NOT NULL,
	fecha_subida TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	UNIQUE KEY uq_imagen_reporte_ruta (reporte_id, ruta),
	CONSTRAINT fk_imagenes_reporte FOREIGN KEY (reporte_id) REFERENCES reportes(id) ON DELETE CASCADE
);

INSERT INTO imagenes (reporte_id, ruta)
SELECT r.id, r.imagen FROM reportes r
WHERE r.imagen IS NOT NULL
	AND NOT EXISTS (SELECT 1 FROM imagenes i WHERE i.reporte_id = r.id AND i.ruta = r.imagen);

CREATE TABLE IF NOT EXISTS asignaciones (
	id INT AUTO_INCREMENT PRIMARY KEY,
	reporte_id INT NOT NULL,
	usuario_id INT NULL,
	asignado_por INT NOT NULL,
	fecha_asignacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	fecha_finalizacion TIMESTAMP NULL,
	observacion VARCHAR(500) NULL,
	CONSTRAINT fk_asignaciones_reporte FOREIGN KEY (reporte_id) REFERENCES reportes(id) ON DELETE CASCADE,
	CONSTRAINT fk_asignaciones_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL,
	CONSTRAINT fk_asignaciones_asignador FOREIGN KEY (asignado_por) REFERENCES usuarios(id)
);

CREATE TABLE IF NOT EXISTS historial_reportes (
	id INT AUTO_INCREMENT PRIMARY KEY,
	reporte_id INT NOT NULL,
	usuario_id INT NULL,
	accion VARCHAR(50) NOT NULL,
	estado_anterior VARCHAR(30) NULL,
	estado_nuevo VARCHAR(30) NULL,
	comentario VARCHAR(500) NULL,
	fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	CONSTRAINT fk_historial_reporte FOREIGN KEY (reporte_id) REFERENCES reportes(id) ON DELETE CASCADE,
	CONSTRAINT fk_historial_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS comentarios (
	id INT AUTO_INCREMENT PRIMARY KEY,
	reporte_id INT NOT NULL,
	usuario_id INT NOT NULL,
	comentario VARCHAR(1000) NOT NULL,
	fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	CONSTRAINT fk_comentarios_reporte FOREIGN KEY (reporte_id) REFERENCES reportes(id) ON DELETE CASCADE,
	CONSTRAINT fk_comentarios_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

-- El primer administrador se promueve desde una cuenta creada por el equipo:
-- UPDATE usuarios SET rol = 'administrador' WHERE rut = 'RUT-VALIDADO';
