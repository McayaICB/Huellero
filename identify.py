# identify.py (Actualización con Lógica de Marcación e Impresión)
import gi
import base64
import sys

gi.require_version('FPrint', '2.0')
from gi.repository import FPrint, GLib

# Importar funciones de utilidad de la base de datos y la impresora
from db_utils import get_all_templates, save_clocking 
from printer_utils import print_clocking_receipt 

def identify_user_automatically():
    """
    Captura una huella, la compara contra todas las plantillas almacenadas 
    en SQLite, y si es exitosa, registra la marcación e imprime un ticket.
    """
    
    templates_data = get_all_templates()
    
    if not templates_data:
        print("❌ No hay usuarios registrados para realizar la identificación.")
        return False

    try:
        print("\n=== INICIO DE IDENTIFICACIÓN AUTOMÁTICA ===")
        
        ctx = FPrint.Context()
        ctx.enumerate()
        
        if not ctx.get_devices():
            print("ERROR: No se encontró ningún dispositivo de huella dactilar.")
            return

        device = ctx.get_devices()[0]
        device.open_sync()

        # 1. Crear una lista de objetos FPrint.Print con todas las plantillas cargadas
        fprints_to_check = []
        for name, template_b64 in templates_data.items():
            try:
                stored_data = base64.b64decode(template_b64)
                template_fprint = FPrint.Print.deserialize(stored_data)
                template_fprint.set_username(name) # Asignamos el nombre al objeto
                fprints_to_check.append(template_fprint)
            except Exception as e:
                print(f"Advertencia: No se pudo cargar la plantilla para {name}. Error: {e}")
                
        print(f"Coloque el dedo para la identificación (comparando contra {len(fprints_to_check)} usuarios)...")

        # 2. El método identify_sync captura y compara la huella
        # Retorna el objeto FPrint (con el username) del usuario que coincide, o None.
        matched_fprint, score = device.identify_sync(fprints_to_check)
        
        device.close_sync() # Cerrar el dispositivo después de la captura/comparación
        
        if matched_fprint:
            identified_user = matched_fprint.get_username()
            print(f"\n✅ ¡IDENTIFICACIÓN EXITOSA! Bienvenido: {identified_user} (Puntuación: {score}).")
            
            # 3. Lógica de MARCACIÓN (Almacenar en la BD)
            save_clocking(identified_user)
            print("🕒 Marcación de asistencia registrada en la base de datos.")
            
            # 4. Lógica de IMPRESIÓN (Imprimir el ticket)
            if print_clocking_receipt(identified_user):
                print("🖨️ Ticket de marcación impreso.")
            else:
                print("⚠️ No se pudo imprimir el ticket. Revisar la configuración de la impresora.")
            
            return identified_user
        else:
            print(f"❌ IDENTIFICACIÓN FALLIDA. La huella no pertenece a ningún usuario registrado.")
            return None
            
    except Exception as e:
        print(f"Error durante la identificación: {e}")
        return None
    finally:
        try:
            # Asegura que el dispositivo se cierre incluso si hay un error
            if 'device' in locals() and device.is_opened():
                device.close_sync()
        except:
            pass

if __name__ == "__main__":
    # Esta parte se usa solo para pruebas directas
    identify_user_automatically()