# identify.py (FINAL: Lógica de Identificación y Obtención de Nombre)
import gi
import base64
import sys
import threading # Necesario para usar el objeto Lock

gi.require_version('FPrint', '2.0')
from gi.repository import FPrint, GLib

# Importar funciones de utilidad de la base de datos y la impresora
from db_utils import get_all_templates, save_clocking, get_alumno_full_name 
from printer_utils import print_clocking_receipt 

def identify_user_automatically(fprint_context, rut_to_verify=None, lock=None):
    """
    Captura una huella, la compara contra todas las plantillas almacenadas 
    en SQLite (o contra una sola si se proporciona rut_to_verify), 
    y si es exitosa, registra la marcación e imprime un ticket.
    
    Args:
        fprint_context: Contexto de FPrint
        rut_to_verify: (Opcional) RUT específico para verificación 1:1. 
                       Si es None, hace identificación 1:N contra todos.
        lock: (Opcional) Objeto threading.Lock para sincronización del hardware.
    """
    
    templates_data = get_all_templates()
    
    if not templates_data:
        print("No hay usuarios registrados para realizar la identificación.")
        return False

    if not fprint_context:
        print("ERROR: No se proporcionó un contexto de FPrint.")
        return None

    # Si no se proporciona un lock, creamos uno localmente (menos seguro, pero evita fallos)
    if lock is None:
        lock = threading.Lock()
        
    device = None
    
    # Bloqueo para asegurar el acceso exclusivo al dispositivo USB
    with lock:
        try:
            if rut_to_verify:
                print(f"\n=== INICIO DE VERIFICACIÓN 1:1 PARA RUT: {rut_to_verify} ===")
            else:
                print("\n=== INICIO DE IDENTIFICACIÓN AUTOMÁTICA ===")
            
            devices = fprint_context.get_devices()
            if not devices:
                print("ERROR: No se encontró ningún dispositivo de huella dactilar.")
                return None

            device = devices[0]
            device.open_sync()

            # 1. Crear una lista de objetos FPrint.Print
            fprints_to_check = []
            
            if rut_to_verify:
                # Verificación 1:1 - Solo cargar la plantilla del RUT específico
                if rut_to_verify not in templates_data:
                    print(f"No se encontró plantilla para el RUT: {rut_to_verify}")
                    device.close_sync()
                    return None
                
                template_b64 = templates_data[rut_to_verify]
                try:
                    stored_data = base64.b64decode(template_b64)
                    template_fprint = FPrint.Print.deserialize(stored_data)
                    template_fprint.set_username(rut_to_verify)
                    fprints_to_check.append(template_fprint)
                except Exception as e:
                    print(f"Error: No se pudo cargar la plantilla para {rut_to_verify}. Error: {e}")
                    device.close_sync()
                    return None
            else:
                # Identificación 1:N - Cargar todas las plantillas
                for rut, template_b64 in templates_data.items():
                    try:
                        stored_data = base64.b64decode(template_b64)
                        template_fprint = FPrint.Print.deserialize(stored_data)
                        template_fprint.set_username(rut)
                        fprints_to_check.append(template_fprint)
                    except Exception as e:
                        print(f"Advertencia: No se pudo cargar la plantilla para {rut}. Error: {e}")
            
            if rut_to_verify:
                print(f"Coloque el dedo para verificar su identidad...")
            else:
                print(f"Coloque el dedo para la identificación (comparando contra {len(fprints_to_check)} usuarios)...")

            # 2. El método identify_sync captura y compara la huella
            matched_fprint, score = device.identify_sync(fprints_to_check)
            
            device.close_sync()
            
            if matched_fprint:
                identified_rut = matched_fprint.get_username()
                print(f"\n¡IDENTIFICACIÓN EXITOSA! RUT: {identified_rut} (Puntuación: {score}).")
                
                # 3. Obtener el nombre completo para el recibo
                full_name = get_alumno_full_name(identified_rut) 
                
                # 4. Lógica de MARCACIÓN (Almacenar en la BD)
                estado, hora, num_atrasos = save_clocking(identified_rut)
                print(f"Marcación de asistencia registrada en la base de datos. Estado: {estado}, Atrasos: {num_atrasos}")
                
                # ELIMINADO: Ya no es necesario el time.sleep(1)

                # 5. Lógica de IMPRESIÓN (Pasando el nombre completo y los atrasos)
                if print_clocking_receipt(full_name, num_atrasos): 
                    print(f"Ticket de marcación impreso para {full_name}.")
                else:
                    print("No se pudo imprimir el ticket. Revisar la configuración de la impresora.")
                
                return identified_rut
            else:
                if rut_to_verify:
                    print(f"VERIFICACIÓN FALLIDA. La huella no coincide con el RUT: {rut_to_verify}")
                else:
                    print(f"IDENTIFICACIÓN FALLIDA. La huella no pertenece a ningún usuario registrado.")
                return None
            
        except Exception as e:
            print(f"Error durante la identificación: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            try:
                # Cierre de emergencia si la excepción ocurrió antes del close_sync
                if device and device.is_opened():
                    device.close_sync()
            except:
                pass
    # El lock se libera automáticamente al salir del bloque 'with lock:'

if __name__ == "__main__":
    # Nota: Si se ejecuta directamente, el lock no se pasará, pero FPrint lo maneja bien en CLI.
    # En la app GUI, siempre se pasa el lock.
    identify_user_automatically(None)