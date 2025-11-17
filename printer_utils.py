# printer_utils.py
from escpos.printer.usb import Usb # Usamos Usb para el modelo TM-T20II típico
from datetime import datetime
import configparser

# --- LEER CONFIGURACIÓN DE LA IMPRESORA DESDE config.ini ---
config = configparser.ConfigParser()
config.read('config.ini')

try:
    VENDOR_ID = int(config.get('Printer', 'vendor_id'), 16)
    PRODUCT_ID = int(config.get('Printer', 'product_id'), 16)
except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
    print("ADVERTENCIA: No se pudo leer 'config.ini' o los valores son incorrectos. Usando IDs por defecto.")
    VENDOR_ID = 0x04b8  # Valor por defecto para Epson
    PRODUCT_ID = 0x0e15 # Valor por defecto para TM-T20II

def print_clocking_receipt(username, num_atrasos):
    """Imprime un ticket de marcación de tiempo, incluyendo el número de atrasos."""
    now = datetime.now()
    p = None  # Inicializamos la variable de la impresora
    try:
        # Intenta inicializar la impresora USB
        p = Usb(VENDOR_ID, PRODUCT_ID)

        # Formato del Ticket
        p.set(align='center', double_width=True, double_height=True)
        p.text("REGISTRO DE ASISTENCIA\n")

        p.set(align='center', double_width=False, double_height=False)
        p.text("--------------------------------\n")

        p.set(align='left')
        p.text(f"USUARIO: {username.upper()}\n")
        p.text(f"FECHA:   {now.strftime('%d/%m/%Y')}\n")
        p.text(f"HORA:    {now.strftime('%H:%M:%S')}\n")

        # Nueva sección para el contador de atrasos
        p.text(f"ATRASOS ESTE MES: {num_atrasos}\n")
        p.text("\n")

        p.text("¡Marcación Exitosa!\n")

        p.cut()
        return True

    except Exception as e:
        # Manejo de errores si la impresora no está conectada o configurada
        print(f"ERROR DE IMPRESIÓN: No se pudo conectar a la impresora. {e}")
        return False
    finally:
        # Asegurarse de cerrar la conexión para liberar el dispositivo USB
        if p:
            p.close()