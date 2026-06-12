import sys
import os
import time
import threading
import unittest
import uvicorn
import socket

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from secure_space_app.backend.app.main import app

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0

def main():
    backend_port = 8089
    server = None
    thread = None
    
    if not is_port_in_use(backend_port):
        config = uvicorn.Config(
            app, 
            host="127.0.0.1", 
            port=backend_port, 
            log_level="warning"
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        
        # Wait for uvicorn to start up
        for _ in range(30):
            if is_port_in_use(backend_port):
                break
            time.sleep(0.1)
        print("Real database-backed backend started successfully. Running test suite...")
    else:
        print("Real database-backed backend is already running on port 8089. Running test suite...")
    
    # Discover and run tests
    loader = unittest.TestLoader()
    suite = loader.discover(
        start_dir=os.path.abspath(os.path.dirname(__file__)),
        pattern="test_e2e_suite.py"
    )
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if server is not None:
        print("Test suite finished. Tearing down real database-backed backend...")
        server.should_exit = True
        thread.join(timeout=3)
    
    # Exit with code 0 if successful, 1 if failures/errors occurred
    if result.wasSuccessful():
        print("All tests passed successfully!")
        sys.exit(0)
    else:
        print(f"Tests failed! Failures: {len(result.failures)}, Errors: {len(result.errors)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
