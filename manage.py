import subprocess
import time
import sys
import signal
import logging

# To start the venv: source OBTBvenv/bin/activate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAIN_APP = "main.py"

main_process = None

def start_server():
    global main_process
    
    logger.info("Starting Flask Application...")
    main_process = subprocess.Popen(["python", MAIN_APP])
    
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
    
    logger.info("Server has been stopped.")

def signal_handler(sig, frame):
    logger.info("Interrupt received, stopping server...")
    stop_server()
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    
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