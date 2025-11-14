# printer_utils.py
from escpos.printer import Usb # Usamos Usb para el modelo TM-T20II típico
from datetime import datetime

# Configuración USB de la Epson TM-T20II (ESTOS VALORES SON EJEMPLOS COMUNES)
# NECESITAS CONFIRMAR EL VID y PID DE TU IMPRESORA (lsusb en Linux)
VENDOR_ID = 0x04b8  # ID de EPSON (puede variar)
PRODUCT_ID = 0x0202 # ID de TM-T20II (puede variar)

def print_clocking_receipt(username):
    """Imprime un ticket de marcación de tiempo."""
    now = datetime.now()
    try:
        # Intenta inicializar la impresora USB
        p = Usb(VENDOR_ID, PRODUCT_ID, profile="epson")
        
        # Formato del Ticket
        p.set(align='center', double_width=True, double_height=True)
        p.text("REGISTRO DE ASISTENCIA\n")
        
        p.set(align='center', double_width=False, double_height=False)
        p.text("--------------------------------\n")
        
        p.set(align='left')
        p.text(f"USUARIO: {username.upper()}\n")
        p.text(f"FECHA:   {now.strftime('%d/%m/%Y')}\n")
        p.text(f"HORA:    {now.strftime('%H:%M:%S')}\n")
        p.text("\n")
        p.text("¡Marcación Exitosa!\n")
        
        p.cut()
        return True
        
    except Exception as e:
        # Manejo de errores si la impresora no está conectada o configurada
        print(f"ERROR DE IMPRESIÓN: No se pudo conectar a la impresora. {e}")
        return False