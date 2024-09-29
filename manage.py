import subprocess
import time
import sys
import signal
import logging
import os

# Add the project root and app directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
sys.path.append(os.path.join(current_dir, 'app'))

# To start the venv: source OBTBvenv/bin/activate
# To start the script: python manage.py start

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAIN_APP = "app/routes.py"

main_process = None

def start_server():
    global main_process
    
    logger.info("Starting Flask Application...")
    env = os.environ.copy()
    env['PYTHONPATH'] = f"{current_dir}:{os.path.join(current_dir, 'app')}:{env.get('PYTHONPATH', '')}"
    main_process = subprocess.Popen([sys.executable, MAIN_APP], env=env)
    
    logger.info("Server is now running.")
    return True

def stop_server():
    global main_process
    
    if main_process:
        main_process.terminate()
        try:
            main_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            main_process.kill()
    
    # Call the cleanup function directly
    try:
        from app.routes import cleanup
        cleanup()
    except ImportError as e:
        logger.error(f"Error importing cleanup function: {e}")
    
    logger.info("Server has been stopped and cleanup completed.")
    
    # Ensure all GPIO resources are released
    try:
        import RPi.GPIO as GPIO
        GPIO.cleanup()
    except ImportError:
        logger.warning("RPi.GPIO module not found, skipping GPIO cleanup")

def signal_handler(sig, frame):
    logger.info("Interrupt received, stopping server...")
    stop_server()
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        if command == "start":
            if start_server():
                logger.info("Press Ctrl+C to stop the server.")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    logger.info("Keyboard interrupt received, stopping server...")
                    stop_server()
        elif command == "stop":
            stop_server()
        else:
            logger.error("Unknown command. Use 'start' or 'stop'.")
    else:
        logger.error("Please specify 'start' or 'stop'.")