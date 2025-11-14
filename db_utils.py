# db_utils.py
import sqlite3

DB_NAME = "fingerprints.db"


def connect_db():
    """Establece la conexión a la base de datos SQLite y asegura que las tablas existan."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Tabla 1: Usuarios (con datos completos y plantillas de huella)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            rut TEXT UNIQUE NOT NULL,
            matricula TEXT,
            template TEXT NOT NULL
        )
    """)
    # Tabla 2: Marcaciones (registro de asistencia)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clockings (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    return conn

def save_template(nombre, apellido, rut, matricula, template):
    """Guarda o actualiza la plantilla y datos de un usuario."""
    conn = connect_db()
    cursor = conn.cursor()
    try:
        # Intenta insertar, si el RUT ya existe, lo actualiza.
        cursor.execute(
            "INSERT INTO users (nombre, apellido, rut, matricula, template) VALUES (?, ?, ?, ?, ?)",
            (nombre, apellido, rut, matricula, template)
        )
    except sqlite3.IntegrityError:
        cursor.execute(
            "UPDATE users SET nombre = ?, apellido = ?, matricula = ?, template = ? WHERE rut = ?",
            (nombre, apellido, matricula, template, rut)
        )
    
    conn.commit()
    conn.close()

def get_all_templates():
    """Recupera todas las plantillas (templates) de la base de datos, usando el RUT como clave."""
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT rut, template FROM users")
    results = cursor.fetchall()
    conn.close()
    
    # Retorna un diccionario: { "rut": "plantilla_base64", ... }
    return {rut: template for rut, template in results}

def get_registered_users():
    """Retorna una lista de strings con la información de usuarios registrados."""
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT nombre, apellido, rut, matricula FROM users ORDER BY apellido")
    results = cursor.fetchall()
    conn.close()
    # Formatea la salida para que sea legible
    return [f"{nombre} {apellido} (RUT: {rut}, Matrícula: {matricula})" for nombre, apellido, rut, matricula in results]



# ... (save_template, get_all_templates, get_registered_users - estas se quedan igual) ...

def save_clocking(rut):
    """Registra una marcación de tiempo para el usuario por RUT."""
    conn = connect_db()
    cursor = conn.cursor()
    
    # 1. Obtener el ID del usuario
    cursor.execute("SELECT id FROM users WHERE rut = ?", (rut,))
    user_id = cursor.fetchone()
    
    if user_id:
        # 2. Insertar la marcación
        cursor.execute("INSERT INTO clockings (user_id) VALUES (?)", (user_id[0],))
        conn.commit()
        conn.close()
        return True
    
    conn.close()
    return False

def get_user_by_rut(rut):

    """Recupera los datos de un usuario por su RUT."""

    conn = connect_db()

    cursor = conn.cursor()

    cursor.execute("SELECT nombre, apellido, rut, matricula FROM users WHERE rut = ?", (rut,))

    result = cursor.fetchone()

    conn.close()

    if result:

        return {"nombre": result[0], "apellido": result[1], "rut": result[2], "matricula": result[3]}

    return None
