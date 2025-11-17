# identify.py (FINAL: Lógica de Identificación y Obtención de Nombre)
import gi
import base64
import sys

gi.require_version('FPrint', '2.0')
from gi.repository import FPrint, GLib

# Importar funciones de utilidad de la base de datos y la impresora
from db_utils import get_all_templates, save_clocking, get_alumno_full_name 
from printer_utils import print_clocking_receipt 

def identify_user_automatically(fprint_context):
    """
    Captura una huella, la compara contra todas las plantillas almacenadas 
    en SQLite, y si es exitosa, registra la marcación e imprime un ticket.
    """
    
    templates_data = get_all_templates()
    
    if not templates_data:
        print("❌ No hay usuarios registrados para realizar la identificación.")
        return False

    if not fprint_context:
        print("ERROR: No se proporcionó un contexto de FPrint.")
        return

    device = None
    try:
        print("\n=== INICIO DE IDENTIFICACIÓN AUTOMÁTICA ===")
        
        devices = fprint_context.get_devices()
        if not devices:
            print("ERROR: No se encontró ningún dispositivo de huella dactilar.")
            return

        device = devices[0]
        device.open_sync()

        # 1. Crear una lista de objetos FPrint.Print con todas las plantillas cargadas
        fprints_to_check = []
        for rut, template_b64 in templates_data.items():
            try:
                stored_data = base64.b64decode(template_b64)
                template_fprint = FPrint.Print.deserialize(stored_data)
                template_fprint.set_username(rut) # Usamos el RUT como clave de usuario
                fprints_to_check.append(template_fprint)
            except Exception as e:
                print(f"Advertencia: No se pudo cargar la plantilla para {rut}. Error: {e}")
                
        print(f"Coloque el dedo para la identificación (comparando contra {len(fprints_to_check)} usuarios)...")

        # 2. El método identify_sync captura y compara la huella
        matched_fprint, score = device.identify_sync(fprints_to_check)
        
        device.close_sync()
        
        if matched_fprint:
            identified_rut = matched_fprint.get_username()
            print(f"\n✅ ¡IDENTIFICACIÓN EXITOSA! RUT: {identified_rut} (Puntuación: {score}).")
            
            # 3. Obtener el nombre completo para el recibo
            full_name = get_alumno_full_name(identified_rut) 
            
            # 4. Lógica de MARCACIÓN (Almacenar en la BD)
            estado, hora, num_atrasos = save_clocking(identified_rut)
            print(f"🕒 Marcación de asistencia registrada en la base de datos. Estado: {estado}, Atrasos: {num_atrasos}")
            
            # Agregamos un pequeño retraso para asegurar que el bus USB se libere
            import time
            time.sleep(1)

            # 5. Lógica de IMPRESIÓN (Pasando el nombre completo y los atrasos)
            if print_clocking_receipt(full_name, num_atrasos): 
                print(f"🖨️ Ticket de marcación impreso para {full_name}.")
            else:
                print("⚠️ No se pudo imprimir el ticket. Revisar la configuración de la impresora.")
            
            return identified_rut
        else:
            print(f"❌ IDENTIFICACIÓN FALLIDA. La huella no pertenece a ningún usuario registrado.")
            return None
            
    except Exception as e:
        print(f"Error durante la identificación: {e}")
        return None
    finally:
        try:
            if 'device' in locals() and device.is_opened():
                device.close_sync()
        except:
            pass

if __name__ == "__main__":
    identify_user_automatically()