import threading
import time
import sys

# Mock FPrint
class MockDevice:
    def __init__(self):
        self.opened = False
        
    def open_sync(self):
        if self.opened:
            raise Exception("Device already open")
        self.opened = True
        print("Device opened")
        
    def close_sync(self):
        if not self.opened:
            print("Warning: Device not open")
        self.opened = False
        print("Device closed")
        
    def enroll_sync(self, print_data):
        if not self.opened:
            raise Exception("Device not open")
        print("Enrolling...")
        time.sleep(1) # Simulate work
        print("Enrollment done")
        
    def is_opened(self):
        return self.opened

class MockContext:
    def __init__(self):
        self.device = MockDevice()
        
    def get_devices(self):
        return [self.device]
        
    def enumerate(self):
        print("Enumerating devices...")

class MockPrint:
    @staticmethod
    def new(device):
        return MockPrint()
    
    def set_username(self, name):
        pass
    
    def serialize(self):
        return b"mock_data"

# Mock Global FPrint
class FPrint:
    Print = MockPrint

# Mock enroll_user from enroll_test.py
def enroll_user(rut, logger, fprint_context, lock):
    def _log(msg):
        if logger: logger(msg)
        else: print(msg)
        
    device = None
    if fprint_context is None:
        _log("No context")
        return False, "No context"

    try:
        fprint_context.enumerate() # New call
        devices = fprint_context.get_devices()
        device = devices[0]
    except Exception as e:
        _log(f"Error getting device: {e}")
        return False, f"Error getting device: {e}"

    with lock:
        try:
            _log(f"Start enroll {rut}")
            if not device.is_opened():
                device.open_sync()
            
            fprint = FPrint.Print.new(device)
            fprint.set_username(rut)
            
            device.enroll_sync(fprint)
            _log("Enroll success")
            
            device.close_sync()
            return True, "Success"
            
        except Exception as e:
            _log(f"Error during enroll: {e}")
            try:
                if device: device.close_sync()
            except:
                pass
            return False, f"Error: {e}"
        finally:
            try:
                if device and device.is_opened():
                    device.close_sync()
            except:
                pass

# Simulation
def run_test():
    ctx = MockContext()
    lock = threading.Lock()
    
    def logger(msg):
        print(f"[LOG] {msg}")
        
    print("--- Test 1: Enroll User A ---")
    success, msg = enroll_user("11111111-1", logger, ctx, lock)
    print(f"Result: {success}, {msg}")
    
    print("\n--- Test 2: Enroll User B ---")
    success, msg = enroll_user("22222222-2", logger, ctx, lock)
    print(f"Result: {success}, {msg}")
    
    if ctx.device.is_opened():
        print("\n[FAIL] Device left open!")
    else:
        print("\n[PASS] Device closed properly.")

if __name__ == "__main__":
    run_test()
