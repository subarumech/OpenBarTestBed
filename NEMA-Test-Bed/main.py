from flask import Flask, jsonify, request, render_template
from flask_socketio import SocketIO
from motor_controller import MotorController
import logging
import atexit
import signal

logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
socketio = SocketIO(app)

motor_controller = MotorController(socketio)

cleanup_done = False

@app.route('/')
def index():
    return render_template('index.html', cache_timeout=0)

@app.route('/set_speed', methods=['POST'])
def set_speed():
    speed = request.json['speed']
    logger.info(f"Setting speed to {speed}")
    motor_controller.set_speed(speed)
    return jsonify({"status": "success"})

@app.route('/start', methods=['POST'])
def start_motor():
    logger.info("Starting motor")
    motor_controller.start()
    socketio.emit('motor_status', {'status': 'running'})
    return jsonify({"status": "success"})

@app.route('/stop', methods=['POST'])
def stop_motor():
    logger.info("Stopping motor")
    motor_controller.stop()
    return jsonify({"status": "success"})

@app.route('/reset_limit_switch', methods=['POST'])
def reset_limit_switch():
    logger.info("Resetting limit switch")
    motor_controller.reset_limit_switch()
    return jsonify({"status": "success"})

@app.route('/get_limit_switch_status', methods=['GET'])
def get_limit_switch_status():
    status = motor_controller.get_limit_switch_status()
    return jsonify({"limit_switch_triggered": status})

@app.route('/home', methods=['POST'])
def home_motor():
    logger.info("Homing motor")
    motor_controller.home()
    return jsonify({"status": "success"})

@app.route('/get_position', methods=['GET'])
def get_position():
    position = motor_controller.get_position()
    return jsonify({"position": position})

@app.route('/is_homed', methods=['GET'])
def is_homed():
    homed = motor_controller.is_homed
    return jsonify({"is_homed": homed})

@app.route('/go_to_position', methods=['POST'])
def go_to_position():
    position = request.json['position']
    logger.info(f"Moving to position: {position}")
    motor_controller.go_to_position(position)
    return jsonify({"status": "success"})

@app.route('/activate', methods=['POST'])
def activate():
    logger.info("Activating system")
    motor_controller.activate()
    return jsonify({"status": "success"})

@app.route('/deactivate', methods=['POST'])
def deactivate():
    logger.info("Deactivating system")
    motor_controller.deactivate()
    return jsonify({"status": "success"})

@app.route('/start_direction', methods=['POST'])
def start_direction():
    direction = request.json['direction']
    logger.info(f"Starting motor in direction: {direction}")
    motor_controller.start_direction(direction)
    return jsonify({"status": "success"})

def cleanup():
    global cleanup_done
    if not cleanup_done:
        cleanup_done = True
        motor_controller.cleanup()
        logger.info("Application cleanup completed")

atexit.register(cleanup)
signal.signal(signal.SIGTERM, lambda signum, frame: cleanup())
signal.signal(signal.SIGINT, lambda signum, frame: cleanup())

@socketio.on('connect')
def handle_connect():
    logger.info("Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    logger.info("Client disconnected")

if __name__ == '__main__':
    logger.info("Starting Flask application with integrated motor control")
    try:
        socketio.run(app, host='0.0.0.0', port=6900, debug=True)
    finally:
        cleanup()