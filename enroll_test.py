# enroll_test.py
#!/usr/bin/env python3
import gi
import base64
import sys

gi.require_version('FPrint', '2.0')
from gi.repository import FPrint, GLib
# Importa la función de guardado en SQLite
from db_utils import save_template 

def enroll_user(nombre: str, apellido: str, rut: str, matricula: str):
    """
    Guarda la plantilla (template) de la huella dactilar para un usuario 
    junto con sus datos personales, utilizando el RUT como identificador único.
    """
    try:
        print(f"=== INICIO DE REGISTRO para: {nombre} {apellido} (RUT: {rut}) ===")
        
        ctx = FPrint.Context()
        ctx.enumerate()
        
        # Verifica si hay dispositivos disponibles
        if not ctx.get_devices():
            print("ERROR: No se encontró ningún dispositivo de huella dactilar.")
            return

        device = ctx.get_devices()[0]
        print(f"Dispositivo: {device.get_name()}")
        device.open_sync()

        # Crear print object, usando el RUT como identificador para libfprint
        fprint = FPrint.Print.new(device)
        fprint.set_username(rut)

        print("\n*** POR FAVOR, COLOQUE EL DEDO MÚLTIPLES VECES CUANDO SE LO INDIQUE ***")
        
        # El método enroll_sync maneja las múltiples capturas
        try:
            device.enroll_sync(fprint)
            print("\nREGISTRO COMPLETO: Plantilla de huella dactilar creada con éxito.")
        except GLib.Error as e:
            print(f"Error durante el registro: {e}")
            return

        # Serializar los datos obtenidos (Template FMD)
        data = fprint.serialize()

        if data and len(data) > 0:
            encoded = base64.b64encode(data).decode()
            
            # ALMACENAMIENTO PERMANENTE en SQLite con todos los datos
            save_template(nombre, apellido, rut, matricula, encoded)
            print(f"✅ Datos y plantilla Base64 almacenados en SQLite para {nombre} {apellido}.")
            
        else:
            print("No se pudieron obtener datos de la huella.")
        
        device.close_sync()

    except Exception as e:
        print(f"Error general: {e}")
    finally:
        try:
            device.close_sync()
        except:
            pass

if __name__ == "__main__":
    # Esta parte se usa solo para pruebas directas, pero el flujo principal usa main.py
    print("Ejecutando prueba de registro directo (sin el menú principal)...")
    # Simula datos para la prueba
    enroll_user("NombrePrueba", "ApellidoPrueba", "12345678-9", "MAT-001")
