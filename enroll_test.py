# enroll_test.py (FUNCIÓN FINAL Y ESTABLE)
#!/usr/bin/env python3
import gi
import base64
import sys

gi.require_version('FPrint', '2.0')
from gi.repository import FPrint, GLib
from db_utils import save_template 
import threading
# Las librerías deben ser accesibles globalmente para la función
# FPrint se importa y se requiere globalmente en app_gui.py

def enroll_user(primer_nombre: str, segundo_nombre: str, apellido_paterno: str, apellido_materno: str, rut: str, hora_max_tardanza: str, max_atrasos_warning: int, curso: str, logger=None, fprint_context=None, lock=None):
    """
    Gestiona el proceso de captura de huella dactilar de forma segura.
    Si no se pasa 'device' y 'lock', la función intentará crear su propio contexto FPrint.
    """
    
    def _log(message):
        if logger:
            logger(message)
        else:
            print(message)
            
    template_name = rut 
    
    created_local_lock = False
    device = None

    # Si no dan lock, creamos uno local (seguro para llamadas desde GUI)
    if lock is None:
        lock = threading.Lock()
        created_local_lock = True

    # --- BLOQUEO CRÍTICO Y OPERACIONES DE HARDWARE ---
    with lock:
        try:
            # Si no pasan device, intentamos inicializar un contexto FPrint localmente
            if fprint_context is None:
                _log("ERROR: No se proporcionó un contexto de FPrint.")
                return False, "No se proporcionó un contexto de FPrint."

            # REFRESCAR DISPOSITIVOS: Es crucial enumerar nuevamente para detectar si el dispositivo
            # quedó en un estado extraño o si fue desconectado/reconectado.
            try:
                fprint_context.enumerate()
                devices = fprint_context.get_devices()
                if not devices:
                    _log("ERROR: No se detectó ningún dispositivo de huella.")
                    return False, "No se detectó ningún dispositivo de huella."
                device = devices[0]
            except Exception as e:
                _log(f"ERROR: No se pudo obtener el dispositivo FPrint: {e}")
                return False, f"Error al obtener dispositivo: {e}"

            _log(f"=== INICIO DE REGISTRO para RUT: {rut} ===")
            
            # 1. Abrir el dispositivo (USANDO EL OBJETO PASADO O CREADO)
            if not device.is_open():
                device.open_sync() 

            # 2. Configurar la captura
            fprint = FPrint.Print.new(device)
            fprint.set_username(template_name) 

            _log("\n*** Coloque el dedo MÚLTIPLES VECES cuando se lo indique. ***")
            
            # 3. Realizar la captura
            device.enroll_sync(fprint)
            _log("\nREGISTRO COMPLETO: Plantilla de huella dactilar creada con éxito.")
            
            data = fprint.serialize()
            
            # 4. Guardar en la DB
            if data and len(data) > 0:
                encoded_template = base64.b64encode(data).decode()
                
                save_template(
                    primer_nombre, 
                    segundo_nombre, 
                    apellido_paterno, 
                    apellido_materno, 
                    rut, 
                    encoded_template, 
                    hora_max_tardanza,
                    max_atrasos_warning,
                    curso
                )
                _log(f"Información del alumno y plantilla guardada en la base de datos.")    
            
                # 5. Cerrar el dispositivo EXPLICITAMENTE
                device.close_sync()
                return True, "Enrolamiento exitoso."
            
            else:
                _log("No se pudieron obtener datos de la huella.")
                device.close_sync()
                return False, "No se obtuvieron datos de la huella."
            
        except Exception as e:
            _log(f"Error general durante el registro: {e}")
            
            # 6. Cierre de emergencia en caso de excepción
            try:
                if device and device.is_open():
                    device.close_sync()
            except:
                pass
            return False, f"Error durante el registro: {e}"
        finally:
            # Asegurarse de que si creamos recursos locales, se limpien
            pass