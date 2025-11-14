# db_utils.py
import sqlite3

DB_NAME = "fingerprints.db"


def connect_db():
    """Establece la conexión a la base de datos SQLite y asegura que las tablas existan."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Tabla 1: Usuarios (plantillas de huella)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
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

def save_template(name, template):
    """Guarda o actualiza la plantilla de un usuario."""
    conn = connect_db()
    cursor = conn.cursor()
    try:
        # Intenta insertar, si el nombre ya existe, lo actualiza.
        cursor.execute("INSERT INTO users (name, template) VALUES (?, ?)", (name, template))
    except sqlite3.IntegrityError:
        cursor.execute("UPDATE users SET template = ? WHERE name = ?", (template, name))
    
    conn.commit()
    conn.close()

def get_all_templates():
    """Recupera todas las plantillas (templates) de la base de datos."""
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name, template FROM users")
    results = cursor.fetchall()
    conn.close()
    
    # Retorna un diccionario: { "nombre": "plantilla_base64", ... }
    return {name: template for name, template in results}

def get_registered_users():
    """Retorna una lista de nombres de usuario registrados."""
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users")
    results = cursor.fetchall()
    conn.close()
    return [row[0] for row in results]



# ... (save_template, get_all_templates, get_registered_users - estas se quedan igual) ...

def save_clocking(username):
    """Registra una marcación de tiempo para el usuario por nombre."""
    conn = connect_db()
    cursor = conn.cursor()
    
    # 1. Obtener el ID del usuario
    cursor.execute("SELECT id FROM users WHERE name = ?", (username,))
    user_id = cursor.fetchone()
    
    if user_id:
        # 2. Insertar la marcación
        cursor.execute("INSERT INTO clockings (user_id) VALUES (?)", (user_id[0],))
        conn.commit()
        conn.close()
        return True
    
    conn.close()
    return False

def get_user_id_by_name(username):
    """Obtiene el ID de usuario para usar en marcaciones/reportes."""
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE name = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None