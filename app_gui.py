
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
from db_utils import get_all_alumnos_details, connect_db, get_clockings_for_month, reset_all_delays, get_alumno_details_by_rut, update_alumno_details, promote_students
from validation_utils import is_valid_rut
from report_utils import send_report_by_email 
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
# HELPER CLASS: ScrolledFrame
# ----------------------------------------------------
class ScrolledFrame(tk.Frame):
    def __init__(self, parent, *args, **kw):
        tk.Frame.__init__(self, parent, *args, **kw)

        vscrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL)
        vscrollbar.pack(fill=tk.Y, side=tk.RIGHT, expand=tk.FALSE)
        
        canvas = tk.Canvas(self, bd=0, highlightthickness=0, yscrollcommand=vscrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=tk.TRUE)
        vscrollbar.config(command=canvas.yview)

        self.interior = interior = tk.Frame(canvas)
        interior_id = canvas.create_window(0, 0, window=interior, anchor=tk.NW)

        def _configure_interior(event):
            # Update the scrollbars to match the size of the inner frame
            size = (interior.winfo_reqwidth(), interior.winfo_reqheight())
            canvas.config(scrollregion="0 0 %s %s" % size)
            if interior.winfo_reqwidth() != canvas.winfo_width():
                # Update the canvas's width to fit the inner frame
                canvas.config(width=interior.winfo_reqwidth())
        interior.bind('<Configure>', _configure_interior)

        def _configure_canvas(event):
            if interior.winfo_width() != canvas.winfo_width():
                # Update the inner frame's width to fill the canvas
                canvas.itemconfigure(interior_id, width=canvas.winfo_width())
        canvas.bind('<Configure>', _configure_canvas)

        # Bind mouse wheel for scrolling
        def _on_mousewheel(event):
            # For Linux
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
            # For Windows
            else:
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        def _bind_mouse(event=None):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Button-4>", _on_mousewheel)
            canvas.bind_all("<Button-5>", _on_mousewheel)

        def _unbind_mouse(event=None):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind('<Enter>', _bind_mouse)
        canvas.bind('<Leave>', _unbind_mouse)


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
        for F in (MainMenuFrame, NumericPadFrame, EnrollmentFrame, PasswordCheckFrame, AdminFrame, EnrollmentStatusFrame, VerificationStatusFrame, ModifyStudentFrame):
            frame = F(container, self)
            self.frames[F] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.log_messages_widget = self._create_log_widget()
        self._check_and_reset_annual_delays() # Comprobar y resetear atrasos al iniciar el AÑO
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

    def _check_and_reset_annual_delays(self):
        """Verifica si es un nuevo AÑO y resetea los contadores de atrasos si es necesario."""
        last_reset_file = ".last_reset_year"
        current_year = str(datetime.now().year)
        
        try:
            with open(last_reset_file, 'r') as f:
                last_reset_year = f.read().strip()
        except FileNotFoundError:
            last_reset_year = ""

        if current_year != last_reset_year:
            self.log_message("Detectado nuevo año. Reseteando contadores de atrasos y promoviendo cursos...")
            
            # 1. Resetear atrasos
            if reset_all_delays(): 
                self.log_message("Contadores de atrasos reseteados a 0 para el nuevo año.")
            else:
                self.log_message("Error al resetear los contadores de atrasos.")
                
            # 2. Promover estudiantes
            success, promoted, graduated = promote_students()
            if success:
                self.log_message(f"Promoción anual completada. Promovidos: {promoted}, Egresados: {graduated}.")
            else:
                self.log_message("Error durante la promoción anual de estudiantes.")

            try:
                with open(last_reset_file, 'w') as f:
                    f.write(current_year)
            except Exception as e:
                self.log_message(f"No se pudo guardar el año de reseteo: {e}")
        else:
            self.log_message("El contador de atrasos ya está actualizado para este año.")

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

    def show_frame(self, cont, **kwargs):
        """Muestra el frame solicitado y le pasa argumentos opcionales."""
        frame = self.frames[cont]
        if hasattr(frame, 'on_show'):
            frame.on_show(**kwargs)
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

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        main_frame = tk.Frame(self, padx=50, pady=50)
        main_frame.grid(row=0, column=0, sticky="")

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
            self.controller.log_message("Contraseña incorrecta. Acceso denegado.")
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

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Frame principal que contendrá el formulario
        main_content_frame = tk.Frame(self)
        main_content_frame.grid(row=0, column=0, sticky="")

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

        # >>> NUEVO CAMPO: Umbral de Advertencia de Atrasos
        tk.Label(form_frame, text="Umbral Advertencia Atrasos (Ej: 10):", font=("Helvetica", 12)).grid(row=6, column=0, padx=10, pady=10, sticky="w")
        self.max_atrasos_warning_entry = tk.Entry(form_frame, width=30, font=("Helvetica", 12))
        self.max_atrasos_warning_entry.grid(row=6, column=1, padx=10, pady=10, sticky="e")
        self.max_atrasos_warning_entry.insert(0, "10")  # Valor por defecto

        # >>> NUEVO CAMPO: Curso
        tk.Label(form_frame, text="Curso (*):", font=("Helvetica", 12)).grid(row=7, column=0, padx=10, pady=10, sticky="w")
        self.curso_combobox = ttk.Combobox(form_frame, values=["1ro Medio", "2do Medio", "3ro Medio", "4to Medio"], state="readonly", font=("Helvetica", 12), width=28)
        self.curso_combobox.grid(row=7, column=1, padx=10, pady=10, sticky="e")
        self.curso_combobox.current(0) # Default 1ro Medio

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

    def on_show(self, **kwargs):
        """Se ejecuta cada vez que se muestra el frame."""
        self._unlock_all_buttons()
        self._clear_fields()
        self.controller.log_message("Pantalla de enrolamiento lista.")
                  
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
        max_warn = self.max_atrasos_warning_entry.get().strip()
        curso = self.curso_combobox.get().strip()

        # 2. Validación de campos obligatorios
        # --- NUEVA VALIDACIÓN: Comprobar si hay un dispositivo ANTES de continuar ---
        try:
            self.controller.fprint_context.enumerate()
            devices = self.controller.fprint_context.get_devices()
            if not devices:
                self.controller.log_message("ERROR: No se detectó ningún lector de huellas conectado.")
                messagebox.showerror("Error de Hardware", "No se encontró ningún lector de huellas. Por favor, conecte el dispositivo e intente de nuevo.")
                return
        except Exception as e:
            messagebox.showerror("Error de Hardware", f"No se pudo acceder al lector de huellas: {e}")
            return
        if not p_n or not a_p or not a_m or not rut or not hora_max:
            self.controller.log_message("ERROR: Los campos obligatorios (*) no pueden estar vacíos.")
            messagebox.showerror("Error", "Por favor, complete todos los campos obligatorios.")
            return
            
        # 3. Validación de formato de RUT
        if not is_valid_rut(rut):
            self.controller.log_message(f"ERROR: RUT ingresado ({rut}) no es válido.")
            messagebox.showerror("Error", "El RUT ingresado no es válido. Revise el formato y dígito verificador.")
            return
            
        # 4. Validación de formato de Hora
        try:
            datetime.strptime(hora_max, '%H:%M')
            hora_max = hora_max + ":00" # Se completa a formato H:M:S para la DB
        except ValueError:
            self.controller.log_message(f"ERROR: El formato de hora '{hora_max}' es inválido (debe ser HH:MM).")
            messagebox.showerror("Error de Validación", "El formato de hora máxima de tardanza debe ser HH:MM (ej: 08:15).")
            return

        # Validar el umbral de advertencia (debe ser entero >=0)
        try:
            max_warn_int = int(max_warn)
            if max_warn_int < 0:
                raise ValueError
        except Exception:
            self.controller.log_message(f"ERROR: Umbral de advertencia inválido: {max_warn}")
            messagebox.showerror("Error de Validación", "El umbral de advertencia debe ser un número entero (ej: 10).")
            return

        # 5. Limpieza del RUT (quitar puntos y guiones para el ID de la huella)
        rut_clean = rut.upper().replace(".", "").replace("-", "")

        # 6. Almacenar datos para pasar al frame de estado (ahora incluye max_warn_int y curso)
        alumno_data = (p_n, s_n, a_p, a_m, rut_clean, hora_max, max_warn_int, curso)

        # 7. Bloquear UI y limpiar campos antes de navegar
        self._clear_fields() 
        self._lock_all_buttons() # Bloquear botones de este frame
        self.controller.lock_main_menu_buttons() # Bloquear botones del menú principal
        
        # 8. CAMBIO CLAVE: Navegar al nuevo frame de estado y pasar los datos.
        # EnrollmentStatusFrame se encargará de:
        # a) Iniciar el hilo de enrolamiento.
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
        self.max_atrasos_warning_entry.delete(0, tk.END)
        self.max_atrasos_warning_entry.insert(0, "10")  # Resetear a valor por defecto
        self.curso_combobox.current(0) # Resetear a 1ro Medio

    def _run_enrollment(self, p_n, s_n, a_p, a_m, rut_clean, hora_max, max_warn, curso):
        """Ejecuta el enrolamiento y desbloquea los botones al finalizar."""
        try:
            enroll_user(p_n, s_n, a_p, a_m, rut_clean, hora_max, max_warn, curso,
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
# 4.5 FRAME: MODIFICAR DATOS ALUMNO (ModifyStudentFrame)
# ---------------------------------------------------
class ModifyStudentFrame(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Frame principal
        main_content_frame = tk.Frame(self)
        main_content_frame.grid(row=0, column=0, sticky="")

        tk.Label(main_content_frame, text="MODIFICAR DATOS DE ALUMNO", font=("Helvetica", 18, "bold")).pack(pady=20)

        # --- SECCIÓN DE BÚSQUEDA ---
        search_frame = tk.LabelFrame(main_content_frame, text="Buscar Alumno", padx=15, pady=15, font=("Helvetica", 12))
        search_frame.pack(padx=20, pady=10, fill=tk.X)

        tk.Label(search_frame, text="Ingrese RUT (sin puntos, con guion):", font=("Helvetica", 12)).pack(side=tk.LEFT, padx=5)
        self.search_rut_entry = tk.Entry(search_frame, width=20, font=("Helvetica", 12))
        self.search_rut_entry.pack(side=tk.LEFT, padx=5)
        self.search_rut_entry.bind('<Return>', lambda event: self._search_student())

        self.search_button = tk.Button(search_frame, text="BUSCAR", command=self._search_student,
                                       bg="#0066AA", fg="white", font=("Helvetica", 10, "bold"))
        self.search_button.pack(side=tk.LEFT, padx=10)

        # --- SECCIÓN DE EDICIÓN ---
        self.form_frame = tk.LabelFrame(main_content_frame, text="Datos del Alumno", padx=15, pady=15, font=("Helvetica", 12))
        self.form_frame.pack(padx=20, pady=10)

        # Campos
        self.primer_nombre_entry = self._create_entry_field(self.form_frame, "Primer Nombre (*):", 0)
        self.segundo_nombre_entry = self._create_entry_field(self.form_frame, "Segundo Nombre:", 1)
        self.apellido_paterno_entry = self._create_entry_field(self.form_frame, "Apellido Paterno (*):", 2)
        self.apellido_materno_entry = self._create_entry_field(self.form_frame, "Apellido Materno (*):", 3)
        
        # Hora Máxima
        tk.Label(self.form_frame, text="Hora Máxima de Tardanza (HH:MM) (*):", font=("Helvetica", 12)).grid(row=4, column=0, padx=10, pady=10, sticky="w")
        self.hora_max_tardanza_entry = tk.Entry(self.form_frame, width=30, font=("Helvetica", 12))
        self.hora_max_tardanza_entry.grid(row=4, column=1, padx=10, pady=10, sticky="e")

        # Umbral Warning
        tk.Label(self.form_frame, text="Umbral Advertencia Atrasos:", font=("Helvetica", 12)).grid(row=5, column=0, padx=10, pady=10, sticky="w")
        self.max_atrasos_warning_entry = tk.Entry(self.form_frame, width=30, font=("Helvetica", 12))
        self.max_atrasos_warning_entry.grid(row=5, column=1, padx=10, pady=10, sticky="e")

        # Curso
        tk.Label(self.form_frame, text="Curso:", font=("Helvetica", 12)).grid(row=6, column=0, padx=10, pady=10, sticky="w")
        self.curso_combobox = ttk.Combobox(self.form_frame, values=["1ro Medio", "2do Medio", "3ro Medio", "4to Medio"], state="readonly", font=("Helvetica", 12), width=28)
        self.curso_combobox.grid(row=6, column=1, padx=10, pady=10, sticky="e")

        self.form_frame.grid_columnconfigure(1, weight=1)

        # Botones de Acción
        button_frame = tk.Frame(main_content_frame, pady=20)
        button_frame.pack(pady=10)

        self.save_button = tk.Button(button_frame, text="GUARDAR CAMBIOS", 
                  command=self._save_changes, 
                  bg="#4CAF50", fg="white", font=("Helvetica", 14, "bold"), padx=20, pady=10)
        self.save_button.pack(side=tk.LEFT, padx=10)

        self.cancel_button = tk.Button(button_frame, text="Cancelar y Volver", 
                  command=self._cancel_and_return, 
                  font=("Helvetica", 14), padx=20, pady=10)
        self.cancel_button.pack(side=tk.LEFT, padx=10)

        # Estado inicial: formulario deshabilitado
        self._disable_form()
        self.current_rut_clean = None

    def on_show(self, **kwargs):
        """Resetear vista al mostrar."""
        self.search_rut_entry.delete(0, tk.END)
        self._clear_form()
        self._disable_form()
        self.search_rut_entry.focus_set()

    def _create_entry_field(self, parent, label_text, row):
        tk.Label(parent, text=label_text, font=("Helvetica", 12)).grid(row=row, column=0, padx=10, pady=10, sticky="w")
        entry = tk.Entry(parent, width=30, font=("Helvetica", 12))
        entry.grid(row=row, column=1, padx=10, pady=10, sticky="e")
        return entry

    def _disable_form(self):
        for child in self.form_frame.winfo_children():
            if isinstance(child, tk.Entry):
                child.config(state='disabled')
        self.curso_combobox.config(state='disabled')
        self.save_button.config(state='disabled')

    def _enable_form(self):
        for child in self.form_frame.winfo_children():
            if isinstance(child, tk.Entry):
                child.config(state='normal')
        self.curso_combobox.config(state='readonly')
        self.save_button.config(state='normal')

    def _clear_form(self):
        self.primer_nombre_entry.config(state='normal')
        self.primer_nombre_entry.delete(0, tk.END)
        self.segundo_nombre_entry.config(state='normal')
        self.segundo_nombre_entry.delete(0, tk.END)
        self.apellido_paterno_entry.config(state='normal')
        self.apellido_paterno_entry.delete(0, tk.END)
        self.apellido_materno_entry.config(state='normal')
        self.apellido_materno_entry.delete(0, tk.END)
        self.hora_max_tardanza_entry.config(state='normal')
        self.hora_max_tardanza_entry.delete(0, tk.END)
        self.max_atrasos_warning_entry.config(state='normal')
        self.max_atrasos_warning_entry.delete(0, tk.END)
        self.curso_combobox.config(state='readonly')
        self.curso_combobox.set('')
        self.current_rut_clean = None

    def _search_student(self):
        rut = self.search_rut_entry.get().strip()
        if not rut:
            messagebox.showerror("Error", "Ingrese un RUT para buscar.")
            return

        if not is_valid_rut(rut):
            messagebox.showerror("Error", "RUT inválido.")
            return

        rut_clean = rut.upper().replace(".", "").replace("-", "")
        
        # Buscar en DB
        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT primer_nombre, segundo_nombre, apellido_paterno, apellido_materno, hora_max_tardanza, max_atrasos_warning, curso
                FROM ALUMNOS WHERE rut = ?
            """, (rut_clean,))
            row = cursor.fetchone()
            conn.close()

            if row:
                self._enable_form()
                self._clear_form() # Limpia pero deja habilitado
                
                pn, sn, ap, am, hmax, mwarn, curso = row
                self.primer_nombre_entry.insert(0, pn)
                if sn: self.segundo_nombre_entry.insert(0, sn)
                self.apellido_paterno_entry.insert(0, ap)
                self.apellido_materno_entry.insert(0, am)
                self.hora_max_tardanza_entry.insert(0, hmax if hmax else "08:15:00")
                self.max_atrasos_warning_entry.insert(0, str(mwarn) if mwarn is not None else "10")
                if curso: self.curso_combobox.set(curso)
                
                self.current_rut_clean = rut_clean
                self.controller.log_message(f"Alumno encontrado: {pn} {ap}")
            else:
                self.controller.log_message(f"No se encontró alumno con RUT {rut}")
                
                # Fix: Limpiar y LUEGO deshabilitar para asegurar que queden bloqueados
                self._clear_form()
                self._disable_form()
                
                # Prompt para enrolar nuevo
                response = messagebox.askyesno(
                    "Alumno no registrado", 
                    "El alumno no está registrado.\n¿Desea registrar un nuevo usuario?"
                )
                if response: # Si es True (Sí)
                    self.controller.show_frame(EnrollmentFrame)

        except Exception as e:
            self.controller.log_message(f"Error al buscar alumno: {e}")
            messagebox.showerror("Error", f"Error de base de datos: {e}")

    def _save_changes(self):
        if not self.current_rut_clean:
            return

        pn = self.primer_nombre_entry.get().strip()
        sn = self.segundo_nombre_entry.get().strip()
        ap = self.apellido_paterno_entry.get().strip()
        am = self.apellido_materno_entry.get().strip()
        hmax = self.hora_max_tardanza_entry.get().strip()
        mwarn = self.max_atrasos_warning_entry.get().strip()
        curso = self.curso_combobox.get().strip()

        if not pn or not ap or not am or not hmax:
             messagebox.showerror("Error", "Complete los campos obligatorios (*).")
             return

        # Validar hora
        try:
            # Si el usuario pone HH:MM, agregar :00
            if len(hmax.split(':')) == 2:
                hmax += ":00"
            datetime.strptime(hmax, '%H:%M:%S')
        except ValueError:
            messagebox.showerror("Error", "Formato de hora inválido (use HH:MM).")
            return

        # Validar warning
        try:
            mwarn_int = int(mwarn)
            if mwarn_int < 0: raise ValueError
        except:
            messagebox.showerror("Error", "El umbral debe ser un número entero positivo.")
            return

        if update_alumno_details(self.current_rut_clean, pn, sn, ap, am, hmax, mwarn_int, curso):
            self.controller.log_message(f"Datos actualizados para RUT {self.current_rut_clean}")
            messagebox.showinfo("Éxito", "Datos del alumno actualizados correctamente.")
            self._cancel_and_return()
        else:
            messagebox.showerror("Error", "No se pudo actualizar la base de datos.")

    def _cancel_and_return(self):
        self._clear_form()
        self._disable_form()
        self.controller.show_frame(AdminFrame)

# ---------------------------------------------------
# 5. FRAME: PAD NUMÉRICO PARA INGRESO DE RUT
# ---------------------------------------------------
class NumericPadFrame(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Usar ScrolledFrame para asegurar que todo el contenido sea visible
        scrolled_frame = ScrolledFrame(self)
        scrolled_frame.pack(fill="both", expand=True)

        # Frame principal centrado
        main_frame = tk.Frame(scrolled_frame.interior, padx=50, pady=50)
        main_frame.pack(expand=True, pady=20)
        
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
        
        # Limpiar display y volver al menú
        self._clear_display()

        # Navegar al frame de estado de verificación
        self.controller.log_message(f"Iniciando verificación 1:1 para RUT: {rut_clean}...")
        self.controller.show_frame(VerificationStatusFrame, rut=rut_clean)
    
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

        # Utilizar ScrolledFrame para hacer que todo el contenido sea desplazable
        scrolled_frame = ScrolledFrame(self)
        scrolled_frame.pack(fill=tk.BOTH, expand=True)

        # El contenido va dentro de 'interior'. Usamos un frame central para mantener el diseño.
        main_content_frame = tk.Frame(scrolled_frame.interior)
        main_content_frame.pack(expand=True, padx=20, pady=20)

        tk.Label(main_content_frame, text="PANEL DE ADMINISTRACIÓN", font=("Helvetica", 16, "bold")).pack(pady=20)
        
        # --- SECCIÓN EXPORTAR EXCEL ---
        export_frame = tk.LabelFrame(main_content_frame, text="Exportar Registros de Asistencia (Excel)", padx=10, pady=10, font=("Helvetica", 12, "bold"))
        export_frame.pack(padx=50, pady=10, ipadx=10, fill=tk.X)
        
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

        tk.Button(users_frame, text="MODIFICAR DATOS ALUMNO", 
                  command=lambda: controller.show_frame(ModifyStudentFrame),
                  bg="#FF9800", fg="white", font=("Helvetica", 12, "bold"), height=2).pack(fill=tk.X, pady=(0, 5))

        # Botón para reiniciar atrasos (NUEVO)
        tk.Button(users_frame, text="REINICIAR ATRASOS (TODOS)", 
                  command=self._reset_delays_confirmation,
                  bg="#D32F2F", fg="white", font=("Helvetica", 12, "bold"), height=2).pack(fill=tk.X, pady=(0, 5))

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
            self.controller.log_message(f"No se pudo cargar la configuración de email: {e}")
    
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
            
            self.controller.log_message("Configuración de correo remitente guardada exitosamente.")
            messagebox.showinfo("Éxito", "La configuración de correo remitente ha sido guardada correctamente.")
            
        except Exception as e:
            error_msg = f"Error al guardar la configuración de email: {e}"
            self.controller.log_message(f"{error_msg}")
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
        Obtiene los registros de asistencia para el mes/año, los ordena cronológicamente 
        y los exporta a un archivo Excel.
        """
        if not PD_AVAILABLE:
            self.controller.log_message("Error: Pandas no está instalado. No se puede generar el Excel.")
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
            
            # 3. CONSOLIDAR y CAMBIAR NOMBRES DE COLUMNAS
            df.rename(columns={
                'rut': 'RUT', 
                'Nombre_Completo': 'Nombre Completo',
                'fecha': 'Fecha', 
                'hora_entrada': 'Hora de Entrada',
                'estado': 'Estado de Asistencia'
            }, inplace=True)

            # 4. ORDENAR CRONOLÓGICAMENTE (de la más antigua a la más nueva)
            # Primero por Fecha, luego por Hora de Entrada
            df['Hora de Entrada'] = df['Hora de Entrada'].astype(str)
            df['Fecha'] = pd.to_datetime(df['Fecha'])
            
            # La columna Fecha ya es la columna "pivote" cronológica
            df = df.sort_values(by=['Fecha', 'Hora de Entrada'], ascending=[True, True])
            
            # Opcional: Reordenar las columnas para que RUT y Nombre aparezcan primero
            df = df[['RUT', 'Nombre Completo', 'Fecha', 'Hora de Entrada', 'Estado de Asistencia']]
            
            # 5. Exportar a Excel
            filename = f"Marcaciones_Detalle_{year}_{month:02d}.xlsx"
            filepath = os.path.join(os.getcwd(), filename) # Guardar en el directorio actual
            
            df.to_excel(filepath, index=False)
            
            self.controller.log_message(f"Reporte Excel generado: {filepath}")
            
            if send_email:
                # 6. Enviar por correo si se solicita
                recipient = self.email_receiver_entry.get()
                subject = f"Reporte Detallado de Marcaciones {month:02d}/{year}"
                body = f"Adjunto encontrarás el reporte detallado de todas las marcaciones (fecha y hora) para el mes de {month}/{year}."
                
                success, msg = send_report_by_email(
                    recipient_email=recipient,
                    subject=subject,
                    body=body,
                    attachment_path=filepath
                )
                if success:
                    messagebox.showinfo("Correo Enviado", f"Reporte enviado exitosamente a {recipient}")
                else:
                    messagebox.showerror("Error de Correo", f"Fallo al enviar el correo: {msg}")
            else:
                messagebox.showinfo("Exportado", f"Excel de marcaciones detallado generado: {filepath}")

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
                if idx_estado is not None and row[idx_estado] and str(row[idx_estado]).lower() in ['atraso', 'tardanza']:
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
                    self.controller.log_message(f"Exportación CSV exitosa: {fp}")
                    messagebox.showinfo("Exportado", f"CSV generado: {fp}")
                except Exception as e:
                    self.controller.log_message(f"Error exportando CSV: {e}")
                    messagebox.showerror("Error", f"No se pudo exportar: {e}")

            ttk.Button(btn_frame, text="Exportar CSV", command=_export_csv).pack(side=tk.RIGHT, padx=8)

        except Exception as e:
            self.controller.log_message(f"Error al mostrar marcaciones en tabla: {e}")
            messagebox.showerror("Error", f"Ocurrió un error al mostrar las marcaciones: {e}")

    def _reset_delays_confirmation(self):
        """Muestra diálogo de confirmación y resetea los atrasos si se confirma."""
        if messagebox.askyesno("Confirmar Reset", 
                               "¿Está seguro de que desea reiniciar los atrasos de TODOS los alumnos a 0?\n\nEsta acción no se puede deshacer."):
            if reset_all_delays():
                self.controller.log_message("Se han reseteado los atrasos de todos los alumnos.")
                messagebox.showinfo("Éxito", "Los contadores de atrasos han sido reiniciados a 0.")
            else:
                self.controller.log_message("Error al intentar resetear atrasos.")
                messagebox.showerror("Error", "Ocurrió un error al intentar reiniciar los atrasos. Revise el log.")

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
        
    def on_show(self, data, from_frame):
        """Prepara e inicia el proceso al mostrar la ventana."""
        self.alumno_data = data
        self.status_label.config(text="Coloque el dedo en el lector cuando se le solicite.")
        self.back_button.config(state=tk.DISABLED)
        
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
            p_n, s_n, a_p, a_m, rut_clean, hora_max, max_warn, curso = self.alumno_data
            
            # Llamar a la función de enrolamiento con el lock y el logger
            success, message = enroll_user(
                p_n, s_n, a_p, a_m, rut_clean, hora_max, max_warn, curso,
                logger=self._update_log_message, # Usar el logger de este frame
                fprint_context=self.controller.fprint_context,
                lock=self.controller.fprint_lock # Pasar el lock
            )
            
            if success:
                # Si tiene éxito, el hilo llama a la finalización
                self.controller.after(100, lambda: self._finish_process(f"{message}"))
            else:
                # Si falla, mostrar error y permitir volver
                self.controller.after(100, lambda: self._handle_enrollment_error(message))

        except Exception as e:
            # Si hay una excepción no controlada
            self.controller.after(100, lambda: self._handle_enrollment_error(f"Error crítico: {e}"))
            
    def _handle_enrollment_error(self, error_message):
        """Maneja el error de enrolamiento en la GUI."""
        self._update_log_message(f"{error_message}")
        self.status_label.config(text=f"Error: {error_message}\nIntente nuevamente.")
        
        # Habilitar botón de volver para que el usuario pueda reintentar
        self.back_button.config(state=tk.NORMAL)
        self.controller.unlock_main_menu_buttons()
            
    def _finish_process(self, final_message):
        """Finaliza el proceso y redirige a AdminFrame."""
        self._update_log_message(final_message)
        
        # Desbloquear botones
        self.controller.unlock_main_menu_buttons()
        
        # Esperar un momento para que el usuario lea el mensaje y luego redirigir
        self.controller.after(3000, lambda: self.controller.show_frame(AdminFrame))
        self.controller.log_message(f"Proceso finalizado. Volviendo a Administración.")

    def _cancel_process(self):
        """Permite al usuario volver al panel de administración después de un error."""
        self.controller.log_message("Cancelando y volviendo al panel de administración.")
        # Asegurarse de que los botones principales estén desbloqueados
        self.controller.unlock_main_menu_buttons()
        # Redirigir al panel de administración
        self.controller.show_frame(AdminFrame)


# ----------------------------------------------------
# 8. FRAME: ESTADO DE VERIFICACIÓN (VerificationStatusFrame)
# ----------------------------------------------------
class VerificationStatusFrame(BaseFrame):
    """Muestra el estado de la verificación 1:1 de huella."""
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        self.rut_to_verify = None

        tk.Label(self, text="VERIFICACIÓN DE ASISTENCIA", font=("Helvetica", 20, "bold"), fg="#4CAF50").pack(pady=(50, 20))
        
        self.status_label = tk.Label(self, text="Iniciando...", font=("Helvetica", 14), fg="black")
        self.status_label.pack(pady=10)

        self.back_button = tk.Button(self, text="Cancelar", command=self._cancel_process, 
                                     bg="#F44336", fg="white", font=("Helvetica", 12, "bold"))
        self.back_button.pack(pady=50, ipadx=20, ipady=10)

    def on_show(self, rut):
        """Prepara e inicia el proceso de verificación."""
        self.rut_to_verify = rut
        self.status_label.config(text=f"Verificando para RUT: {rut}\nColoque el dedo en el lector.")
        self.back_button.config(state=tk.NORMAL)
        
        # Bloquear botones del menú principal
        self.controller.lock_main_menu_buttons()
        
        # Iniciar el hilo de verificación
        threading.Thread(target=self._run_verification_thread, daemon=True).start()

    def _update_status_message(self, message):
        """Actualiza el mensaje de estado en la GUI."""
        self.controller.after(0, lambda: self.status_label.config(text=message))
        self.controller.after(0, lambda: self.controller.log_message(message))

    def _run_verification_thread(self):
        """Ejecuta la lógica de verificación en un hilo secundario."""
        try:
            self._update_status_message("Por favor, coloque su dedo en el lector...")
            
            identified_rut = identify_user_automatically(
                self.controller.fprint_context, 
                rut_to_verify=self.rut_to_verify,
                lock=self.controller.fprint_lock
            )
            
            if identified_rut:
                msg = f"¡Bienvenido(a)! Asistencia registrada para {identified_rut}."
                self._update_status_message(msg)
                self.controller.show_timed_messagebox("Éxito", msg, duration=3000)
                self.controller.after(3000, self._finish_process) # Solo en caso de éxito, volver al menú
            else:
                msg = "La huella no coincide con el RUT ingresado."
                self._update_status_message(f"{msg}")
                # Mostrar el error y luego volver al pad numérico
                self.controller.after(2000, self._return_to_rut_pad)

        except Exception as e:
            error_msg = f"Error durante la verificación: {e}"
            self._update_status_message(f"{error_msg}")
            # En caso de error, también volver al pad numérico
            self.controller.after(2000, self._return_to_rut_pad)

    def _finish_process(self):
        """Desbloquea botones y vuelve al menú principal."""
        self.controller.unlock_main_menu_buttons()
        self.controller.show_frame(MainMenuFrame)

    def _cancel_process(self):
        """Cancela el proceso y vuelve al menú principal."""
        self._finish_process()

    def _return_to_rut_pad(self):
        """Desbloquea botones y vuelve al pad numérico."""
        self.controller.unlock_main_menu_buttons()
        self.controller.show_frame(NumericPadFrame)
    


# ----------------------------------------------------
# 9. INICIO DE LA APLICACIÓN
# ----------------------------------------------------

if __name__ == "__main__":
    try:
        # Inicializa la base de datos (crea ALUMNOS y ASISTENCIAS)
        connect_db().close() 
        app = FingerprintApp()
        app.mainloop()
    except Exception as db_err:
        print(f"ERROR: No se pudo inicializar la aplicación de GUI. Revise los errores anteriores o la conexión a la base de datos: {db_err}")
