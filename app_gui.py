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
import configparser
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

    def __init__(self):
        super().__init__()
        self.title("Sistema de Asistencia Biométrico")

        self.fprint_lock = threading.Lock() 

        self.PASSWORD = self._load_admin_password()
        
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
        for F in (MainMenuFrame, NumericPadFrame, EnrollmentFrame, PasswordCheckFrame, AdminFrame):
            frame = F(container, self)
            self.frames[F] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.log_messages_widget = self._create_log_widget()
        self._check_and_reset_delays() # Comprobar y resetear atrasos al iniciar
        self.show_frame(MainMenuFrame)
    
    def _load_admin_password(self):
        """
        Carga la contraseña del administrador desde config.ini. 
        Si no se encuentra (la clave o la sección), retorna una cadena vacía 
        y registra un mensaje de advertencia.
        """
        config = configparser.ConfigParser()
        config.read('config.ini')
        
        # Intentar obtener la contraseña. 
        # Usamos fallback='' para evitar AttributeError si la sección/clave no existe
        # y eliminamos la contraseña secreta hardcodeada del código fuente.
        password = config.get('Security', 'admin_password', fallback='').strip()
        
        if not password:
             self.log_message("Error Crítico: La contraseña de administrador no está configurada en [Security] > admin_password de config.ini. El acceso administrativo será denegado hasta que se configure.")

        return password

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
                self.log_message("Contadores de atrasos reseteados a 0.")
                try:
                    with open(last_reset_file, 'w') as f:
                        f.write(current_month)
                except Exception as e:
                    self.log_message(f"No se pudo guardar el mes de reseteo: {e}")
            else:
                self.log_message("Error al resetear los contadores de atrasos.")
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
    
    def lock_main_menu_buttons(self):
        """Bloquea los botones del menú principal."""
        main_menu = self.frames.get(MainMenuFrame)
        if main_menu:
            main_menu._lock_all_buttons()

    def unlock_main_menu_buttons(self):
        """Desbloquea los botones del menú principal."""
        main_menu = self.frames.get(MainMenuFrame)
        if main_menu:
            main_menu._unlock_all_buttons()

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
        self.grid_rowconfigure(0, weight=0) # Margen superior
        self.grid_rowconfigure(1, weight=0) # Fila para el encabezado
        self.grid_rowconfigure(2, weight=1) # Boton

         # --- BARRA SUPERIOR CON BOTÓN HAMBURGUESA ---
        top_bar = tk.Frame(self, bg="#E0E0E0", height=60)
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.grid_propagate(False)

        # Botón Hamburguesa (≡)
        self.menu_button = tk.Button(top_bar, text="☰", font=("Helvetica", 24), 
                                     bg="#333", fg="white", bd=0, padx=15, pady=5,
                                     command=self._toggle_menu)
        self.menu_button.pack(side=tk.LEFT, padx=10, pady=5)

        # --- MENÚ DESPLEGABLE (inicialmente oculto) ---
        self.menu_open = False
        self.dropdown_menu = None

        # --- ENCABEZADO (Logo y Nombre de la Institución) ---
        # Este frame se centra en su celda del grid.
        header_frame = tk.Frame(self, bg="#E0E0E0")
        header_frame.grid(row=1, column=0, pady=0, sticky="ew")

        inner = tk.Frame(header_frame, bg="#E0E0E0")
        inner.pack(expand=True)
        
        # Logo (Requerido)
        logo_path = "logo.png"
        logo_img = controller._load_logo(logo_path, max_height=120)
        if logo_img:
            controller.logo_img = logo_img
            tk.Label(inner, image=controller.logo_img, bg="#E0E0E0").pack(side=tk.LEFT, padx=10, pady=10)
        else:
            try:
                if os.path.exists(logo_path):
                    controller.logo_img = tk.PhotoImage(file=logo_path)
                    tk.Label(inner, image=controller.logo_img, bg="#E0E0E0").pack(side=tk.LEFT, padx=10, pady=10)
                else:
                    tk.Label(inner, text="[Logo no disponible]", font=("Helvetica", 12), bg="#E0E0E0", fg="#000").pack(side=tk.LEFT, padx=10, pady=10)
            except Exception:
                tk.Label(inner, text="[Logo no disponible]", font=("Helvetica", 12), bg="#E0E0E0", fg="#000").pack(side=tk.LEFT, padx=10, pady=10)

        tk.Label(
            inner,
            text="Liceo Politécnico Ireneo Badilla Fuentes",
            font=("Helvetica", 24, "bold"),
            bg="#E0E0E0",
            fg="#000"
        ).pack(side=tk.LEFT, padx=10, pady=10)
        
        # --- Botón MARCAR ASISTENCIA (Principal) ---
        buttons_frame = tk.Frame(self, padx=100, bg="#E0E0E0")
        buttons_frame.grid(row=2, column=0, sticky="nsew")
        buttons_frame.grid_columnconfigure(0, weight=1)
        buttons_frame.grid_rowconfigure(0, weight=1)
        # Label para GIF (fila 0)
        gif_label = tk.Label(buttons_frame, bg="#E0E0E0")
        gif_label.grid(row=0, column=0, pady=(20, 10))

        # Botón MARCAR ASISTENCIA
        self.attendance_button = tk.Button(buttons_frame, text="MARCAR ASISTENCIA",
                                           command=lambda: self.controller.show_frame(NumericPadFrame),
                                           bg="#4CAF50", fg="white", font=("Helvetica", 24, "bold"))
        self.attendance_button.grid(row=1, column=0, sticky="n", pady=(10, 60), ipady=60)

        self.all_buttons = [self.attendance_button, self.menu_button]

        gif_path = "fp-gif.gif"
        frames = []
        durations = []  
        try:
            from PIL import Image, ImageTk, ImageSequence
            if os.path.exists(gif_path):
                gif = Image.open(gif_path)
                bg_color = buttons_frame.cget("bg") or "#E0E0E0"
                for pil_frame in ImageSequence.Iterator(gif):
                    pil = pil_frame.convert("RGBA")
                    bg = Image.new("RGBA", pil.size, bg_color)
                    bg.paste(pil, (0, 0), pil)
                    tk_frame = ImageTk.PhotoImage(bg.convert("RGB"))
                    frames.append(tk_frame)
                    # intentar leer duración del frame; fallback a 100ms
                    dur = pil_frame.info.get('duration', gif.info.get('duration', 100))
                    durations.append(int(dur) if dur else 100)
        except Exception:
            # Fallback con PhotoImage (sin duraciones por frame)
            frames = []
            durations = []
            if os.path.exists(gif_path):
                try:
                    i = 0
                    while True:
                        try:
                            frame = tk.PhotoImage(file=gif_path, format=f"gif -index {i}")
                            frames.append(frame)
                            durations.append(100)
                            i += 1
                        except Exception:
                            break
                except Exception:
                    frames = []
                    durations = []

        if frames:
            # Mantener referencias en la instancia para evitar GC
            self._gif_frames = frames
            self._gif_durations = durations or [100] * len(frames)
            gif_label._frame_index = 0
            # Cancelar animación previa si existe
            try:
                if getattr(gif_label, "_after_id", None):
                    gif_label.after_cancel(gif_label._after_id)
            except Exception:
                pass

            def _animate():
                if not gif_label.winfo_exists():
                    return
                idx = getattr(gif_label, "_frame_index", 0)
                img = self._gif_frames[idx]
                gif_label.config(image=img)
                gif_label.image = img  # referencia actual
                # calcular siguiente y reprogramar con la duración del frame
                gif_label._frame_index = (idx + 1) % len(self._gif_frames)
                delay = self._gif_durations[idx]
                gif_label._after_id = gif_label.after(delay, _animate)

            _animate()
        else:
            gif_label.config(text="", width=1, height=1)
        
    def _toggle_menu(self):
        """Alterna la visibilidad del menú desplegable."""
        if self.menu_open:
            self._close_menu()
        else:
            self._open_menu()
    
    def _open_menu(self):
        """Abre el menú desplegable."""
        if self.dropdown_menu is not None:
            return
        
        self.menu_open = True
        
        # Crear ventana flotante para el menú
        self.dropdown_menu = tk.Toplevel(self.controller)
        self.dropdown_menu.overrideredirect(True)  # Sin decoraciones
        self.dropdown_menu.attributes("-topmost", True)
        
        # Posicionar debajo del botón hamburguesa
        x = self.menu_button.winfo_rootx()
        y = self.menu_button.winfo_rooty() + self.menu_button.winfo_height()
        self.dropdown_menu.geometry(f"+{x}+{y}")
        
        # Frame para los botones del menú
        menu_frame = tk.Frame(self.dropdown_menu, bg="#E0E0E0", relief=tk.RAISED, bd=1)
        menu_frame.pack()
        
        # Botón: Administración
        admin_btn = tk.Button(menu_frame, text="  Administrar Datos", 
                             command=lambda: self._menu_action(AdminFrame),
                             bg="#0066AA", fg="white", font=("Helvetica", 12, "bold"),
                             anchor="w", padx=20, pady=10, width=30, bd=0)
        admin_btn.pack(fill=tk.X)
        
        # Botón: Salir
        exit_btn = tk.Button(menu_frame, text=" Salir", 
                        command=lambda: self._menu_action("exit"),
                        bg="#F44336", fg="white", font=("Helvetica", 12, "bold"),
                        anchor="w", padx=20, pady=10, width=30, bd=0)
        exit_btn.pack(fill=tk.X)
        
        # Cerrar menú cuando se pierda el foco
        self.dropdown_menu.bind("<FocusOut>", lambda e: self._close_menu())
    
    def _close_menu(self):
        """Cierra el menú desplegable."""
        if self.dropdown_menu is not None:
            try:
                self.dropdown_menu.destroy()
            except Exception:
                pass
            self.dropdown_menu = None
        self.menu_open = False
    
    def _menu_action(self, action):
        """Ejecuta una acción del menú."""
        self._close_menu()
         # Para cualquier acción (frames o "exit") pedimos contraseña primero.
        # Guardamos la "destinación" en controller.next_destination.
        self.controller.next_destination = action
        # Mostramos la pantalla de verificación de contraseña
        self.controller.show_frame(PasswordCheckFrame)
        
        
    # --- Métodos de Navegación ---
    def _go_to_password_check(self, destination):
        """Prepara el controlador y navega a la verificación de contraseña."""
        self.controller.next_destination = destination
        self.controller.show_frame(PasswordCheckFrame)

    def _start_identification_thread(self):
        """Inicia el proceso de identificación en un hilo para no congelar la GUI."""
        if not self.identification_lock.acquire(blocking=False):
            self.controller.log_message("Identificación ya en progreso.")
            return

        self._lock_all_buttons()  # Bloquear todos los botones
        self.attendance_button.config(text="PROCESANDO...")
        self.controller.log_message("Iniciando escaneo de huella para IDENTIFICACIÓN...")
        thread = threading.Thread(target=self._run_identification, args=(self.controller.fprint_context,))
        thread.daemon = True
        thread.start()
    
    def _run_identification(self, fprint_context):
        """Ejecuta la lógica de identificación y vuelve a habilitar la GUI."""
        try:
            # identify_user_automatically ahora también recibe el lock
            identified_rut = identify_user_automatically(
                fprint_context, 
                lock=self.controller.fprint_lock) 
            
            if identified_rut:
                self.controller.log_message(f"Identificación Exitosa para RUT: {identified_rut}. Ticket impreso.")
                self.controller.show_timed_messagebox("Éxito", "¡Bienvenido(a)! Asistencia registrada.", duration=3000)
            else:
                self.controller.log_message("Identificación Fallida. Huella no reconocida o DB vacía.")
                messagebox.showerror("Error", "Huella no reconocida o error en el proceso.")
        finally:
            # Re-habilitar el botón en el hilo principal de Tkinter
            self.controller.after(100, self._enable_button)
            self.identification_lock.release()

    def _enable_button(self):
        """Vuelve a habilitar todos los botones."""
        self._unlock_all_buttons()  # Desbloquear todos los botones
        self.attendance_button.config(text="MARCAR ASISTENCIA")
        self.controller.show_frame(MainMenuFrame)
    
    def _lock_all_buttons(self):
        """Bloquea todos los botones."""
        for button in self.all_buttons:
            button.config(state="disabled")

    def _unlock_all_buttons(self):
        """Desbloquea todos los botones."""
        for button in self.all_buttons:
            button.config(state="normal")

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
            dest = self.controller.next_destination
            # Si la intención era salir, cerrar la aplicación.
            if dest == "exit":
                # limpiar antes de salir
                self.controller.next_destination = None
                self.controller.quit_app()
                return
            # Si dest es una clase de Frame registrada, mostrarla.
            if dest in getattr(self.controller, "frames", {}):
                self.controller.show_frame(dest)
            else:
                # Si no hay destino válido, volver al menú principal.
                self.controller.show_frame(MainMenuFrame)
            # limpiar la intención una vez ejecutada
            self.controller.next_destination = None
        else:
            self.controller.log_message("❌ Contraseña incorrecta. Acceso denegado.")
            messagebox.showerror("Error de Acceso", "Contraseña incorrecta. Intente de nuevo.")
         
        self.pass_entry.delete(0, tk.END)
        
    def _cancel_and_reset(self):
        self.pass_entry.delete(0, tk.END)
        # Limpiar próxima acción solicitada y volver al menú principal
        self.controller.next_destination = None
        self.controller.show_frame(MainMenuFrame)

# 
# 4. FORMULARIO DE REGISTRO (ENROLLMENT)
# ---------------------------------------------------
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
        
        self.enroll_button = tk.Button(button_frame, text="INICIAR CAPTURA DE HUELLA", 
                  command=self._start_enrollment_process, 
                  bg="#4CAF50", fg="white", font=("Helvetica", 14, "bold"), padx=20, pady=10)
        self.enroll_button.pack(side=tk.LEFT, padx=10)
        
        self.cancel_button = tk.Button(button_frame, text="Cancelar y Volver", 
                  command=self._cancel_and_reset, 
                  font=("Helvetica", 14), padx=20, pady=10)
        self.cancel_button.pack(side=tk.LEFT, padx=10)
        
        # Lista de botones para bloquear/desbloquear
        self.all_buttons = [self.enroll_button, self.cancel_button]
                  
    def _create_entry_field(self, parent, label_text, row):
        """Función helper para crear campos de entrada."""
        tk.Label(parent, text=label_text, font=("Helvetica", 12)).grid(row=row, column=0, padx=10, pady=10, sticky="w")
        entry = tk.Entry(parent, width=30, font=("Helvetica", 12))
        entry.grid(row=row, column=1, padx=10, pady=10, sticky="e")
        return entry
    
    def _lock_all_buttons(self):
        """Bloquea todos los botones."""
        for button in self.all_buttons:
            button.config(state="disabled")
    
    def _unlock_all_buttons(self):
        """Desbloquea todos los botones."""
        for button in self.all_buttons:
            button.config(state="normal")
        
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
        
        # 6. Almacenar datos para pasar al frame de estado
        alumno_data = (p_n, s_n, a_p, a_m, rut_clean, hora_max)

        # 7. Limpiar los campos del formulario antes de navegar
        self._clear_fields() 
        self._lock_all_buttons() # Bloquear botones de este frame
        
        # 8. CAMBIO CLAVE: Navegar al nuevo frame de estado y pasar los datos.
        # EnrollmentStatusFrame se encargará de:
        # a) Bloquear los botones principales.
        # b) Iniciar el hilo de enrolamiento.
        # c) Desbloquear y redirigir a AdminFrame al finalizar.
        self.controller.show_frame(EnrollmentStatusFrame, data=alumno_data, from_frame=EnrollmentFrame)
        self.controller.log_message(f"Navegando a pantalla de estado de captura para RUT: {rut_clean}...")
        
    def _clear_fields(self):
        """Función auxiliar para limpiar los campos del formulario."""
        self.primer_nombre_entry.delete(0, tk.END)
        self.segundo_nombre_entry.delete(0, tk.END)
        self.apellido_paterno_entry.delete(0, tk.END)
        self.apellido_materno_entry.delete(0, tk.END)
        self.rut_entry.delete(0, tk.END)
        self.hora_max_tardanza_entry.delete(0, tk.END)
        self.hora_max_tardanza_entry.insert(0, "08:15")

    def _run_enrollment(self, p_n, s_n, a_p, a_m, rut_clean, hora_max):
        """Ejecuta el enrolamiento y desbloquea los botones al finalizar."""
        try:
            enroll_user(p_n, s_n, a_p, a_m, rut_clean, hora_max, 
                    logger=self.controller.log_message, 
                    fprint_context=self.controller.fprint_context)
        finally:
            self.controller.after(100, self._finish_enrollment_and_return)

    def _finish_enrollment_and_return(self):
        """Desbloquea los botones y redirige a AdminFrame."""
        self.controller.unlock_main_menu_buttons()
        # Redirigir al AdminFrame
        self.controller.show_frame(AdminFrame)
        self.controller.log_message("Proceso de enrolamiento finalizado. Volviendo al panel de administración.")
    
    def _enable_buttons(self):
        """Vuelve a habilitar los botones."""
        self._unlock_all_buttons()
        self.enroll_button.config(text="INICIAR CAPTURA DE HUELLA")

    def _cancel_and_reset(self, skip_unlock=False):
        """Limpia los campos y vuelve al panel de administración."""
        
        # Se reemplaza la limpieza por el nuevo método auxiliar
        self._clear_fields()
        
        # Desbloquear botones de ESTE frame
        if not skip_unlock:
            self._unlock_all_buttons()
        
        # Volver a AdminFrame (navegación ya corregida en pasos anteriores)
        self.controller.show_frame(AdminFrame)
        self.controller.log_message("Cancelación de enrolamiento. Volviendo al panel de administración.")

# ---------------------------------------------------
# 5. FRAME: PAD NUMÉRICO PARA INGRESO DE RUT
# ---------------------------------------------------
class NumericPadFrame(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        
        # Frame principal centrado
        main_frame = tk.Frame(self, padx=50, pady=50)
        main_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        tk.Label(main_frame, text="INGRESE SU RUT", font=("Helvetica", 24, "bold")).pack(pady=20)
        tk.Label(main_frame, text="(sin puntos, con guión)", font=("Helvetica", 14)).pack(pady=5)
        
        # Display del RUT
        self.rut_display = tk.Entry(main_frame, width=20, font=("Helvetica", 32, "bold"), 
                                     justify='center', state='readonly')
        self.rut_display.pack(pady=20, ipady=10)
        
        # Frame para el pad numérico
        pad_frame = tk.Frame(main_frame)
        pad_frame.pack(pady=20)
        
        # Botones numéricos (3x4 grid)
        buttons = [
            ('7', 0, 0), ('8', 0, 1), ('9', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('1', 2, 0), ('2', 2, 1), ('3', 2, 2),
            ('-', 3, 0), ('0', 3, 1), ('K', 3, 2)
        ]
        
        for (text, row, col) in buttons:
            btn = tk.Button(pad_frame, text=text, width=8, height=3,
                          font=("Helvetica", 20, "bold"),
                          command=lambda t=text: self._add_digit(t),
                          bg="#E0E0E0")
            btn.grid(row=row, column=col, padx=5, pady=5)
        
        # Frame para botones de acción
        action_frame = tk.Frame(main_frame)
        action_frame.pack(pady=20)
        
        tk.Button(action_frame, text="BORRAR", width=12, height=2,
                 command=self._clear_display,
                 bg="#FF9800", fg="white", font=("Helvetica", 14, "bold")).pack(side=tk.LEFT, padx=10)
        
        tk.Button(action_frame, text="CONFIRMAR", width=12, height=2,
                 command=self._confirm_rut,
                 bg="#4CAF50", fg="white", font=("Helvetica", 14, "bold")).pack(side=tk.LEFT, padx=10)
        
        tk.Button(action_frame, text="CANCELAR", width=12, height=2,
                 command=self._cancel,
                 bg="#F44336", fg="white", font=("Helvetica", 14, "bold")).pack(side=tk.LEFT, padx=10)
        
        self.current_rut = ""
    
    def _add_digit(self, digit):
        """Agrega un dígito al display."""
        if len(self.current_rut) < 12:  # Límite razonable para RUT
            self.current_rut += digit
            self._update_display()
    
    def _clear_display(self):
        """Limpia el display."""
        self.current_rut = ""
        self._update_display()
    
    def _update_display(self):
        """Actualiza el display con el RUT actual."""
        self.rut_display.config(state='normal')
        self.rut_display.delete(0, tk.END)
        self.rut_display.insert(0, self.current_rut)
        self.rut_display.config(state='readonly')
    
    def _confirm_rut(self):
        """Confirma el RUT ingresado e inicia la verificación 1:1."""
        rut = self.current_rut.strip()
        
        if not rut:
            messagebox.showerror("Error", "Debe ingresar un RUT.")
            return
        
        # Validar formato de RUT
        if not is_valid_rut(rut):
            self.controller.log_message(f"ERROR: RUT ingresado ({rut}) no es válido.")
            messagebox.showerror("Error", "El RUT ingresado no es válido. Revise el formato y dígito verificador.")
            return
        
        # Limpiar RUT para búsqueda en DB
        rut_clean = rut.upper().replace(".", "").replace("-", "")
        
        # Verificar que el RUT existe en la base de datos
        if not self._verify_rut_exists(rut_clean):
            self.controller.log_message(f"ERROR: RUT {rut} no está registrado en el sistema.")
            messagebox.showerror("Error", "El RUT ingresado no está registrado en el sistema.")
            return
        
        # Bloquear botones del menú principal
        self.controller.lock_main_menu_buttons()
        
        # Limpiar display y volver al menú
        self._clear_display()
        self.controller.show_frame(MainMenuFrame)
        
        # Iniciar verificación 1:1
        self.controller.log_message(f"Iniciando verificación 1:1 para RUT: {rut_clean}...")
        thread = threading.Thread(target=self._run_verification, args=(rut_clean,))
        thread.daemon = True
        thread.start()
    
    def _verify_rut_exists(self, rut_clean):
        """Verifica si el RUT existe en la base de datos."""
        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM ALUMNOS WHERE rut = ?", (rut_clean,))
            count = cursor.fetchone()[0]
            conn.close()
            return count > 0
        except Exception as e:
            self.controller.log_message(f"Error al verificar RUT en DB: {e}")
            return False
    
    def _run_verification(self, rut_clean):
        """Ejecuta la verificación 1:1 de huella."""
        try:
            # Usar identify_user_automatically con el parámetro rut_to_verify
            identified_rut = identify_user_automatically(self.controller.fprint_context, rut_to_verify=rut_clean)
            
            if identified_rut:
                self.controller.log_message(f"Verificación 1:1 Exitosa para RUT: {rut_clean}. Ticket impreso.")
                self.controller.show_timed_messagebox("Éxito", "¡Bienvenido(a)! Asistencia registrada.", duration=3000)
            else:
                self.controller.log_message(f"Verificación 1:1 Fallida para RUT: {rut_clean}. Huella no coincide.")
                messagebox.showerror("Error", "La huella no coincide con el RUT ingresado.")
        except Exception as e:
            self.controller.log_message(f"Error durante verificación 1:1: {e}")
            messagebox.showerror("Error", f"Error durante la verificación: {e}")
        finally:
            # Desbloquear botones del menú principal
            self.controller.after(100, self.controller.unlock_main_menu_buttons)
    
    def _cancel(self):
        """Cancela y vuelve al menú principal."""
        self._clear_display()
        self.controller.show_frame(MainMenuFrame)

# ----------------------------------------------------
# 6. FRAME: ADMINISTRACIÓN (AdminFrame)
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
        
        # --- Formulario de Enrolamiento ---
        tk.Button(users_frame, text="ENROLLAR NUEVO ALUMNO", 
                  command=lambda: controller.show_frame(EnrollmentFrame),
                  bg="#0066AA", fg="white", font=("Helvetica", 12, "bold"), height=2).pack(fill=tk.X, pady=(0, 5))

        #--- NUEVA SECCIÓN: GRÁFICOS DE ASISTENCIA ---  
        graph_frame = tk.LabelFrame(main_content_frame, text="Ver Marcaciones", padx=10, pady=10, font=("Helvetica", 12, "bold"))
        graph_frame.pack(padx=50, pady=10, fill=tk.X)

        # Botón para la nueva funcionalidad
        tk.Button(graph_frame, text="VER TABLA DE ASISTENCIAS MENSUAL", 
                  command=self._view_clockings_graphically, 
                  bg="#6A5ACD", fg="white", font=("Helvetica", 12, "bold"), height=2).pack(fill=tk.X)
                  
        # --- SECCIÓN CONFIGURACIÓN DE CORREO REMITENTE ---
        sender_config_frame = tk.LabelFrame(main_content_frame, text="Configuración de Correo Remitente", padx=10, pady=10, font=("Helvetica", 12, "bold"))
        sender_config_frame.pack(padx=50, pady=10, fill=tk.X)
        
        self.sender_email_entry = self._create_email_entry(sender_config_frame, "Correo Remitente:", 0)
        self.sender_password_entry = self._create_email_entry(sender_config_frame, "Contraseña Remitente:", 1, show="*")
        
        # Cargar valores existentes desde config.ini
        self._load_email_config()
        
        # Botón para guardar configuración
        save_config_button = tk.Button(sender_config_frame, text="GUARDAR CONFIGURACIÓN DE CORREO", 
                  command=self._save_email_config,
                  bg="#388E3C", fg="white", font=("Helvetica", 12, "bold"), height=2)
        save_config_button.grid(row=2, column=0, columnspan=2, sticky="ew", pady=10, padx=5)
        
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
    
    def _load_email_config(self):
        """Carga la configuración de email desde config.ini y la muestra en los campos."""
        try:
            config = configparser.ConfigParser()
            config.read('config.ini')
            sender_email = config.get('Email', 'sender_email', fallback='').strip()
            sender_password = config.get('Email', 'sender_password', fallback='').strip()
            
            if sender_email:
                self.sender_email_entry.delete(0, tk.END)
                self.sender_email_entry.insert(0, sender_email)
            if sender_password:
                self.sender_password_entry.delete(0, tk.END)
                self.sender_password_entry.insert(0, sender_password)
        except Exception as e:
            self.controller.log_message(f"⚠️ No se pudo cargar la configuración de email: {e}")
    
    def _save_email_config(self):
        """Guarda la configuración de email en config.ini."""
        sender_email = self.sender_email_entry.get().strip()
        sender_password = self.sender_password_entry.get().strip()
        
        if not sender_email or not sender_password:
            messagebox.showerror("Error", "Por favor, complete ambos campos: correo remitente y contraseña.")
            return
        
        try:
            config = configparser.ConfigParser()
            config.read('config.ini')
            
            # Asegurar que la sección Email existe
            if not config.has_section('Email'):
                config.add_section('Email')
            
            config.set('Email', 'sender_email', sender_email)
            config.set('Email', 'sender_password', sender_password)
            
            # Guardar el archivo
            with open('config.ini', 'w') as configfile:
                config.write(configfile)
            
            self.controller.log_message("✅ Configuración de correo remitente guardada exitosamente.")
            messagebox.showinfo("Éxito", "La configuración de correo remitente ha sido guardada correctamente.")
            
        except Exception as e:
            error_msg = f"Error al guardar la configuración de email: {e}"
            self.controller.log_message(f"❌ {error_msg}")
            messagebox.showerror("Error", error_msg)
        
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
        """
        Obtiene los datos de asistencia, los pivotea por día y exporta el resultado
        a un archivo Excel. Si se especifica, también lo envía por correo.
        El valor de la tabla dinámica es la HORA DE ENTRADA.
        """
        if not PD_AVAILABLE:
            self.controller.log_message("❌ Error: Pandas no está instalado. No se puede generar el Excel.")
            messagebox.showerror("Error", "La librería 'pandas' no está instalada. No se puede generar el Excel.")
            return

        month = int(self.month_var.get())
        year = int(self.year_var.get())
        
        try:
            # 1. Obtener los datos sin procesar de la DB
            # Esto retorna: rut, Nombre_Completo, fecha, hora_entrada, estado
            columns, results = get_clockings_for_month(month, year)
            
            if not results:
                messagebox.showinfo("Reporte Vacío", f"No hay marcaciones para {month}/{year}.")
                return

            # 2. Crear un DataFrame de Pandas
            df = pd.DataFrame(results, columns=columns)
            
            # 3. Procesar y Pivotear (Crear la planilla de asistencia)
            
            # Extraer el número de día
            df['Día'] = pd.to_datetime(df['fecha'], errors='coerce').dt.day
            
            # Asegurar que la hora de entrada es una cadena limpia (o vacía si es NaN)
            # ESTE ES EL CAMBIO CLAVE: Se usa la hora_entrada como Valor_Marcacion
            df['Valor_Marcacion'] = df.get('hora_entrada', '').fillna('').astype(str)
            
            # Nombre completo para el índice
            df['Nombre_Completo'] = df.get('Nombre_Completo', df.get('primer_nombre', '')).fillna('').astype(str)
            
            # El pivote usa la hora de entrada como valor para la tabla
            pivot_df = df.pivot_table(
                index=['rut', 'Nombre_Completo'],
                columns='Día',
                values='Valor_Marcacion', 
                aggfunc='first'
            ).fillna('')

            # 4. Exportar a Excel
            filename = f"Reporte_Asistencia_{year}_{month:02d}.xlsx"
            filepath = os.path.join(os.getcwd(), filename) # Guardar en el directorio actual
            
            # Guardar el DataFrame pivoteado
            pivot_df.to_excel(filepath)
            
            self.controller.log_message(f"✅ Reporte Excel generado: {filepath}")
            
            if send_email:
                # 5. Enviar por correo si se solicita
                success, msg = send_report_by_email(
                    recipient_email=self.email_target_var.get(),
                    subject=f"Reporte de Asistencia {month}/{year}",
                    body=f"Adjunto encontrarás el reporte consolidado de asistencia para el mes de {month}/{year}.",
                    attachment_path=filepath
                )
                if success:
                    messagebox.showinfo("Correo Enviado", f"Reporte enviado exitosamente a {self.email_target_var.get()}")
                else:
                    messagebox.showerror("Error de Correo", f"Fallo al enviar el correo: {msg}")
            else:
                messagebox.showinfo("Exportado", f"Excel generado: {filepath}")

        except Exception as e:
            self.controller.log_message(f"Error durante la exportación a Excel: {e}")
            messagebox.showerror("Error", f"Ocurrió un error inesperado al generar el Excel: {e}")


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
            self.controller.log_message(f"Error al mostrar listado de alumnos: {e}")
            messagebox.showerror("Error", f"No se pudo cargar la lista de alumnos: {e}")

    def _view_clockings_graphically(self):
        """Muestra una tabla con las marcaciones del mes/año seleccionado, ordenada por fecha y hora."""
        month = int(self.month_var.get())
        year = int(self.year_var.get())

        try:
            columns, results = get_clockings_for_month(month, year)
            if not results:
                self.controller.log_message(f"No se encontraron marcaciones para {month:02d}/{year}.")
                messagebox.showinfo("Marcaciones", f"No se encontraron marcaciones para {month:02d}/{year}.")
                return

            # Identificar índices útiles en la tupla de resultados
            col_names = list(columns)
            idx_fecha = col_names.index('fecha') if 'fecha' in col_names else None
            idx_hora = col_names.index('hora_entrada') if 'hora_entrada' in col_names else None
            idx_estado = col_names.index('estado') if 'estado' in col_names else None

            # Agregar columna de atrasos después de estado
            if idx_estado is not None:
                col_names.insert(idx_estado + 1, 'es_atraso')
            else:
                col_names.append('es_atraso')

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

            # Agregar indicador de atraso a cada fila
            total_atrasos = 0
            enhanced_results = []
            for row in sorted_results:
                row_list = list(row)
                es_atraso = ''
                if idx_estado is not None and row[idx_estado] and 'atraso' in str(row[idx_estado]).lower():
                    es_atraso = '✓'
                    total_atrasos += 1
                
                if idx_estado is not None:
                    row_list.insert(idx_estado + 1, es_atraso)
                else:
                    row_list.append(es_atraso)
                
                enhanced_results.append(row_list)

            # Crear ventana con tabla
            table_win = tk.Toplevel(self.controller)
            table_win.title(f"Marcaciones - {month:02d}/{year} - Total Atrasos: {total_atrasos}")
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
                if c == 'es_atraso':
                    heading = 'Atraso'
                    tree.heading(c, text=heading)
                    tree.column(c, width=80, anchor='center')
                else:
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
            for row in enhanced_results:
                display_row = [str(item) if item is not None else '' for item in row]
                item_id = tree.insert('', tk.END, values=display_row)
                
                # Resaltar atrasos en rojo
                idx_atraso_col = col_names.index('es_atraso')
                if row[idx_atraso_col] == '✓':
                    tree.item(item_id, tags=('atraso',))
            
            # Configurar estilo para atrasos
            tree.tag_configure('atraso', background='#ffcccc')

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
                        for r in enhanced_results:
                            writer.writerow([r[i] if i < len(r) else '' for i in range(len(cols))])
                        # Agregar estadísticas al final
                        writer.writerow([])
                        writer.writerow(['TOTAL ATRASOS', total_atrasos])
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
# 7. FRAME: ESTADO DE ENROLAMIENTO (EnrollmentStatusFrame)
# ----------------------------------------------------    
class EnrollmentStatusFrame(BaseFrame):
    """Muestra el estado del enrolamiento de huella dactilar mientras el proceso se ejecuta en un hilo."""
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        
        # Atributos para almacenar los datos del alumno y el lock
        self.alumno_data = None
        
        tk.Label(self, text="PROCESO DE CAPTURA DE HUELLA EN CURSO", font=("Helvetica", 20, "bold"), fg="#0066AA").pack(pady=(50, 20))
        
        # Placeholder para el mensaje de estado principal
        self.status_label = tk.Label(self, text="Por favor, espere mientras se inicializa el dispositivo...", font=("Helvetica", 14), fg="black")
        self.status_label.pack(pady=10)
        
        # Botón para volver (inicialmente deshabilitado)
        self.back_button = tk.Button(self, text="Cancelar y Volver", command=self._cancel_process, 
                                     bg="#F44336", fg="white", font=("Helvetica", 12, "bold"), state=tk.DISABLED)
        self.back_button.pack(pady=50, ipadx=20, ipady=10)
        
    def show_frame(self, data, from_frame):
        """Prepara e inicia el proceso al mostrar la ventana."""
        super().show_frame()
        self.alumno_data = data
        self.status_label.config(text="Coloque el dedo en el lector cuando se le solicite.")
        self.back_button.config(state=tk.DISABLED)
        
        # 1. Bloquear los botones principales
        self.controller.lock_main_menu_buttons()
        
        # 2. Iniciar el hilo de enrolamiento
        threading.Thread(target=self._run_enrollment_thread, daemon=True).start()

    def _update_log_message(self, message):
        """Método de log que se pasa al enroll_user para actualizar la GUI."""
        # Se usa after para asegurar que la actualización del log se hace en el hilo principal de Tkinter
        self.controller.after(0, lambda: self.controller.log_message(message))
        self.controller.after(0, lambda: self.status_label.config(text=message.replace('\n', ' ')))

    def _run_enrollment_thread(self):
        """Ejecuta la función de enrolamiento en el hilo secundario."""
        try:
            # Desempaquetar los datos del alumno
            p_n, s_n, a_p, a_m, rut_clean, hora_max = self.alumno_data
            
            # Llamar a la función de enrolamiento con el lock y el logger
            enroll_user(
                p_n, s_n, a_p, a_m, rut_clean, hora_max, 
                logger=self._update_log_message, # Usar el logger de este frame
                fprint_context=self.controller.fprint_context,
                lock=self.controller.fprint_lock # Pasar el lock
            )
            
            # Si tiene éxito, el hilo llama a la finalización
            self.controller.after(100, lambda: self._finish_process("✅ Enrolamiento completado."))

        except Exception as e:
            # Si hay una excepción, notificar y finalizar
            self.controller.after(100, lambda: self._finish_process(f"❌ Error durante el enrolamiento: {e}"))
            
    def _finish_process(self, final_message):
        """Finaliza el proceso y redirige a AdminFrame."""
        self._update_log_message(final_message)
        
        # Desbloquear botones
        self.controller.unlock_main_menu_buttons()
        
        # Esperar un momento para que el usuario lea el mensaje y luego redirigir
        self.controller.after(3000, lambda: self.controller.show_frame(AdminFrame))
        self.controller.log_message(f"Proceso finalizado. Volviendo a Administración.")

    def _cancel_process(self):
        """Cancelación no disponible, ya que el proceso de FPrint es sincrónico."""
        self._update_log_message("El enrolamiento está en curso. Por favor, espere a que termine o reinicie la aplicación.")
        self.controller.after(3000, lambda: self.back_button.config(state=tk.DISABLED))   

# ----------------------------------------------------
# 8. INICIO DE LA APLICACIÓN
# ----------------------------------------------------

if __name__ == "__main__":
    try:
        # Inicializa la base de datos (crea ALUMNOS y ASISTENCIAS)
        connect_db().close() 
        app = FingerprintApp()
        app.mainloop()
    except Exception as db_err:
        print(f"ERROR: No se pudo inicializar la aplicación de GUI. Revise los errores anteriores o la conexión a la base de datos: {db_err}")
