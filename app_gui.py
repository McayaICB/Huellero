# app_gui.py
import tkinter as tk
from tkinter import messagebox
from tkinter import scrolledtext
import threading
import time 
import sys
import os # Necesario para verificar la existencia del logo

# Importar funciones de los otros módulos
from enroll_test import enroll_user
from identify import identify_user_automatically
from db_utils import get_registered_users, connect_db 


class EnrollmentDialog(tk.Toplevel):
    """Diálogo para ingresar los datos del usuario y realizar el registro."""
    
    def __init__(self, master, log_message_callback):
        super().__init__(master)
        self.title("Nuevo Registro de Huella")
        self.log_message = log_message_callback
        self.resizable(False, False)
        
        self.create_widgets()
        
    def create_widgets(self):
        tk.Label(self, text="Paso 2: Ingrese los Datos del Usuario a Registrar", font=("Helvetica", 10, "bold")).pack(pady=10, padx=20)
        
        # Crear un frame para los campos de entrada
        form_frame = tk.Frame(self)
        form_frame.pack(pady=5, padx=20)

        # Campos del formulario
        labels = ["Nombre:", "Apellido:", "RUT (con guion):", "Matrícula (Opcional):"]
        self.entries = {}

        for i, label_text in enumerate(labels):
            tk.Label(form_frame, text=label_text).grid(row=i, column=0, sticky="w", pady=2)
            entry = tk.Entry(form_frame, width=40)
            entry.grid(row=i, column=1, pady=2)
            self.entries[label_text] = entry
        
        # Botón para iniciar el registro
        tk.Button(self, text="Iniciar Registro de Huella", 
                  command=self.start_enrollment_process, 
                  bg="orange", fg="white").pack(pady=10)

    def start_enrollment_process(self):
        nombre = self.entries["Nombre:"].get().strip()
        apellido = self.entries["Apellido:"].get().strip()
        rut = self.entries["RUT (con guion):"].get().strip()
        matricula = self.entries["Matrícula (Opcional):"].get().strip()

        if not nombre or not apellido or not rut:
            messagebox.showerror("Error", "Nombre, Apellido y RUT son campos obligatorios.")
            return

        # Cerramos el diálogo antes de iniciar el proceso largo de captura
        self.destroy() 
        
        # Iniciamos el proceso de registro en un hilo
        self.log_message(f"Iniciando registro para {nombre} {apellido} (RUT: {rut})...")
        thread = threading.Thread(target=enroll_user, args=(nombre, apellido, rut, matricula))
        thread.start()


class FingerprintApp(tk.Tk):
    # Contraseña para el modo Enrolar
    PASSWORD = "Icbutalca" 

    def __init__(self):
        super().__init__()
        self.title("Sistema de Asistencia - Liceo Politécnico Ireneo Badilla Fuentes")
        self.geometry("800x600")
        # Permitir que la ventana sea redimensionable
        self.resizable(True, True)
        self.logo_img = None 
        
        self.create_widgets()

    def create_widgets(self):
        # Configurar el grid de la ventana principal para que el frame principal se expanda
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Frame principal para contener todo
        main_frame = tk.Frame(self, padx=10, pady=10)
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # Configurar el grid del main_frame para que se expanda
        main_frame.grid_rowconfigure(2, weight=1) # El área de log se expandirá
        main_frame.grid_columnconfigure(0, weight=1)

        # ----------------------------------
        # ENCABEZADO (Logo y Nombre)
        # ----------------------------------
        header_frame = tk.Frame(main_frame, bd=2, relief=tk.GROOVE)
        header_frame.grid(row=0, column=0, sticky="ew", pady=10)
        header_frame.columnconfigure(1, weight=1) # Para que el texto se centre

        # Cargar Logo
        logo_path = "logo.png"
        if os.path.exists(logo_path):
            try:
                self.logo_img = tk.PhotoImage(file=logo_path)
                logo_label = tk.Label(header_frame, image=self.logo_img)
                logo_label.grid(row=0, column=0, padx=10, pady=5)
            except Exception as e:
                self.log_message(f"⚠️ Error al cargar el logo: {e}", is_error=True)

        tk.Label(header_frame, 
                 text="Liceo Politécnico Ireneo Badilla Fuentes", 
                 font=("Helvetica", 14, "bold")).grid(row=0, column=1, padx=10, pady=10)

        # ----------------------------------
        # Consola/Log de Mensajes
        # ----------------------------------
        log_label = tk.Label(main_frame, text="Log de Eventos:", anchor="w", font=("Helvetica", 10, "bold"))
        log_label.grid(row=1, column=0, sticky="w", pady=(10, 0))
        
        self.log_area = scrolledtext.ScrolledText(main_frame, height=12, state=tk.DISABLED, wrap=tk.WORD)
        self.log_area.grid(row=2, column=0, sticky="nsew", pady=5)
        
        # Redirigir la salida estándar (print) a la caja de texto
        sys.stdout.write = lambda text: self.log_message(text)
        sys.stderr.write = lambda text: self.log_message(text, is_error=True)
        
        # ----------------------------------
        # MENÚ PRINCIPAL
        # ----------------------------------
        menu_frame = tk.LabelFrame(main_frame, text="Opciones Principales", padx=10, pady=10)
        menu_frame.grid(row=3, column=0, sticky="ew", pady=10)
        menu_frame.columnconfigure(0, weight=1) # Para que los botones se expandan
        
        scan_btn = tk.Button(menu_frame, text="1. MARCAR ASISTENCIA", 
                             command=self.start_identification_thread, 
                             bg="#4CAF50", fg="white", font=("Helvetica", 16, "bold"))
        scan_btn.grid(row=0, column=0, sticky="ew", pady=5)

        enroll_btn = tk.Button(menu_frame, text="2. ENROLAR NUEVO USUARIO (ADMIN)", 
                               command=self.open_password_check, 
                               bg="#FF9800", fg="white", font=("Helvetica", 16, "bold"))
        enroll_btn.grid(row=1, column=0, sticky="ew", pady=5)

        # ----------------------------------
        # Botones de Utilidad
        # ----------------------------------
        util_frame = tk.Frame(main_frame)
        util_frame.grid(row=4, column=0, sticky="ew", pady=10)
        util_frame.columnconfigure(0, weight=1) # Para que el botón de la izquierda se expanda un poco
        util_frame.columnconfigure(1, weight=1) # Para que el botón de la derecha se expanda un poco

        tk.Button(util_frame, text="Mostrar Usuarios Registrados", command=self.show_registered_users).grid(row=0, column=0, sticky="w", padx=5)
        tk.Button(util_frame, text="Salir", command=self.quit_app, bg="red", fg="white").grid(row=0, column=1, sticky="e", padx=5)

    def log_message(self, message, is_error=False):
        """Muestra un mensaje en el área de log."""
        self.log_area.config(state=tk.NORMAL)
        
        # Elimina espacios en blanco innecesarios y añade la hora
        message = message.strip()
        if not message:
             return
             
        timestamp = time.strftime("[%H:%M:%S]")
        formatted_message = f"{timestamp} {message}\n"
        
        self.log_area.insert(tk.END, formatted_message)
        self.log_area.see(tk.END) # Scroll automático
        self.log_area.config(state=tk.DISABLED)
        
    # --- PROCESOS EN HILOS ---
    
    def start_identification_thread(self):
        self.log_message("Iniciando identificación automática...")
        thread = threading.Thread(target=identify_user_automatically)
        thread.start()

    def open_password_check(self):
        """Abre el diálogo para verificar la contraseña."""
        
        # Paso 1: Pedir Contraseña
        dialog = tk.Toplevel(self)
        dialog.title("Acceso de Administración")
        dialog.resizable(False, False)
        
        tk.Label(dialog, text="Paso 1: Ingrese la Contraseña", font=("Helvetica", 10, "bold")).pack(pady=10, padx=20)
        
        pass_entry = tk.Entry(dialog, show="*", width=30)
        pass_entry.pack(pady=5, padx=20)
        pass_entry.focus_set()

        def check_password():
            if pass_entry.get() == self.PASSWORD:
                dialog.destroy()
                # Si la contraseña es correcta, abrir el diálogo de registro
                EnrollmentDialog(self, self.log_message)
            else:
                messagebox.showerror("Acceso Denegado", "Contraseña incorrecta.")
                pass_entry.delete(0, tk.END) # Limpiar campo

        tk.Button(dialog, text="Verificar", command=check_password, bg="#008CBA", fg="white").pack(pady=10)
        dialog.bind('<Return>', lambda event=None: check_password())
        self.wait_window(dialog) # Espera a que se cierre el diálogo de contraseña

    # --- UTILIDADES ---

    def show_registered_users(self):
        users = get_registered_users()
        if users:
            user_list = "\n".join(users)
            messagebox.showinfo("Usuarios Registrados", f"Total de usuarios: {len(users)}\n\n{user_list}")
        else:
            messagebox.showinfo("Usuarios Registrados", "No hay usuarios registrados en la base de datos.")
            
    def quit_app(self):
        self.quit()
        self.destroy()


if __name__ == "__main__":
    # Inicializa la base de datos para asegurar que las tablas existan
    # Esto creará el archivo fingerprints.db si no existe.
    try:
        connect_db().close() 
    except Exception as db_err:
        print(f"ERROR: No se pudo inicializar la base de datos SQLite. {db_err}")
        sys.exit(1)
        
    app = FingerprintApp()
    app.mainloop()