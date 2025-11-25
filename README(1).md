![Logo del Proyecto](logo.png)
# Marcador de Asistencias Inst. Politecnico Irineo Badilla Fuentes

Esta es una aplicacion/software generada por Bastián Andrade, Alejandro Ide, Claudio La Rosa, Diego Lorca y Ricardo Macaya, alumnos de la Universidad de Talca de als carreras de IDVRV y ICB. La finalidad de esta aplicación es poder concectar y hacer valer el uso de hulleros con tal de hacer ams eficiente la toma de asistencia y registro de entrada de los estudiantes.

## Características Principales

- **Registro de Asistencia**
- **Impresión de Tickets**
- **Gestión de Alumnos**
- **Cálculo de Atrasos**
- **Reportes en Excel**
- **Envío por Correo**
- **Panel de Administración**

## Guía de Instalación y Configuración

La siguiente lista esta planteada para la instalacion en un sistema operativo basado en linux (probado de la distro de Ubuntu/Debian) por medio de terminal.

### Paso 1: Prerrequisitos del Sistema

Actualiza el computador e instala los paquetes necesarios. No hace falta actualizar python que cuenta como requisito, si trabajas en sistema operativo linux, a uno mas actual, con la version 3.12 hasta la que tenga compatibilidad con las proximas depencias (Paso 3) estara bien.

```bash
sudo apt-get update
sudo apt-get install python3-pip python3-tk libfprint-2-2 gir1.2-fprint-2.0
```

### Paso 2: Clonar o Copiar el Proyecto

Descarga el archivo .zip desde el github o usa la siguiente linea de comando

```bash
git clone https://github.com/McayaICB/Huellero.git
```


### Paso 3: Instalar Dependencias de Python

Instala los paquetes de python corresopndientes por medio del archivo `requirements.txt`. Al revisarlo encontaras los paquetes que requiere para su ejecución. No es necesario instalarlos  uno por uno si usas el siguiente comando (recuerda estar en la capeta en que se encuentra, por ello esta la linea de comando que parte por cd).

```bash
cd /ruta/a/tu/proyecto/Huellero-main
pip install -r requirements.txt
```

### Paso 4: Configurar Hardware (Impresora de Tickets)

Para que la aplicación pueda usar la impresora USB sin necesidad de permisos de administrador (`sudo`), debes crear una regla `udev`.

1.  **Crea el archivo de reglas:**
    ```bash
    sudo nano /etc/udev/rules.d/99-escpos-printer.rules
    ```

2.  **Pega la siguiente línea dentro del archivo**. Estos valores son para una impresora Epson TM-T20II común. Si tienes otra, deberás verificar su `idVendor` y `idProduct` con el comando `lsusb`.
    ```
    SUBSYSTEM=="usb", ATTR{idVendor}=="04b8", ATTR{idProduct}=="0e15", MODE="0666", GROUP="dialout"
    ```

3.  **Guarda y cierra** el editor (`Ctrl+O`, `Enter`, `Ctrl+X`).

4.  **Recarga las reglas y reinicia los permisos:**
    ```bash
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    ```

5.  **Desconecta y vuelve a conectar la impresora** para que los cambios se apliquen.

### Paso 5: Configurar Variables de Entorno (Para Envío de Correos)

La aplicación envía correos usando una cuenta de Microsoft (Outlook/Office 365) configurada a través de variables de entorno para mayor seguridad.

1.  **Genera una Contraseña de Aplicación** en tu cuenta de Microsoft si tienes la autenticación de dos factores activada.

2.  **Configura las variables en la terminal**. Para que la configuración sea permanente, añádelas a tu archivo `~/.bashrc`.
    ```bash
    # Abre el archivo de configuración de tu terminal
    nano ~/.bashrc
    ```

3.  **Añade estas líneas al final del archivo**, reemplazando los valores con tus credenciales:
    ```bash
    export EMAIL_USER="tu_correo@outlook.com"
    export EMAIL_PASS="tu_contraseña_de_aplicacion_de_16_letras"
    ```

4.  **Guarda el archivo y recarga la configuración** de la terminal:
    ```bash
    source ~/.bashrc
    ```
    > **Nota:** Deberás reiniciar la terminal o abrir una nueva para que las variables estén disponibles.

### Paso 6: Configurar la Aplicación (`config.ini`)

Para facilitar la configuración de la impresora en diferentes equipos, los IDs se leen desde un archivo `config.ini`.

1.  **Crea un archivo llamado `config.ini`** en la raíz del proyecto.
2.  **Pega el siguiente contenido**. Asegúrate de que los valores coincidan con los de tu impresora (puedes verificarlos con `lsusb`).

    ```ini
    [Printer]
    vendor_id = 0x04b8
    product_id = 0x0e15
    ```

---

## Cómo Ejecutar la Aplicación

Una vez completados todos los pasos de configuración, abre una terminal, navega a la carpeta del proyecto y ejecuta:

```bash
python3 app_gui.py
```

La aplicación se iniciará en modo de pantalla completa. Puedes usar `F11` para alternar este modo y `Esc` para cerrar la aplicación.

---

## Estructura del Proyecto

- `app_gui.py`: Archivo principal que contiene la interfaz gráfica y la lógica de la aplicación.
- `db_utils.py`: Funciones para interactuar con la base de datos SQLite.
- `email.utils`: Gestiona el envio del correo.
- `enroll_test.py` / `identify.py`: Lógica para el enrolamiento e identificación con el lector de huellas.
- `printer_utils.py`: Función para imprimir los tickets de asistencia.
- `report_utils.py`: Funciones para generar el archivo Excel y enviarlo por correo.
- `requirements.txt`: Lista de dependencias de Python.
- `config.ini`: Archivo de configuración para parámetros de hardware.
