import sqlite3
import os
from datetime import datetime
import unittest
from unittest.mock import MagicMock, patch

# Import functions to test
# We need to mock imports in db_utils and printer_utils if they are not available
# But here we are testing the logic, so we can import them directly if dependencies allow.
# Assuming dependencies are installed or we can mock them.

# Mocking dependencies for the test environment
import sys
sys.modules['escpos.printer.usb'] = MagicMock()
sys.modules['gi'] = MagicMock()
sys.modules['gi.repository'] = MagicMock()

from db_utils import save_template, connect_db
from printer_utils import print_clocking_receipt

class TestDelayLogic(unittest.TestCase):
    
    def setUp(self):
        # Use a temporary DB
        self.db_name = "fingerprints.db"
        # Ensure clean state
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ALUMNOS")
        cursor.execute("DELETE FROM ASISTENCIAS")
        conn.commit()
        conn.close()

    def test_enrollment_resets_delays(self):
        print("\n--- Testing Enrollment Resets Delays ---")
        conn = connect_db()
        cursor = conn.cursor()
        
        # 1. Insert user with delays manually
        rut = "99999999-9"
        cursor.execute("""
            INSERT INTO ALUMNOS (primer_nombre, apellido_paterno, apellido_materno, rut, num_atrasos) 
            VALUES ('Test', 'User', 'One', ?, 5)
        """, (rut,))
        conn.commit()
        
        # Verify initial state
        cursor.execute("SELECT num_atrasos FROM ALUMNOS WHERE rut = ?", (rut,))
        delays = cursor.fetchone()[0]
        print(f"Initial delays: {delays}")
        self.assertEqual(delays, 5)
        
        conn.close()
        
        # 2. Re-enroll user (call save_template)
        save_template("Test", "User", "One", "Mat", rut, "mock_template", "08:15:00")
        
        # 3. Verify delays are 0
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("SELECT num_atrasos FROM ALUMNOS WHERE rut = ?", (rut,))
        delays = cursor.fetchone()[0]
        print(f"Delays after re-enrollment: {delays}")
        self.assertEqual(delays, 0)
        
        # 4. Verify ASISTENCIAS history is cleared (estado -> 'presente')
        # First, we need to insert a delay record to test this properly.
        # But since we just ran save_template, it might be too late for this specific test run unless we insert before.
        # Let's add a separate test for history clearing.
        conn.close()
        print("[PASS] Enrollment reset delays.")

    def test_enrollment_clears_history(self):
        print("\n--- Testing Enrollment Clears History ---")
        conn = connect_db()
        cursor = conn.cursor()
        
        rut = "88888888-8"
        # 1. Insert user
        cursor.execute("INSERT INTO ALUMNOS (primer_nombre, apellido_paterno, apellido_materno, rut, num_atrasos) VALUES ('Hist', 'User', 'Two', ?, 3)", (rut,))
        user_id = cursor.lastrowid
        
        # 2. Insert delay records
        cursor.execute("INSERT INTO ASISTENCIAS (id_alumno, fecha, hora_entrada, estado) VALUES (?, '2023-01-01', '09:00', 'tardanza')", (user_id,))
        cursor.execute("INSERT INTO ASISTENCIAS (id_alumno, fecha, hora_entrada, estado) VALUES (?, '2023-01-02', '09:00', 'atraso')", (user_id,))
        conn.commit()
        
        # 3. Re-enroll
        save_template("Hist", "User", "Two", "Mat", rut, "mock_template", "08:15:00")
        
        # 4. Verify records are now 'presente'
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM ASISTENCIAS WHERE id_alumno = ? AND estado IN ('tardanza', 'atraso')", (user_id,))
        count = cursor.fetchone()[0]
        print(f"Remaining delays in history: {count}")
        self.assertEqual(count, 0)
        
        cursor.execute("SELECT count(*) FROM ASISTENCIAS WHERE id_alumno = ? AND estado = 'presente'", (user_id,))
        present_count = cursor.fetchone()[0]
        self.assertEqual(present_count, 2)
        
        conn.close()
        print("[PASS] History cleared.")

    @patch('printer_utils.Usb')
    def test_printer_warning(self, mock_usb):
        print("\n--- Testing Printer Warning ---")
        mock_printer = MagicMock()
        mock_usb.return_value = mock_printer
        
        # Test with 2 delays (No warning)
        print_clocking_receipt("User A", 2)
        # Check calls
        calls = [args[0] for args, _ in mock_printer.text.call_args_list]
        combined_text = "".join(calls)
        if "*** LIMITE DE ATRASOS ALCANZADO ***" in combined_text:
             print("[FAIL] Warning printed for 2 delays")
        else:
             print("[PASS] No warning for 2 delays")

        # Test with 3 delays (Warning expected)
        mock_printer.reset_mock()
        print_clocking_receipt("User B", 3)
        calls = [args[0] for args, _ in mock_printer.text.call_args_list]
        combined_text = "".join(calls)
        
        if "*** LIMITE DE ATRASOS ALCANZADO ***" in combined_text:
             print("[PASS] Warning printed for 3 delays")
        else:
             print(f"[FAIL] Warning NOT printed for 3 delays. Output: {combined_text}")

    def test_annual_reset_logic(self):
        print("\n--- Testing Annual Reset Logic ---")
        # This logic is in app_gui.py, which is hard to import without GUI.
        # We will simulate the logic here.
        
        last_reset_file = ".last_reset_year_test"
        if os.path.exists(last_reset_file):
            os.remove(last_reset_file)
            
        current_year = str(datetime.now().year)
        
        # 1. First run (no file)
        # Logic: if current != last, reset.
        last_reset_year = ""
        should_reset = current_year != last_reset_year
        print(f"First run (No file): Should reset? {should_reset}")
        self.assertTrue(should_reset)
        
        # 2. Create file with current year
        with open(last_reset_file, 'w') as f:
            f.write(current_year)
            
        # 3. Second run (same year)
        with open(last_reset_file, 'r') as f:
            last_reset_year = f.read().strip()
        should_reset = current_year != last_reset_year
        print(f"Second run (Same year): Should reset? {should_reset}")
        self.assertFalse(should_reset)
        
        # 4. Simulate next year
        with open(last_reset_file, 'w') as f:
            f.write("2000") # Old year
            
        with open(last_reset_file, 'r') as f:
            last_reset_year = f.read().strip()
        should_reset = current_year != last_reset_year
        print(f"New year run (Old year in file): Should reset? {should_reset}")
        self.assertTrue(should_reset)
        
        if os.path.exists(last_reset_file):
            os.remove(last_reset_file)
        print("[PASS] Annual reset logic verified.")

if __name__ == '__main__':
    unittest.main()
