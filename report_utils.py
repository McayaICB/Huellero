# report_utils.py
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# --- CONFIGURACIÓN DE CORREO (PARA MICROSOFT/OUTLOOK) ---
# Las credenciales se leen de forma segura desde variables de entorno.
# ANTES de ejecutar la app, configura estas variables en tu terminal:
#
# En Linux/macOS:
# export EMAIL_USER="tu_correo@outlook.com"
# export EMAIL_PASS="tu_contraseña_de_aplicacion_de_16_letras"
#
# En Windows (CMD):
# set EMAIL_USER="tu_correo@outlook.com"
# set EMAIL_PASS="tucontraseñadeaplicacion"

SENDER_EMAIL = os.getenv("EMAIL_USER")
SENDER_PASSWORD = os.getenv("EMAIL_PASS")
SMTP_SERVER = "smtp.office365.com"  # Servidor SMTP para Microsoft 365/Outlook
SMTP_PORT = 587                     # Puerto para STARTTLS

def send_report_by_email(recipient_email, subject, body, attachment_path):
    """
    Envía un correo electrónico con un archivo adjunto usando una cuenta de Microsoft.
    """
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        msg = "Error: Las variables de entorno EMAIL_USER y EMAIL_PASS no están configuradas."
        print(msg)
        return False, msg

    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))

        # Adjuntar el archivo
        with open(attachment_path, "rb") as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename= {os.path.basename(attachment_path)}")
        msg.attach(part)

        # Conexión al servidor SMTP de Microsoft
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()  # Iniciar conexión segura con STARTTLS
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        return True, "Correo enviado exitosamente."
    except smtplib.SMTPAuthenticationError:
        return False, "Error de autenticación. Verifica las credenciales (EMAIL_USER/EMAIL_PASS) y que la contraseña de aplicación sea correcta."
    except Exception as e:
        return False, f"Error al enviar el correo: {e}"