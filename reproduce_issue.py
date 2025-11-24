import sqlite3
import pandas as pd
from datetime import datetime

# Mocking the logic from app_gui.py and db_utils.py

def test_excel_logic():
    # 1. Setup temporary DB
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    
    # Schema from db_utils.py
    cursor.execute("""
        CREATE TABLE ALUMNOS (
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
    
    cursor.execute("""
        CREATE TABLE ASISTENCIAS (
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
    
    # 2. Insert Data
    cursor.execute("INSERT INTO ALUMNOS (primer_nombre, apellido_paterno, apellido_materno, rut) VALUES ('Juan', 'Perez', 'Soto', '12345678-9')")
    user_id = cursor.lastrowid
    
    # Simulate a 'tardanza' (as db_utils.py does)
    cursor.execute("INSERT INTO ASISTENCIAS (id_alumno, fecha, hora_entrada, estado) VALUES (?, ?, ?, ?)", 
                   (user_id, '2023-10-01', '08:30:00', 'tardanza'))
    
    conn.commit()
    
    # 3. Run the logic from app_gui.py _export_to_excel
    
    # Fetch data (simulating get_clockings_for_month)
    cursor.execute("""
        SELECT 
            A.rut, 
            A.primer_nombre || ' ' || A.apellido_paterno AS Nombre_Completo,
            S.fecha,
            S.hora_entrada,
            S.estado
        FROM ASISTENCIAS S
        JOIN ALUMNOS A ON S.id_alumno = A.id_alumno
    """)
    results = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    
    df = pd.DataFrame(results, columns=columns)
    
    print("DataFrame Content:")
    print(df)
    
    # Logic from app_gui.py line 1183
    # total_atrasos=('estado', lambda x: (x.str.lower() == 'atraso').sum())
    
    asistencias_df = df.groupby('rut').agg(
        dias_asistidos=('fecha', 'count'),
        total_atrasos=('estado', lambda x: (x.str.lower() == 'atraso').sum())
    ).reset_index()
    
    print("\nAggregated Results (Current Logic):")
    print(asistencias_df)
    
    # Check if total_atrasos is 0 (Bug) or 1 (Correct)
    if asistencias_df['total_atrasos'].iloc[0] == 0:
        print("\n[FAIL] Bug Reproduced: 'tardanza' in DB is not counted because code looks for 'atraso'.")
    else:
        print("\n[PASS] Logic is correct.")

    # 4. Test Fix
    asistencias_df_fix = df.groupby('rut').agg(
        dias_asistidos=('fecha', 'count'),
        total_atrasos=('estado', lambda x: (x.str.lower().isin(['atraso', 'tardanza'])).sum())
    ).reset_index()
    
    print("\nAggregated Results (With Fix):")
    print(asistencias_df_fix)
    
    if asistencias_df_fix['total_atrasos'].iloc[0] == 1:
        print("\n[SUCCESS] Fix verified: Checking for 'tardanza' works.")

    conn.close()

if __name__ == "__main__":
    test_excel_logic()
