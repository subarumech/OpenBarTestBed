from flask import Flask, jsonify, request, render_template, g
from flask_socketio import SocketIO
from motor_controller import MotorController  # Change this line
import logging
import atexit
import signal
from flask.logging import default_handler
from database import init_db, insert_recipe, update_recipe, delete_recipe, get_all_recipes, get_recipe
import threading
import time
import os

# Suppress werkzeug logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# Configure your app's logger
app_logger = logging.getLogger(__name__)
app_logger.setLevel(logging.INFO)

logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add this global variable at the top of the file, after the imports
cleanup_done = False

motor_controller = None

def create_app():
    global motor_controller
    app = Flask(__name__)
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    socketio = SocketIO(app)

    init_db()  # This will only create the database if it doesn't exist

    if motor_controller is None:
        motor_controller = MotorController(socketio)

    @app.teardown_appcontext
    def close_connection(exception):
        db = getattr(g, '_database', None)
        if db is not None:
            db.close()

    # ... rest of your route definitions ...

    return app, socketio

app, socketio = create_app()

# Remove these global variables
# cleanup_done = False
# is_shutting_down = False
# homing_thread = None

@app.route('/')
def index():
    return render_template('index.html', cache_timeout=0)

@app.route('/manual_movement')
def manual_movement():
    return render_template('manual_movement.html')

@app.route('/manual_pouring')
def manual_pouring():
    return render_template('manual_pouring.html')

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

@app.route('/pour', methods=['POST'])
def pour():
    ingredient = request.json['ingredient']
    volume = request.json['volume']
    logger.info(f"Received pour request for {ingredient} (volume: {volume})")
    result = motor_controller.pour(ingredient, volume)
    logger.info(f"Pour result: {result}")
    return jsonify(result)

@app.route('/recipes')
def recipes():
    return render_template('recipes.html')

@app.route('/recipe/form')
def recipe_form():
    recipe_id = request.args.get('id')
    return render_template('recipe_form.html', recipe_id=recipe_id)

@app.route('/api/recipes', methods=['GET', 'POST'])
def api_recipes():
    if request.method == 'GET':
        recipes = get_all_recipes()
        return jsonify([dict(recipe) for recipe in recipes])
    elif request.method == 'POST':
        recipe = request.json
        recipe_id = insert_recipe(recipe)
        return jsonify({"id": recipe_id, "status": "success"})

@app.route('/api/recipes/<int:recipe_id>', methods=['GET', 'PUT', 'DELETE'])
def api_recipe(recipe_id):
    if request.method == 'GET':
        recipe = get_recipe(recipe_id)
        return jsonify(dict(recipe))
    elif request.method == 'PUT':
        recipe = request.json
        update_recipe(recipe_id, recipe)  # Make sure update_recipe accepts two arguments
        return jsonify({"status": "success"})
    elif request.method == 'DELETE':
        delete_recipe(recipe_id)
        return jsonify({"status": "success"})

def init_app(app, socketio, motor_controller):
    global app_instance, socketio_instance, motor_controller_instance
    app_instance = app
    socketio_instance = socketio
    motor_controller_instance = motor_controller

def cleanup():
    global cleanup_done, motor_controller
    if not cleanup_done:
        cleanup_done = True
        motor_controller.cleanup()
        logger.info("Application cleanup completed")

# Register the cleanup function to be called on exit
atexit.register(cleanup)

# Register the cleanup function for SIGTERM and SIGINT signals
def signal_handler(signum, frame):
    global is_shutting_down
    is_shutting_down = True
    cleanup()

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

@socketio.on('connect')
def handle_connect():
    logger.info("Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    logger.info("Client disconnected")

# Add this new function
def initial_homing():
    global motor_controller
    logger.info("Performing initial homing sequence")
    motor_controller.home()
    motor_controller.set_homed(True)

if __name__ == '__main__':
    logger.info(f"Starting Flask application with integrated motor control (PID: {os.getpid()})")
    try:
        if not os.environ.get('WERKZEUG_RUN_MAIN'):
            initial_homing()  # Perform homing only in the main process
        socketio.run(app, host='0.0.0.0', port=6900, debug=True)
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        cleanup()
else:
    logger.info(f"routes.py module imported (PID: {os.getpid()})")
