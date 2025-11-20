# db_utils.py (FINAL: Schema y Funciones)
import sqlite3
from datetime import datetime

DB_NAME = "fingerprints.db"

def connect_db():
    """Establece la conexión a la base de datos SQLite y asegura que ambas tablas existan."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Tabla ALUMNOS (Estructura final con 4 nombres/apellidos)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ALUMNOS (
            id_alumno INTEGER PRIMARY KEY,
            primer_nombre TEXT NOT NULL,
            segundo_nombre TEXT,         
            apellido_paterno TEXT NOT NULL,
            apellido_materno TEXT NOT NULL,
            rut TEXT UNIQUE NOT NULL,    
            huella_plantilla TEXT,
            hora_max_tardanza TEXT DEFAULT '08:15:00',
            max_inasistencias INTEGER DEFAULT 3,
            num_atrasos INTEGER DEFAULT 0,
            activo BOOLEAN DEFAULT 1,
            fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 2. Tabla ASISTENCIAS (Registro de Marcación)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ASISTENCIAS (
            id_asistencia INTEGER PRIMARY KEY,
            id_alumno INTEGER NOT NULL,
            fecha DATE NOT NULL,
            hora_entrada TIME,
            hora_salida TIME,
            estado TEXT,      -- 'presente' / 'tardanza' / 'ausente'
            notificado BOOLEAN DEFAULT 0,
            observaciones TEXT,
            
            FOREIGN KEY (id_alumno) REFERENCES ALUMNOS(id_alumno),
            UNIQUE (id_alumno, fecha)
        )
    """)
    
    conn.commit()
    return conn

def get_alumno_full_name(rut: str) -> str:
    """Recupera el nombre completo del alumno dado su RUT."""
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT primer_nombre, apellido_paterno
            FROM ALUMNOS
            WHERE rut = ?
        """, (rut,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            # Junta el primer nombre y el apellido paterno
            return f"{result[0]} {result[1]}"
        return "Alumno Desconocido"
    except Exception as e:
        print(f"DB Error al buscar nombre: {e}")
        conn.close()
        return "Error de Consulta"

def save_template(pn, sn, ap, am, rut, huella, hora_max):
    """
    Guarda o actualiza (ON CONFLICT) la información completa de un alumno y su huella.
    Acepta los 7 parámetros de la nueva estructura.
    """
    conn = connect_db()
    cursor = conn.cursor()
    try:
        data = (pn, sn, ap, am, rut, huella, hora_max)
        
        cursor.execute("""
            INSERT INTO ALUMNOS (primer_nombre, segundo_nombre, apellido_paterno, apellido_materno, rut, huella_plantilla, hora_max_tardanza) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rut) DO UPDATE SET 
                primer_nombre=excluded.primer_nombre, 
                segundo_nombre=excluded.segundo_nombre, 
                apellido_paterno=excluded.apellido_paterno,
                apellido_materno=excluded.apellido_materno,
                huella_plantilla=excluded.huella_plantilla,
                hora_max_tardanza=excluded.hora_max_tardanza
        """, data)
        conn.commit()
        print(f"DB: Alumno {rut} guardado/actualizado con éxito.")
    except Exception as e:
        print(f"DB Error al guardar alumno: {e}")
    finally:
        conn.close()

def get_all_templates():
    """Recupera los RUT (como claves de huella) y las plantillas para la identificación."""
    conn = connect_db()
    cursor = conn.cursor()
    # Se selecciona 'rut' y 'huella_plantilla'
    cursor.execute("SELECT rut, huella_plantilla FROM ALUMNOS")
    results = cursor.fetchall()
    conn.close()
    
    return {rut: template for rut, template in results}

def get_registered_users():
    """Retorna una lista de RUT de alumnos registrados."""
    conn = connect_db()
    cursor = conn.cursor()
    # Se selecciona 'rut'
    cursor.execute("SELECT rut FROM ALUMNOS")
    results = cursor.fetchall()
    conn.close()
    return [row[0] for row in results]

def get_all_alumnos_details():
    """Recupera todos los detalles de los alumnos para la vista de administración (listado)."""
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            rut, primer_nombre, segundo_nombre, apellido_paterno, apellido_materno, hora_max_tardanza
        FROM ALUMNOS
        ORDER BY apellido_paterno, apellido_materno, primer_nombre
    """)
    columns = [desc[0] for desc in cursor.description]
    results = cursor.fetchall()
    conn.close()
    return columns, results


def get_clockings_for_month(month: int, year: int):
    """
    Recupera los registros de asistencia para un mes y año dados.
    Junta la tabla ASISTENCIAS con ALUMNOS para el reporte de Excel.
    """
    conn = connect_db()
    cursor = conn.cursor()
    
    start_date = f"{year}-{month:02d}-01"
    
    cursor.execute("""
        SELECT 
            A.rut, 
            A.primer_nombre || ' ' || A.apellido_paterno AS Nombre_Completo,
            S.fecha,
            S.hora_entrada,
            S.estado
        FROM ASISTENCIAS S
        JOIN ALUMNOS A ON S.id_alumno = A.id_alumno
        WHERE S.fecha BETWEEN ? AND date(?, '+1 month', '-1 day') 
        ORDER BY A.apellido_paterno, S.fecha
    """, (start_date, start_date))
    
    columns = [desc[0] for desc in cursor.description]
    results = cursor.fetchall()
    conn.close()
    
    return columns, results

def save_clocking(rut):
    """Registra una marcación de asistencia para el alumno y actualiza el contador de atrasos."""
    conn = connect_db()
    cursor = conn.cursor()
    
    try:
        current_date = datetime.now().strftime('%Y-%m-%d')
        current_time = datetime.now().strftime('%H:%M:%S')
        
        # 1. Obtener el ID del alumno, la hora máxima y el número de atrasos actual
        cursor.execute("SELECT id_alumno, hora_max_tardanza, num_atrasos FROM ALUMNOS WHERE rut = ?", (rut,))
        result = cursor.fetchone()
        
        if result:
            user_id, max_tardy_time, num_atrasos = result
            
            # 2. Determinar el estado (Lógica de negocio)
            max_tardy_dt = datetime.strptime(max_tardy_time, '%H:%M:%S').time()
            current_time_dt = datetime.strptime(current_time, '%H:%M:%S').time()
            
            if current_time_dt <= max_tardy_dt:
                estado = 'presente'
            else:
                estado = 'tardanza'
                # Solo incrementar si es una tardanza Y si la marcación es la primera del día
                
            # 3. Intentar Insertar la marcación (solo hora_entrada)
            # USAMOS 'ON CONFLICT DO NOTHING'
            cursor.execute("""
                INSERT INTO ASISTENCIAS (id_alumno, fecha, hora_entrada, estado) 
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id_alumno, fecha) DO NOTHING 
            """, (user_id, current_date, current_time, estado))
            
            # 4. Verificar si la inserción ocurrió (solo si no hubo conflicto)
            if cursor.rowcount > 0:
                # Si se insertó una nueva fila y el estado es 'tardanza', actualizamos el contador.
                if estado == 'tardanza':
                    num_atrasos += 1
                    cursor.execute("UPDATE ALUMNOS SET num_atrasos = ? WHERE id_alumno = ?", (num_atrasos, user_id))
                
                conn.commit()
                # Devuelve el estado, la hora y el número de atrasos actualizado
                return f"entrada ({estado})", current_time, num_atrasos
            else:
                # Si hubo conflicto, significa que el alumno ya marcó hoy.
                # No se hace nada y se notifica.
                # Para devolver el estado, necesitamos consultarlo. 
                # Simplificamos devolviendo "ya registrado"
                return "ya registrado", None, num_atrasos

        # Si no hay usuario encontrado
        return None, None, None

    except Exception as e:
        print(f"Error al registrar marcación: {e}")
        return None, None, None
    finally:
        conn.close()

def reset_monthly_delays():
    """Resetea el contador de atrasos de todos los alumnos a 0."""
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE ALUMNOS SET num_atrasos = 0")
        conn.commit()
        print("DB: El contador de atrasos ha sido reseteado para todos los alumnos.")
        return True
    except Exception as e:
        print(f"DB Error al resetear los atrasos: {e}")
        return False
    finally:
        conn.close()