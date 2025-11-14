# enroll_test.py
#!/usr/bin/env python3
import gi
import base64
import sys

gi.require_version('FPrint', '2.0')
from gi.repository import FPrint, GLib
# Importa la función de guardado en SQLite
from db_utils import save_template 

def enroll_user(username: str):
    """
    Guarda la plantilla (template) de la huella dactilar para un usuario 
    utilizando el proceso de enrollment de libfprint (múltiples pasadas).
    """
    try:
        print(f"=== INICIO DE REGISTRO para: {username} ===")
        
        ctx = FPrint.Context()
        ctx.enumerate()
        
        # Verifica si hay dispositivos disponibles
        if not ctx.get_devices():
            print("ERROR: No se encontró ningún dispositivo de huella dactilar.")
            return

        device = ctx.get_devices()[0]
        print(f"Dispositivo: {device.get_name()}")
        device.open_sync()

        # Crear print object
        fprint = FPrint.Print.new(device)
        fprint.set_username(username)

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
            
            # ALMACENAMIENTO PERMANENTE en SQLite
            save_template(username, encoded)
            print(f"✅ Plantilla Base64 almacenada en SQLite para {username}.")
            
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
    enroll_user("test_user_solo")
