# app_gui.py (VERSIÓN FINAL Y COMPLETA)
import tkinter as tk
from tkinter import messagebox
from tkinter import scrolledtext
from tkinter import filedialog
from tkinter import ttk
import threading
import time 
import sys
import os 
from datetime import datetime


try:
    import pandas as pd
    PD_AVAILABLE = True
except ImportError:
    pd = None
    PD_AVAILABLE = False
    print("WARNING: 'pandas' no está instalado.")

# Importar matplotlib
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
except ImportError:
    plt = None
    mdates = None
    FigureCanvasTkAgg = None
    print("WARNING: 'matplotlib' no está instalado.")

# Importar funciones de los otros módulos
from enroll_test import enroll_user 
from identify import identify_user_automatically
from db_utils import get_all_alumnos_details, connect_db, get_clockings_for_month, reset_monthly_delays
from validation_utils import is_valid_rut
from report_utils import send_report_by_email # <-- Usamos la nueva función
import gi

try:
    gi.require_version('FPrint', '2.0')
    from gi.repository import FPrint
except (ValueError, ImportError):
    FPrint = None
    print("WARNING: 'FPrint' no está disponible.")

# ----------------------------------------------------
# 0. CLASE BASE DE FRAME ESTABLE
# ----------------------------------------------------
class BaseFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent) 
        self.controller = controller
        
    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)
        self.after(100, self._set_initial_focus) 

    def _set_initial_focus(self):
        """Busca el primer Entry y le da foco, además de limpiarlo."""
        for widget in self.winfo_children():
            if isinstance(widget, tk.Frame) or isinstance(widget, tk.LabelFrame): 
                for sub_widget in widget.winfo_children():
                    if isinstance(sub_widget, tk.Entry):
                        sub_widget.focus_set()
                        sub_widget.delete(0, tk.END)
                        return
            elif isinstance(widget, tk.Entry):
                widget.focus_set()
                widget.delete(0, tk.END)
                return

# ----------------------------------------------------
# 1. CLASE PRINCIPAL DE LA APLICACIÓN (App)
# ----------------------------------------------------
class FingerprintApp(tk.Tk):
    PASSWORD = "Icbutalca" 

    def __init__(self):
        super().__init__()
        self.title("Sistema de Asistencia Biométrico")
        
        # --- SOLUCIÓN DE ESTABILIDAD (MAXIMIZACIÓN MANUAL) ---
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        self.geometry(f"{screen_width}x{screen_height}+0+0")

        try:
            self.attributes("-fullscreen", True)
            self._is_fullscreen = True
            # F11 alterna fullscreen
            self.bind('<F11>', self._toggle_fullscreen)
        except Exception:
            # Entornos donde -fullscreen no está soportado seguirán con la ventana maximizada
            self._is_fullscreen = False        
        self.bind('<Escape>', lambda e: self.quit_app())
        self.resizable(True, True) 
        # -----------------------------------------------------
        
        self.logo_img = None
        self.next_destination = None
        
        if FPrint:
            self.fprint_context = FPrint.Context()
            self.fprint_context.enumerate()
        else:
            self.fprint_context = None
            self.log_message("ERROR: No se pudo inicializar el contexto de FPrint.")

        # Contenedor para los Frames
        container = tk.Frame(self)
        container.pack(side="top", fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for F in (MainMenuFrame, EnrollmentFrame, PasswordCheckFrame, AdminFrame):
            frame = F(container, self)
            self.frames[F] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.log_messages_widget = self._create_log_widget()
        self._check_and_reset_delays() # Comprobar y resetear atrasos al iniciar
        self.show_frame(MainMenuFrame)

    def _check_and_reset_delays(self):
        """Verifica si es un nuevo mes y resetea los contadores de atrasos si es necesario."""
        last_reset_file = ".last_reset_month"
        current_month = str(datetime.now().month)
        
        try:
            with open(last_reset_file, 'r') as f:
                last_reset_month = f.read().strip()
        except FileNotFoundError:
            last_reset_month = ""

        if current_month != last_reset_month:
            self.log_message("Detectado nuevo mes. Reseteando contadores de atrasos...")
            if reset_monthly_delays():
                self.log_message("✅ Contadores de atrasos reseteados a 0.")
                try:
                    with open(last_reset_file, 'w') as f:
                        f.write(current_month)
                except Exception as e:
                    self.log_message(f"❌ No se pudo guardar el mes de reseteo: {e}")
            else:
                self.log_message("❌ Error al resetear los contadores de atrasos.")
        else:
            self.log_message("El contador de atrasos ya está actualizado para este mes.")

    def _toggle_fullscreen(self, event=None):
        """Alterna el estado de pantalla completa (F11)."""
        self._is_fullscreen = not getattr(self, '_is_fullscreen', False)
        try:
            self.attributes("-fullscreen", self._is_fullscreen)
        except Exception:
            # En plataformas que no soportan attributes("-fullscreen", ...) usar state('zoomed')
            if self._is_fullscreen:
                try:
                    self.state('zoomed')
                except Exception:
                    pass
            else:
                try:
                    self.state('normal')
                except Exception:
                    pass    

        # La responsividad se manejará con ScrolledFrame en cada vista.

    def _create_log_widget(self):
        """Crea y coloca el widget de log en la parte inferior."""
        log_frame = tk.Frame(self, bg="#333")
        log_frame.pack(side="bottom", fill="x")
        
        log_widget = scrolledtext.ScrolledText(log_frame, height=5, state='normal', bg="#333", fg="white", font=("Courier", 10))
        log_widget.pack(fill="x", padx=5, pady=5)
        # Insertar mensaje inicial directamente (evita llamar a self.log_message antes de asignar)
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        log_widget.insert(tk.END, f"{timestamp} Sistema iniciado. ¡Bienvenido!\n")
        log_widget.config(state='disabled')
        return log_widget

    def show_frame(self, cont):
        """Muestra el frame solicitado."""
        frame = self.frames[cont]
        frame.tkraise()

    def log_message(self, message):
        """Añade un mensaje al log."""
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        full_message = f"{timestamp} {message}\n"
        
        try:
            self.log_messages_widget.config(state='normal')
            self.log_messages_widget.insert(tk.END, full_message)
            self.log_messages_widget.see(tk.END)
            self.log_messages_widget.config(state='disabled')
        except AttributeError:
             print(f"ERROR LOG: {full_message.strip()}") # Falla si se llama antes de _create_log_widget
        
    def quit_app(self):
        self.log_message("Saliendo de la aplicación...")
        self.quit()
        sys.exit(0) 

    def show_timed_messagebox(self, title, message, duration=3000):
        """Muestra un messagebox que se cierra solo después de 'duration' ms."""
        win = tk.Toplevel()
        win.title(title)
        win.transient(self) # Hace que la ventana aparezca sobre la principal
        win.attributes("-topmost", True) # La mantiene encima

        # --- Centrar la ventana ---
        main_x = self.winfo_x()
        main_y = self.winfo_y()
        main_w = self.winfo_width()
        main_h = self.winfo_height()
        
        win_w = 280
        win_h = 100
        
        pos_x = main_x + (main_w // 2) - (win_w // 2)
        pos_y = main_y + (main_h // 2) - (win_h // 2)
        
        win.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        win.resizable(False, False)

        tk.Label(win, text=message, font=("Helvetica", 12), padx=20, pady=20).pack(expand=True)
        
        win.after(duration, win.destroy)

    def _load_logo(self, logo_path="logo.png", max_height=128):
        """Carga y redimensiona logo usando Pillow si está disponible; fallback a PhotoImage."""
        try:
            from PIL import Image, ImageTk
            if not os.path.exists(logo_path):
                return None
            img = Image.open(logo_path)
            w, h = img.size
            if h > max_height:
                scale = max_height / float(h)
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:
            try:
                if os.path.exists(logo_path):
                    return tk.PhotoImage(file=logo_path)
            except Exception:
                return None

# ----------------------------------------------------
# 2. FRAME: MENÚ PRINCIPAL (MainMenuFrame)
# ----------------------------------------------------
class MainMenuFrame(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        self.identification_lock = threading.Lock()
        
        # --- CONFIGURACIÓN DE GRID RESPONSIVO ---
        # Se crea una columna central (0) que se expande.
        self.grid_columnconfigure(0, weight=1)
        
        # Se crean filas para distribuir el contenido verticalmente, permitiendo que se expandan.
        self.grid_rowconfigure(0, weight=1) # Margen superior
        self.grid_rowconfigure(1, weight=0) # Fila para el encabezado
        self.grid_rowconfigure(2, weight=1) # Fila para los botones (se expande)
        self.grid_rowconfigure(3, weight=0) # Fila para el botón de salir
        self.grid_rowconfigure(4, weight=1) # Margen inferior

        # --- ENCABEZADO (Logo y Nombre de la Institución) ---
        # Este frame se centra en su celda del grid.
        header_frame = tk.Frame(self)
        header_frame.grid(row=1, column=0, pady=10)
        
        # Logo (Requerido)
        logo_path = "logo.png"
        logo_img = controller._load_logo(logo_path, max_height=120)
        if logo_img:
            controller.logo_img = logo_img
            tk.Label(header_frame, image=controller.logo_img).pack(side=tk.LEFT, padx=10)
        else:
            try:
                if os.path.exists(logo_path):
                    controller.logo_img = tk.PhotoImage(file=logo_path)
                    tk.Label(header_frame, image=controller.logo_img).pack(side=tk.LEFT, padx=10)
                else:
                    tk.Label(header_frame, text="[Logo no disponible]", font=("Helvetica", 12)).pack(side=tk.LEFT, padx=10)
            except Exception:
                tk.Label(header_frame, text="[Logo no disponible]", font=("Helvetica", 12)).pack(side=tk.LEFT, padx=10)
        tk.Label(header_frame, 
                 text="Liceo Politécnico Ireneo Badilla Fuentes", 
                 font=("Helvetica", 24, "bold")).pack(side=tk.LEFT, padx=10)
        
        # --- Botones ---
        # Este frame también se centra y contiene los botones principales.
        buttons_frame = tk.Frame(self, padx=100)
        buttons_frame.grid(row=2, column=0, sticky="nsew")
        buttons_frame.grid_columnconfigure(0, weight=1)
        buttons_frame.grid_rowconfigure(0, weight=1)
        buttons_frame.grid_rowconfigure(1, weight=1)

        
        # Botón 1: MARCAR ASISTENCIA (Proceso principal)
        self.attendance_button = tk.Button(buttons_frame, text="MARCAR ASISTENCIA", 
                  command=self._start_identification_thread, 
                  bg="#4CAF50", fg="white", font=("Helvetica", 28, "bold"))
        self.attendance_button.grid(row=0, column=0, sticky="nsew", pady=10, ipady=10)
        
        # Frame para botones de administración
        admin_frame = tk.LabelFrame(buttons_frame, text="Funciones Administrativas", padx=10, pady=10, font=("Helvetica", 12))
        admin_frame.grid(row=1, column=0, sticky="nsew", pady=10)
        admin_frame.grid_columnconfigure(0, weight=1)

        
        tk.Button(admin_frame, text="ENROLAR NUEVO USUARIO", 
                  command=lambda: self._go_to_password_check(EnrollmentFrame),
                  bg="#FF9800", fg="white", font=("Helvetica", 16, "bold")).pack(fill=tk.X, expand=True, pady=5, ipady=5)
        
        tk.Button(admin_frame, text="ADMINISTRAR DATOS Y EXPORTAR", 
                  command=lambda: self._go_to_password_check(AdminFrame), 
                  bg="#0066AA", fg="white", font=("Helvetica", 16, "bold")).pack(fill=tk.X, expand=True, pady=5, ipady=5)

        # Botón 4: SALIR
        tk.Button(self, text="SALIR", 
                  command=controller.quit_app, 
                  font=("Helvetica", 14), bg="#F44336", fg="white").grid(row=3, column=0, pady=10, ipady=5, padx=100, sticky="ew")
        
        # --- Métodos de Navegación ---
        
    def _go_to_password_check(self, destination):
        """Prepara el controlador y navega a la verificación de contraseña."""
        self.controller.next_destination = destination
        self.controller.show_frame(PasswordCheckFrame)

    def _start_identification_thread(self):
        """Inicia el proceso de identificación en un hilo para no congelar la GUI."""
        if not self.identification_lock.acquire(blocking=False):
            self.controller.log_message("⚠️ Identificación ya en progreso.")
            return

        self.attendance_button.config(state=tk.DISABLED, text="PROCESANDO...")
        self.controller.log_message("Iniciando escaneo de huella para IDENTIFICACIÓN...")
        thread = threading.Thread(target=self._run_identification, args=(self.controller.fprint_context,))
        thread.daemon = True
        thread.start()

    def _run_identification(self, fprint_context):
        """Ejecuta la lógica de identificación y vuelve a habilitar la GUI."""
        try:
            # identify_user_automatically retorna el RUT del alumno identificado o None
            identified_rut = identify_user_automatically(fprint_context) 
            
            if identified_rut:
                self.controller.log_message(f"✅ Identificación Exitosa para RUT: {identified_rut}. Ticket impreso.")
                self.controller.show_timed_messagebox("Éxito", "¡Bienvenido(a)! Asistencia registrada.", duration=3000)
            else:
                self.controller.log_message("❌ Identificación Fallida. Huella no reconocida o DB vacía.")
                messagebox.showerror("Error", "Huella no reconocida o error en el proceso.")
        finally:
            # Re-habilitar el botón en el hilo principal de Tkinter
            self.controller.after(100, self._enable_button)
            self.identification_lock.release()

    def _enable_button(self):
        """Vuelve a habilitar el botón de asistencia."""
        self.attendance_button.config(state=tk.NORMAL, text="MARCAR ASISTENCIA")
        self.controller.show_frame(MainMenuFrame)


# ----------------------------------------------------
# 3. VERIFICACIÓN DE CONTRASEÑA
# ----------------------------------------------------
class PasswordCheckFrame(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)

        main_frame = tk.Frame(self, padx=50, pady=50)
        main_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        tk.Label(main_frame, text="ACCESO RESTRINGIDO", font=("Helvetica", 18, "bold")).pack(pady=20)
        tk.Label(main_frame, text="Ingrese la contraseña de administrador:", font=("Helvetica", 14)).pack(pady=10)

        self.pass_entry = tk.Entry(main_frame, width=30, show="*", font=("Helvetica", 14))
        self.pass_entry.pack(pady=10)
        self.pass_entry.bind('<Return>', lambda event: self._check_password())

        tk.Button(main_frame, text="Ingresar", command=self._check_password, 
                  bg="#4CAF50", fg="white", font=("Helvetica", 14, "bold")).pack(pady=20)

        tk.Button(main_frame, text="Cancelar", command=lambda: self._cancel_and_reset(), 
                  font=("Helvetica", 14)).pack()

    def _check_password(self):
        """Verifica la contraseña y navega al destino almacenado."""
        if self.pass_entry.get() == self.controller.PASSWORD:
            self.controller.log_message("Contraseña correcta. Acceso concedido.")
            self.controller.show_frame(self.controller.next_destination) 
        else:
            self.controller.log_message("❌ Contraseña incorrecta. Acceso denegado.")
            messagebox.showerror("Error de Acceso", "Contraseña incorrecta. Intente de nuevo.")
        
        self.pass_entry.delete(0, tk.END)
        
    def _cancel_and_reset(self):
        self.pass_entry.delete(0, tk.END)
        self.controller.show_frame(MainMenuFrame)

# ----------------------------------------------------
# 4. FORMULARIO DE REGISTRO (ENROLLMENT)
# ----------------------------------------------------
class EnrollmentFrame(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)

        # Frame principal que contendrá el formulario
        main_content_frame = tk.Frame(self)
        main_content_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        tk.Label(main_content_frame, text="REGISTRO DE NUEVO ALUMNO", font=("Helvetica", 18, "bold")).pack(pady=20)
        
        form_frame = tk.LabelFrame(main_content_frame, text="Datos del Alumno", padx=15, pady=15, font=("Helvetica", 12))
        form_frame.pack(padx=20, pady=10)
        
        # 1. Primer Nombre
        self.primer_nombre_entry = self._create_entry_field(form_frame, "Primer Nombre (*):", 0)
        self.segundo_nombre_entry = self._create_entry_field(form_frame, "Segundo Nombre:", 1)
        self.apellido_paterno_entry = self._create_entry_field(form_frame, "Apellido Paterno (*):", 2)
        self.apellido_materno_entry = self._create_entry_field(form_frame, "Apellido Materno (*):", 3)
        self.rut_entry = self._create_entry_field(form_frame, "RUT (sin puntos, con guion) (*):", 4)
        
        # Campo Hora Máxima de Tardanza (Nuevo)
        tk.Label(form_frame, text="Hora Máxima de Tardanza (HH:MM) (*):", font=("Helvetica", 12)).grid(row=5, column=0, padx=10, pady=10, sticky="w")
        self.hora_max_tardanza_entry = tk.Entry(form_frame, width=30, font=("Helvetica", 12))
        self.hora_max_tardanza_entry.grid(row=5, column=1, padx=10, pady=10, sticky="e")
        self.hora_max_tardanza_entry.insert(0, "08:15") # Valor por defecto
        
        form_frame.grid_columnconfigure(1, weight=1)
        
        # Botones de Acción
        button_frame = tk.Frame(main_content_frame, pady=20)
        button_frame.pack(pady=10)
        
        tk.Button(button_frame, text="INICIAR CAPTURA DE HUELLA", 
                  command=self._start_enrollment_process, 
                  bg="#4CAF50", fg="white", font=("Helvetica", 14, "bold"), padx=20, pady=10).pack(side=tk.LEFT, padx=10)
        
        tk.Button(button_frame, text="Cancelar y Volver", 
                  command=self._cancel_and_reset, 
                  font=("Helvetica", 14), padx=20, pady=10).pack(side=tk.LEFT, padx=10)
                  
    def _create_entry_field(self, parent, label_text, row):
        """Función helper para crear campos de entrada."""
        tk.Label(parent, text=label_text, font=("Helvetica", 12)).grid(row=row, column=0, padx=10, pady=10, sticky="w")
        entry = tk.Entry(parent, width=30, font=("Helvetica", 12))
        entry.grid(row=row, column=1, padx=10, pady=10, sticky="e")
        return entry
        
    def _start_enrollment_process(self):
        # 1. Obtener y limpiar los datos
        p_n = self.primer_nombre_entry.get().strip()
        s_n = self.segundo_nombre_entry.get().strip()
        a_p = self.apellido_paterno_entry.get().strip()
        a_m = self.apellido_materno_entry.get().strip()
        rut = self.rut_entry.get().strip()
        hora_max = self.hora_max_tardanza_entry.get().strip()

        # 2. Validación de campos obligatorios
        if not p_n or not a_p or not a_m or not rut or not hora_max:
            self.controller.log_message("❌ ERROR: Los campos obligatorios (*) no pueden estar vacíos.")
            messagebox.showerror("Error", "Por favor, complete todos los campos obligatorios.")
            return
            
        # 3. Validación de formato de RUT
        if not is_valid_rut(rut):
             self.controller.log_message(f"❌ ERROR: RUT ingresado ({rut}) no es válido.")
             messagebox.showerror("Error", "El RUT ingresado no es válido. Revise el formato y dígito verificador.")
             return
             
        # 4. Validación de formato de Hora
        try:
            datetime.strptime(hora_max, '%H:%M')
            hora_max = hora_max + ":00" # Se completa a formato H:M:S para la DB
        except ValueError:
            self.controller.log_message(f"❌ ERROR: El formato de hora '{hora_max}' es inválido (debe ser HH:MM).")
            messagebox.showerror("Error de Validación", "El formato de hora máxima de tardanza debe ser HH:MM (ej: 08:15).")
            return
             
        # 5. Limpieza del RUT (quitar puntos y guiones para el ID de la huella)
        rut_clean = rut.upper().replace(".", "").replace("-", "")
        
        # 6. Vuelve al menú principal y limpia los campos
        self._cancel_and_reset() 
        self.controller.log_message(f"Iniciando captura de huella para RUT: {rut_clean}...")
        
        # La función enroll_user ahora recibe los 6 parámetros y el logger
        thread = threading.Thread(target=enroll_user, args=(
            p_n, s_n, a_p, a_m, rut_clean, hora_max
        ), kwargs={'logger': self.controller.log_message, 'fprint_context': self.controller.fprint_context})
        thread.daemon = True
        thread.start()

    def _cancel_and_reset(self):
        """Limpia los campos y vuelve al menú principal."""
        self.primer_nombre_entry.delete(0, tk.END)
        self.segundo_nombre_entry.delete(0, tk.END)
        self.apellido_paterno_entry.delete(0, tk.END)
        self.apellido_materno_entry.delete(0, tk.END)
        self.rut_entry.delete(0, tk.END)
        
        # Restablecemos el valor por defecto de la hora
        self.hora_max_tardanza_entry.delete(0, tk.END)
        self.hora_max_tardanza_entry.insert(0, "08:15")
        
        self.controller.show_frame(MainMenuFrame)

# ----------------------------------------------------
# 5. FRAME: ADMINISTRACIÓN (AdminFrame)
# ----------------------------------------------------
class AdminFrame(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)

        # Frame principal que contendrá el formulario
        main_content_frame = tk.Frame(self)
        main_content_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        tk.Label(main_content_frame, text="PANEL DE ADMINISTRACIÓN", font=("Helvetica", 16, "bold")).pack(pady=20)
        
        # --- SECCIÓN EXPORTAR EXCEL ---
        export_frame = tk.LabelFrame(main_content_frame, text="Exportar Registros de Asistencia (Excel)", padx=10, pady=10, font=("Helvetica", 12, "bold"))
        export_frame.pack(padx=50, pady=10, ipadx=10)
        
        # Frame para la selección de Mes/Año
        selection_frame = tk.Frame(export_frame)
        selection_frame.pack(pady=10)
        
        # Variables y Opciones
        now = datetime.now()
        months = [f"{i:02d}" for i in range(1, 13)]
        years = [str(now.year), str(now.year - 1), str(now.year - 2)]

        self.month_var = tk.StringVar(self); self.month_var.set(f"{now.month:02d}")
        self.year_var = tk.StringVar(self); self.year_var.set(str(now.year))
        
        # Menú desplegable de Mes
        tk.Label(selection_frame, text="Mes:", font=("Helvetica", 12)).pack(side=tk.LEFT, padx=5)
        tk.OptionMenu(selection_frame, self.month_var, *months).pack(side=tk.LEFT, padx=15)
        
        # Menú desplegable de Año
        tk.Label(selection_frame, text="Año:", font=("Helvetica", 12)).pack(side=tk.LEFT, padx=5)
        tk.OptionMenu(selection_frame, self.year_var, *years).pack(side=tk.LEFT, padx=15)
        
        # Botón de Exportar
        tk.Button(export_frame, text="GENERAR EXCEL Y EXPORTAR", 
                  command=self._export_to_excel_thread, 
                  bg="#1E88E5", fg="white", font=("Helvetica", 12, "bold"), height=2).pack(fill=tk.X, pady=5)
                  
        # --- SECCIÓN VER USUARIOS ---
        users_frame = tk.LabelFrame(main_content_frame, text="Gestión de Alumnos", padx=10, pady=10, font=("Helvetica", 12, "bold"))
        users_frame.pack(padx=50, pady=10, fill=tk.X)

        tk.Button(users_frame, text="VER LISTADO DE ALUMNOS ENROLADOS", 
                  command=self._view_enrolled_users, 
                  font=("Helvetica", 12, "bold"), height=2).pack(fill=tk.X)

        #--- NUEVA SECCIÓN: GRÁFICOS DE ASISTENCIA ---
        graph_frame = tk.LabelFrame(main_content_frame, text="Ver Marcaciones (Gráfico)", padx=10, pady=10, font=("Helvetica", 12, "bold"))
        graph_frame.pack(padx=50, pady=10, fill=tk.X)

        # Botón para la nueva funcionalidad
        tk.Button(graph_frame, text="VER TABLA DE ASISTENCIAS MENSUAL", 
                  command=self._view_clockings_graphically, 
                  bg="#6A5ACD", fg="white", font=("Helvetica", 12, "bold"), height=2).pack(fill=tk.X)
                  
        
        # --- SECCIÓN ENVIAR POR CORREO ---
        email_frame = tk.LabelFrame(main_content_frame, text="Enviar Reporte por Correo", padx=10, pady=10, font=("Helvetica", 12, "bold"))
        email_frame.pack(padx=50, pady=10, fill=tk.X)

        self.email_receiver_entry = self._create_email_entry(email_frame, "Correo Destinatario:", 0)
        
        # Botón para la nueva funcionalidad (usando grid)
        email_button = tk.Button(email_frame, text="GENERAR Y ENVIAR REPORTE POR CORREO", 
                  command=self._export_and_email_thread,
                  bg="#D32F2F", fg="white", font=("Helvetica", 12, "bold"), height=2)
        email_button.grid(row=1, column=0, columnspan=2, sticky="ew", pady=10, padx=5)

        # --- BOTÓN VOLVER ---
        tk.Button(main_content_frame, text="Volver al Menú Principal", 
                  command=lambda: controller.show_frame(MainMenuFrame), 
                  font=("Helvetica", 14)).pack(pady=20)

    def _create_email_entry(self, parent, label_text, row, show=None):
        """Función helper para crear campos de entrada de correo."""
        tk.Label(parent, text=label_text, font=("Helvetica", 12)).grid(row=row, column=0, padx=5, pady=5, sticky="w")
        entry = tk.Entry(parent, width=40, font=("Helvetica", 12), show=show)
        entry.grid(row=row, column=1, padx=5, pady=5, sticky="e")
        parent.grid_columnconfigure(1, weight=1)
        return entry
        
    def _export_and_email_thread(self):
        """Inicia la exportación y envío de correo en un hilo."""
        self.controller.log_message("Iniciando exportación y envío de correo...")
        
        # Validar que los campos de correo no estén vacíos
        if not self.email_receiver_entry.get():
            messagebox.showerror("Error", "Debe ingresar un correo de destinatario.")
            return
            
        t = threading.Thread(target=self._export_to_excel, kwargs={'send_email': True})
        t.daemon = True
        t.start()

    def _export_to_excel_thread(self):
        """Inicia la exportación en un hilo para no congelar la GUI."""
        self.controller.log_message("Iniciando exportación de datos a Excel...")
        t = threading.Thread(target=self._export_to_excel)
        t.daemon = True
        t.start()

    def _export_to_excel(self, send_email=False):
        """Lógica para obtener datos de la DB, pivotear y exportar a Excel."""
        
        # Verificar dependencias
        if pd is None or not PD_AVAILABLE:
            self.controller.log_message("❌ ERROR: La librería 'pandas' no está instalada.")
            messagebox.showerror("Error", "Se requiere 'pandas'. Ejecute:\npython3 -m pip install --user pandas openpyxl")
            return
        
        try:
            import openpyxl
        except ImportError:
            self.controller.log_message("❌ ERROR: La librería 'openpyxl' no está instalada.")
            messagebox.showerror("Error", "Se requiere 'openpyxl'. Ejecute:\npython3 -m pip install --user openpyxl")
            return
        
        month = int(self.month_var.get())
        year = int(self.year_var.get())
        
        try:
            # 1. Obtener los datos sin procesar de la DB
            columns, results = get_clockings_for_month(month, year)
            if not results:
                self.controller.log_message(f"❌ No se encontraron marcaciones para {month:02d}/{year}.")
                messagebox.showinfo("Exportación", f"No se encontraron marcaciones de asistencia para el mes {month:02d}/{year}.")
                return

            # 2. Crear un DataFrame de Pandas
            df = pd.DataFrame(results, columns=columns)
            
            # 3. Procesar y Pivotear (Lógica de Planilla de Asistencia)
            df['Día'] = pd.to_datetime(df['fecha'], errors='coerce').dt.day
            df['hora_entrada'] = df.get('hora_entrada', '').fillna('').astype(str)
            df['estado'] = df.get('estado', '').fillna('').astype(str)
            df['Nombre_Completo'] = df.get('Nombre_Completo', df.get('primer_nombre', '')).fillna('').astype(str)
            df['Valor_Marcacion'] = df['hora_entrada'].astype(str) + ' (' + df['estado'].astype(str) + ')'
            
            pivot_df = df.pivot_table(
                index=['rut', 'Nombre_Completo'],
                columns='Día',
                values='Valor_Marcacion', 
                aggfunc='first'
            ).fillna('')
            
            # 4. Definir la ruta del archivo
            default_filename = f"Registro_Asistencia_{year}_{month:02d}.xlsx"
            
            if send_email:
                # Guardar en una carpeta temporal si se va a enviar por correo
                temp_dir = "temp_reports"
                if not os.path.exists(temp_dir):
                    os.makedirs(temp_dir)
                file_path = os.path.join(temp_dir, default_filename)
            else:
                # Pedir al usuario que elija la ubicación
                file_path = filedialog.asksaveasfilename(
                    defaultextension=".xlsx",
                    initialfile=default_filename,
                    filetypes=[("Archivos de Excel", "*.xlsx")]
                )

            if file_path:
                # 5. Exportar a Excel
                pivot_df.to_excel(file_path, sheet_name='Asistencia Mensual')
                self.controller.log_message(f"✅ Exportación exitosa a: {file_path}")

                if send_email:
                    # 6. Enviar por correo
                    receiver = self.email_receiver_entry.get()
                    subject = f"Reporte de Asistencia - {month:02d}/{year}"
                    body = "Adjunto se encuentra el reporte de asistencia mensual."

                    success, message = send_report_by_email(receiver, subject, body, file_path)
                    
                    if success:
                        self.controller.log_message(f"✅ Correo enviado exitosamente a {receiver}.")
                        messagebox.showinfo("Éxito", f"El reporte ha sido enviado por correo a:\n{receiver}")
                    else:
                        self.controller.log_message(f"❌ {message}")
                        messagebox.showerror("Error de Envío", message)
                    
                    # 7. Limpiar el archivo temporal
                    try:
                        os.remove(file_path)
                        self.controller.log_message(f"Archivo temporal eliminado: {file_path}")
                    except Exception as e:
                        self.controller.log_message(f"❌ No se pudo eliminar el archivo temporal: {e}")
                else:
                    messagebox.showinfo("Éxito", f"El archivo de asistencia ha sido generado exitosamente:\n{file_path}")

        except Exception as e:
            self.controller.log_message(f"❌ Error durante la exportación a Excel: {e}")
            messagebox.showerror("Error", f"Ocurrió un error al exportar: {e}")


    def _view_enrolled_users(self):
        """Muestra una ventana temporal con el listado de todos los alumnos."""
        try:
            columns, results = get_all_alumnos_details()

            if not results:
                messagebox.showinfo("Alumnos", "No hay alumnos registrados en la base de datos.")
                return

            user_list = "ALUMNOS REGISTRADOS:\n\n"
            
            # Buscamos los índices de las columnas para mayor robustez
            col_rut = columns.index('rut') if 'rut' in columns else 4 
            col_pn = columns.index('primer_nombre') if 'primer_nombre' in columns else 0
            col_ap = columns.index('apellido_paterno') if 'apellido_paterno' in columns else 2
            col_hm = columns.index('hora_max_tardanza') if 'hora_max_tardanza' in columns else 5
            col_sn = columns.index('segundo_nombre') if 'segundo_nombre' in columns else 1 # Segundo nombre
            col_am = columns.index('apellido_materno') if 'apellido_materno' in columns else 3 # Apellido materno

            for row in results:
                rut = row[col_rut]
                pn = row[col_pn]
                sn = row[col_sn]
                ap = row[col_ap]
                am = row[col_am]
                hm = row[col_hm]

                nombre_completo = f"{pn} {sn} {ap} {am}".strip()
                user_list += f" - {nombre_completo} | RUT: {rut} | Hora Máx: {hm}\n"
            
            # Mostramos en una nueva ventana (Toplevel)
            list_window = tk.Toplevel(self.controller)
            list_window.title("Listado de Alumnos")
            
            list_text = scrolledtext.ScrolledText(list_window, width=80, height=30, font=("Courier", 11))
            list_text.insert(tk.END, user_list)
            list_text.config(state='disabled')
            list_text.pack(padx=10, pady=10)
            
            tk.Button(list_window, text="Cerrar", command=list_window.destroy).pack(pady=5)
            
        except Exception as e:
            self.controller.log_message(f"❌ Error al mostrar listado de alumnos: {e}")
            messagebox.showerror("Error", f"No se pudo cargar la lista de alumnos: {e}")
    def _view_clockings_graphically(self):
            """Muestra una tabla con las marcaciones del mes/año seleccionado, ordenada por fecha y hora."""
            month = int(self.month_var.get())
            year = int(self.year_var.get())

            try:
                columns, results = get_clockings_for_month(month, year)
                if not results:
                    self.controller.log_message(f"❌ No se encontraron marcaciones para {month:02d}/{year}.")
                    messagebox.showinfo("Marcaciones", f"No se encontraron marcaciones para {month:02d}/{year}.")
                    return

                # Identificar índices útiles en la tupla de resultados
                col_names = list(columns)
                idx_fecha = col_names.index('fecha') if 'fecha' in col_names else None
                idx_hora = col_names.index('hora_entrada') if 'hora_entrada' in col_names else None

                # Ordenar por fecha y hora (si existen índices válidos)
                def _parse_dt(row):
                    try:
                        f = row[idx_fecha] if idx_fecha is not None else ''
                        h = row[idx_hora] if idx_hora is not None else ''
                        if not f:
                            return datetime.min
                        # Normalizar hora si viene sin segundos
                        if h and len(str(h).split(':')) == 2:
                            h = str(h) + ":00"
                        return datetime.strptime(str(f) + ' ' + str(h), '%Y-%m-%d %H:%M:%S')
                    except Exception:
                        return datetime.min

                sorted_results = sorted(results, key=_parse_dt)

                # Crear ventana con tabla
                table_win = tk.Toplevel(self.controller)
                table_win.title(f"Marcaciones - {month:02d}/{year}")
                table_win.geometry("1000x600")

                # Frame para la tabla y scrollbars
                frame = tk.Frame(table_win)
                frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

                cols = col_names
                tree = ttk.Treeview(frame, columns=cols, show='headings', selectmode='browse')
                vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
                hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
                tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

                # Configurar encabezados y anchos razonables
                for c in cols:
                    heading = c.replace('_', ' ').title()
                    tree.heading(c, text=heading)
                    if c in ('fecha', 'hora_entrada', 'estado'):
                        tree.column(c, width=120, anchor='center')
                    elif c in ('rut',):
                        tree.column(c, width=120, anchor='center')
                    else:
                        tree.column(c, width=200, anchor='w')

                tree.grid(row=0, column=0, sticky='nsew')
                vsb.grid(row=0, column=1, sticky='ns')
                hsb.grid(row=1, column=0, sticky='ew')

                frame.grid_rowconfigure(0, weight=1)
                frame.grid_columnconfigure(0, weight=1)

                # Insertar filas ya ordenadas
                for row in sorted_results:
                    display_row = [str(item) if item is not None else '' for item in row]
                    tree.insert('', tk.END, values=display_row)

                # Botones de acción
                btn_frame = tk.Frame(table_win)
                btn_frame.pack(fill=tk.X, pady=6)
                ttk.Button(btn_frame, text="Cerrar", command=table_win.destroy).pack(side=tk.RIGHT, padx=8)

                # Exportar a CSV
                def _export_csv():
                    fp = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
                    if not fp:
                        return
                    try:
                        import csv
                        with open(fp, 'w', newline='', encoding='utf-8') as f:
                            writer = csv.writer(f)
                            writer.writerow(cols)
                            for r in sorted_results:
                                writer.writerow([r[i] if i < len(r) else '' for i in range(len(cols))])
                        self.controller.log_message(f"✅ Exportación CSV exitosa: {fp}")
                        messagebox.showinfo("Exportado", f"CSV generado: {fp}")
                    except Exception as e:
                        self.controller.log_message(f"❌ Error exportando CSV: {e}")
                        messagebox.showerror("Error", f"No se pudo exportar: {e}")

                ttk.Button(btn_frame, text="Exportar CSV", command=_export_csv).pack(side=tk.RIGHT, padx=8)

            except Exception as e:
                self.controller.log_message(f"❌ Error al mostrar marcaciones en tabla: {e}")
                messagebox.showerror("Error", f"Ocurrió un error al mostrar las marcaciones: {e}")
    

# ----------------------------------------------------
# 6. INICIO DE LA APLICACIÓN
# ----------------------------------------------------

if __name__ == "__main__":
    try:
        # Inicializa la base de datos (crea ALUMNOS y ASISTENCIAS)
        connect_db().close() 
        app = FingerprintApp()
        app.mainloop()
    except Exception as db_err:
        print(f"ERROR: No se pudo inicializar la aplicación de GUI. Revise los errores anteriores o la conexión a la base de datos: {db_err}")