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
            curso TEXT DEFAULT '1ro Medio',
            hora_max_tardanza TEXT DEFAULT '08:15:00',
            max_inasistencias INTEGER DEFAULT 3,
            num_atrasos INTEGER DEFAULT 0,
            max_atrasos_warning INTEGER DEFAULT 10,
            activo BOOLEAN DEFAULT 1,
            fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # MIGRACIÓN: Añadir columna 'curso' si no existe (para bases de datos existentes)
    try:
        cursor.execute("ALTER TABLE ALUMNOS ADD COLUMN curso TEXT DEFAULT '1ro Medio'")
        print("DB: Columna 'curso' añadida exitosamente.")
    except sqlite3.OperationalError:
        # La columna ya existe
        pass
    
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

def save_template(pn, sn, ap, am, rut, huella, hora_max, atrasos_max_w, curso="1ro Medio"):
    """
    Guarda o actualiza (ON CONFLICT) la información completa de un alumno y su huella.
    Acepta los 9 parámetros de la nueva estructura.
    """
    conn = connect_db()
    cursor = conn.cursor()
    try:
        data = (pn, sn, ap, am, rut, huella, hora_max, atrasos_max_w, curso)
        
        cursor.execute("""
            INSERT INTO ALUMNOS (
                primer_nombre,
                segundo_nombre,
                apellido_paterno,
                apellido_materno,
                rut,
                huella_plantilla,
                hora_max_tardanza,
                max_atrasos_warning,
                curso,
                num_atrasos
            ) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(rut) DO UPDATE SET 
                primer_nombre=excluded.primer_nombre, 
                segundo_nombre=excluded.segundo_nombre, 
                apellido_paterno=excluded.apellido_paterno,
                apellido_materno=excluded.apellido_materno,
                huella_plantilla=excluded.huella_plantilla,
                hora_max_tardanza=excluded.hora_max_tardanza,
                max_atrasos_warning=excluded.max_atrasos_warning,
                curso=excluded.curso,
                num_atrasos=0
        """, data)
        
        # NUEVO: Para que el Excel coincida con el contador en 0, debemos "perdonar" los atrasos históricos.
        # Cambiamos el estado de 'tardanza' a 'presente' en la tabla ASISTENCIAS para este alumno.
        cursor.execute("""
            UPDATE ASISTENCIAS 
            SET estado = 'presente' 
            WHERE id_alumno = (SELECT id_alumno FROM ALUMNOS WHERE rut = ?) 
            AND estado IN ('tardanza', 'atraso')
        """, (rut,))
        
        conn.commit()
        print(f"DB: Alumno {rut} guardado/actualizado con éxito. Historial de atrasos limpiado.")
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
            rut, primer_nombre, segundo_nombre, apellido_paterno, apellido_materno, curso, hora_max_tardanza
        FROM ALUMNOS
        ORDER BY curso, apellido_paterno, apellido_materno, primer_nombre
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

def save_clocking(rut, full_name=None, hora_max_tardanza=None):
    """
    Registra la hora de entrada y actualiza el contador de atrasos.
    Devuelve (estado, hora, num_atrasos_actualizado, max_atrasos_warning)
    """
    conn = connect_db()
    cursor = conn.cursor()
    current_date = datetime.now().strftime('%Y-%m-%d')
    current_time = datetime.now().strftime('%H:%M:%S')

    try:
        # Obtener ID, hora_max_tardanza (de BD), num_atrasos actual y max_atrasos_warning
        cursor.execute("SELECT id_alumno, hora_max_tardanza, num_atrasos, max_atrasos_warning FROM ALUMNOS WHERE rut = ?", (rut,))
        result = cursor.fetchone()
        
        if not result:
            return None, None, None, None

        user_id, db_hora_max, num_atrasos, max_atrasos_warning = result

        # Si se pasa hora_max_tardanza como override, usarla; si no, usar la de la BD
        effective_max_time = hora_max_tardanza or db_hora_max or "23:59:59"

        # Determinar estado comparando horas
        try:
            max_tardy_dt = datetime.strptime(effective_max_time, '%H:%M:%S').time()
            current_time_dt = datetime.strptime(current_time, '%H:%M:%S').time()
        except Exception:
            # En caso de formato distinto, asumir presente para evitar falsos positivos
            max_tardy_dt = None
            current_time_dt = None

        if max_tardy_dt and current_time_dt:
            estado = 'presente' if current_time_dt <= max_tardy_dt else 'tardanza'
        else:
            estado = 'presente'

        # Intentar insertar la marcación (solo hora_entrada). ON CONFLICT DO NOTHING
        cursor.execute("""
            INSERT INTO ASISTENCIAS (id_alumno, fecha, hora_entrada, estado) 
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id_alumno, fecha) DO NOTHING 
        """, (user_id, current_date, current_time, estado))
        
        # Si se insertó una nueva fila y el estado es 'tardanza', actualizar contador.
        if cursor.rowcount > 0:
            if estado == 'tardanza':
                num_atrasos += 1
                cursor.execute("UPDATE ALUMNOS SET num_atrasos = ? WHERE id_alumno = ?", (num_atrasos, user_id))
            conn.commit()
            return f"entrada ({estado})", current_time, num_atrasos, max_atrasos_warning
        else:
            # Ya registrado hoy: devolver contador actual y umbral
            return "ya registrado", None, num_atrasos, max_atrasos_warning

    except Exception as e:
        print(f"Error al registrar marcación: {e}")
        return None, None, None, None
    finally:
        conn.close()

def reset_all_delays():
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

def get_alumno_details_by_rut(rut):
    """
    Obtiene los detalles de un alumno por su RUT.
    Devuelve (id_alumno, full_name, num_atrasos, max_atrasos_warning, hora_max_tardanza)
    """
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                id_alumno, primer_nombre, segundo_nombre, apellido_paterno, apellido_materno,
                num_atrasos, max_atrasos_warning, hora_max_tardanza, curso
            FROM ALUMNOS
            WHERE rut = ?
        """, (rut,))
        row = cursor.fetchone()
        if row:
            id_alumno, p_nombre, s_nombre, a_paterno, a_materno, num_atrasos, max_atrasos_warning, hora_max_tardanza, curso = row
            full_name = f"{p_nombre} {s_nombre or ''} {a_paterno} {a_materno}"
            return id_alumno, full_name.strip(), num_atrasos, max_atrasos_warning, hora_max_tardanza, curso
        return None, None, None, None, None, None
    except Exception as e:
        print(f"Error al obtener detalles del alumno: {e}")
        return None, None, None, None, None, None
    finally:
        conn.close()

def update_alumno_details(rut, pn, sn, ap, am, hora_max, max_warn, curso):
    """
    Actualiza los datos personales y de configuración de un alumno existente.
    Retorna True si se actualizó correctamente, False si hubo error o no se encontró.
    """
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE ALUMNOS
            SET primer_nombre = ?,
                segundo_nombre = ?,
                apellido_paterno = ?,
                apellido_materno = ?,
                hora_max_tardanza = ?,
                max_atrasos_warning = ?,
                curso = ?
            WHERE rut = ?
        """, (pn, sn, ap, am, hora_max, max_warn, curso, rut))
        
        if cursor.rowcount > 0:
            conn.commit()
            print(f"DB: Alumno {rut} actualizado correctamente.")
            return True
        else:
            print(f"DB: No se encontró alumno con RUT {rut} para actualizar.")
            return False
    except Exception as e:
        print(f"DB Error al actualizar alumno: {e}")
        return False
    finally:
        conn.close()

def promote_students():
    """
    Promueve a los estudiantes al siguiente curso y elimina a los que egresan (4to Medio).
    Cursos esperados: '1ro Medio', '2do Medio', '3ro Medio', '4to Medio'.
    """
    conn = connect_db()
    cursor = conn.cursor()
    
    # Mapa de promoción
    promotion_map = {
        '1ro Medio': '2do Medio',
        '2do Medio': '3ro Medio',
        '3ro Medio': '4to Medio',
        '4to Medio': 'EGRESADO' # Marcador para eliminar
    }
    
    try:
        cursor.execute("SELECT id_alumno, rut, primer_nombre, apellido_paterno, curso FROM ALUMNOS")
        students = cursor.fetchall()
        
        promoted_count = 0
        graduated_count = 0
        
        print("INICIANDO PROMOCIÓN ANUAL DE ESTUDIANTES...")
        
        for student in students:
            id_alumno, rut, nombre, apellido, curso_actual = student
            
            if not curso_actual:
                continue # Si no tiene curso, se salta
                
            # Normalizar string (por si acaso)
            curso_actual = curso_actual.strip()
            
            if curso_actual in promotion_map:
                nuevo_curso = promotion_map[curso_actual]
                
                if nuevo_curso == 'EGRESADO':
                    # Eliminar estudiante
                    print(f"  - {nombre} {apellido} ({rut}): Egresado de 4to Medio. Eliminando registro...")
                    # Eliminar asistencias primero (FK)
                    cursor.execute("DELETE FROM ASISTENCIAS WHERE id_alumno = ?", (id_alumno,))
                    # Eliminar alumno
                    cursor.execute("DELETE FROM ALUMNOS WHERE id_alumno = ?", (id_alumno,))
                    graduated_count += 1
                else:
                    # Promover
                    print(f"  - {nombre} {apellido} ({rut}): Promovido de {curso_actual} a {nuevo_curso}.")
                    cursor.execute("UPDATE ALUMNOS SET curso = ? WHERE id_alumno = ?", (nuevo_curso, id_alumno))
                    promoted_count += 1
            else:
                print(f"  - {nombre} {apellido} ({rut}): Curso '{curso_actual}' no reconocido para promoción.")
                
        conn.commit()
        print(f"PROMOCIÓN FINALIZADA. Promovidos: {promoted_count}, Egresados/Eliminados: {graduated_count}")
        return True, promoted_count, graduated_count
        
    except Exception as e:
        print(f"Error durante la promoción de estudiantes: {e}")
        return False, 0, 0
    finally:
        conn.close()