# report_utils.py
import smtplib
import os
import configparser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# --- CONFIGURACIÓN DE CORREO (PARA MICROSOFT/OUTLOOK) ---
# Las credenciales se leen desde el archivo config.ini en la sección [Email]

SMTP_SERVER = "smtp.office365.com"  # Servidor SMTP para Microsoft 365/Outlook
SMTP_PORT = 587                     # Puerto para STARTTLS

def _get_email_config():
    """
    Lee la configuración de email desde config.ini.
    Retorna (sender_email, sender_password) o (None, None) si no están configurados.
    """
    config = configparser.ConfigParser()
    try:
        config.read('config.ini')
        sender_email = config.get('Email', 'sender_email', fallback='').strip()
        sender_password = config.get('Email', 'sender_password', fallback='').strip()
        
        if sender_email and sender_password:
            return sender_email, sender_password
        else:
            return None, None
    except Exception as e:
        print(f"Error al leer configuración de email: {e}")
        return None, None

def send_report_by_email(recipient_email, subject, body, attachment_path):
    """
    Envía un correo electrónico con un archivo adjunto usando una cuenta de Microsoft.
    Las credenciales se leen desde config.ini.
    """
    SENDER_EMAIL, SENDER_PASSWORD = _get_email_config()
    
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        msg = "Error: Las credenciales de email no están configuradas en config.ini. Por favor, configure el correo remitente y contraseña en el panel de administración."
        print(msg)
        return False, msg
    
    # Establecer variables de entorno para compatibilidad (si es necesario)
    os.environ["EMAIL_USER"] = SENDER_EMAIL
    os.environ["EMAIL_PASS"] = SENDER_PASSWORD

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
