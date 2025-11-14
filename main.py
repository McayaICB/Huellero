		# main.py (Final)
import sys
from enroll_test import enroll_user
from identify import identify_user_automatically # NUEVA FUNCIÓN
from db_utils import get_registered_users # NUEVA UTILIDAD

# La función 'verify_user' ya no se necesita, la sustituye 'identify_user_automatically'

def show_menu():
    """Muestra el menú principal."""
    print("\n====================================")
    print("         MENÚ HUELLA DACTILAR       ")
    print("====================================")
    print("1. Registrar nuevo usuario (Enroll)")
    print("2. IDENTIFICACIÓN AUTOMÁTICA (Scan)") # Opción 2 cambiada
    print("3. Mostrar usuarios registrados")
    print("4. Salir")
    print("------------------------------------")


def main():
    """Bucle principal de la aplicación."""
    
    while True:
        show_menu()
        
        choice = input("Selecciona una opción (1-4): ")
        
        if choice == '1':
            # REGISTRAR
            username = input("Ingresa el nombre de usuario a registrar: ")
            if username:
                enroll_user(username)
            else:
                print("El nombre de usuario no puede estar vacío.")
            
        elif choice == '2':
            # IDENTIFICACIÓN AUTOMÁTICA
            identify_user_automatically()
            
        elif choice == '3':
            # MOSTRAR
            registered_users = get_registered_users() # Usamos la función de la BD
            print("\n--- Usuarios Registrados ---")
            if registered_users:
                for user in registered_users:
                    print(f"- {user}")
            else:
                print("No hay plantillas guardadas.")
        
        elif choice == '4':
            # SALIR
            print("Saliendo de la aplicación. ¡Hasta luego!")
            sys.exit(0)
            
        else:
            print("Opción no válida. Por favor, intenta de nuevo.")
            
        input("\nPresiona ENTER para continuar...")


if __name__ == "__main__":
    main()
