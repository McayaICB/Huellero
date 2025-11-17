# validation_utils.py

import re

def is_valid_rut(rut_full: str) -> bool:
    """
    Valida el formato y el dígito verificador del RUT chileno.
    Acepta formatos con o sin puntos/guiones (ej: 12.345.678-K o 12345678K).
    """
    # 1. Limpiar y estandarizar el RUT
    rut = rut_full.upper().replace(".", "").replace("-", "")
    
    if len(rut) < 2:
        return False
        
    dv = rut[-1] # Dígito verificador (último carácter)
    body = rut[:-1] # Cuerpo del RUT (números)
    
    if not body.isdigit():
        return False
        
    # 2. Cálculo del Dígito Verificador (Módulo 11)
    reversed_body = body[::-1]
    
    suma = 0
    multiplicador = 2
    
    for char in reversed_body:
        suma += int(char) * multiplicador
        multiplicador += 1
        if multiplicador == 8:
            multiplicador = 2
            
    resto = suma % 11
    calculated_dv_int = 11 - resto
    
    # 3. Mapeo a carácter
    if calculated_dv_int == 11:
        calculated_dv = '0'
    elif calculated_dv_int == 10:
        calculated_dv = 'K'
    else:
        calculated_dv = str(calculated_dv_int)
        
    # 4. Comparación
    return calculated_dv == dv