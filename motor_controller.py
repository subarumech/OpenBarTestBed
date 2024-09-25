import RPi.GPIO as GPIO
import threading
import time
import logging

logger = logging.getLogger(__name__)

class MotorController:
    def __init__(self, socketio):
        self.speed = 0
        self.running = False
        self.thread = None
        self.cleanup_done = False
        self.limit_switch_triggered = False
        self.socketio = socketio
        self.position = 0
        self._is_homed = False
        self.is_activated = False
        
        # Open-loop motor pins
        self.enable_pin = 17
        self.direction_pin = 27
        self.step_pin = 22
        
        self.limit_switch_pin = 5

        self.limit_switch_thread = None
        self.setup_gpio()

    def setup_gpio(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        GPIO.setup(self.enable_pin, GPIO.OUT)
        GPIO.setup(self.direction_pin, GPIO.OUT)
        GPIO.setup(self.step_pin, GPIO.OUT)
        
        # Initialize enable pin to HIGH to disable the motor
        GPIO.output(self.enable_pin, GPIO.HIGH)
        GPIO.output(self.direction_pin, GPIO.LOW)
        GPIO.output(self.step_pin, GPIO.LOW)
        
        GPIO.setup(self.limit_switch_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        logger.info("GPIO setup completed successfully")

    def set_speed(self, speed):
        self.speed = min(max(speed, 0), 100)
        logger.info(f"Speed set to {self.speed}")
        if self.running:
            # If the motor is already running, update the speed immediately
            self._update_motor_speed()

    def _update_motor_speed(self):
        # This method should be called when the motor is running and the speed changes
        # You might need to adjust this based on your specific motor control method
        if self.running:
            # Update the motor speed here
            # This could involve changing PWM duty cycle, step frequency, etc.
            pass

    def start(self):
        if not self.running and not self.limit_switch_triggered:
            self.running = True
            GPIO.output(self.enable_pin, GPIO.LOW)  # Enable the motor
            GPIO.output(self.direction_pin, GPIO.HIGH if self.speed >= 0 else GPIO.LOW)
            self.thread = threading.Thread(target=self._run_motor_free)
            self.thread.start()
            self.limit_switch_thread = threading.Thread(target=self._poll_limit_switch)
            self.limit_switch_thread.start()
            logger.info("Motor started in free mode")
            self.socketio.emit('motor_status', {'status': 'running'})
        elif self.limit_switch_triggered:
            logger.warning("Cannot start motor: Limit switch triggered")
            self.socketio.emit('motor_status', {'status': 'error', 'message': 'Limit switch triggered'})
        else:
            logger.warning("Cannot start motor: Already running")

    def start_direction(self, direction):
        if not self.is_activated:
            logger.warning("Cannot start motor: System not activated")
            self.socketio.emit('motor_status', {'status': 'error', 'message': 'System not activated'})
            return

        if not self.running and not self.limit_switch_triggered:
            self.running = True
            GPIO.output(self.enable_pin, GPIO.LOW)  # Enable the motor
            GPIO.output(self.direction_pin, GPIO.HIGH if direction == 'right' else GPIO.LOW)
            self.thread = threading.Thread(target=self._run_motor_free)
            self.thread.start()
            logger.info(f"Motor running in direction: {direction}")
            self.socketio.emit('motor_status', {'status': 'running', 'direction': direction})
        elif self.limit_switch_triggered:
            logger.warning("Cannot start motor: Limit switch triggered")
            self.socketio.emit('motor_status', {'status': 'error', 'message': 'Limit switch triggered'})

    def _run_motor_free(self):
        steps_per_revolution = 200
        microstep = 2
        while self.running and not self.limit_switch_triggered:
            if self.speed > 0:
                delay = (60 / (self.speed * steps_per_revolution * microstep)) / 2
                GPIO.output(self.step_pin, GPIO.HIGH)
                time.sleep(delay)
                GPIO.output(self.step_pin, GPIO.LOW)
                time.sleep(delay)
                self.position += 1 if GPIO.input(self.direction_pin) == GPIO.HIGH else -1

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join()
        self._power_off_motor()
        self.socketio.emit('motor_status', {'status': 'stopped'})

    def _power_off_motor(self):
        GPIO.output(self.enable_pin, GPIO.HIGH)  # Disable the motor
        GPIO.output(self.step_pin, GPIO.LOW)
        GPIO.output(self.direction_pin, GPIO.LOW)

    def _run_motor(self):
        steps_per_revolution = 200
        microstep = 2
        while self.running and not self.limit_switch_triggered:
            if self.speed > 0:
                delay = (60 / (self.speed * steps_per_revolution * microstep)) / 2
                GPIO.output(self.step_pin, GPIO.HIGH)
                time.sleep(delay)
                GPIO.output(self.step_pin, GPIO.LOW)
                time.sleep(delay)
                self.position += 1 if GPIO.input(self.direction_pin) == GPIO.HIGH else -1

    def _poll_limit_switch(self):
        while self.running:
            if GPIO.input(self.limit_switch_pin) == GPIO.LOW:
                self.limit_switch_triggered = True
                self.running = False
                logger.info("Limit switch triggered, motor stopped")
                self._power_off_motor()
                self.socketio.emit('motor_status', {'status': 'stopped', 'reason': 'limit_switch'})
                break
            time.sleep(0.01)  # Poll every 10ms

    def reset_limit_switch(self):
        self.limit_switch_triggered = False
        logger.info("Limit switch reset")

    def get_limit_switch_status(self):
        return self.limit_switch_triggered

    def home(self):
        if not self.running and not self.limit_switch_triggered:
            self.running = True
            GPIO.output(self.enable_pin, GPIO.LOW)  # Enable the motor
            GPIO.output(self.direction_pin, GPIO.LOW)  # Set direction towards limit switch
            self.thread = threading.Thread(target=self._home_sequence)
            self.thread.start()

    def _home_sequence(self):
        steps_per_revolution = 200
        microstep = 2
        homing_speed = 20  # Adjust this value to set homing speed
        back_off_steps = 100  # Number of steps to back off after hitting the limit switch

        # Move towards limit switch
        while self.running and not self.limit_switch_triggered:
            delay = (60 / (homing_speed * steps_per_revolution * microstep)) / 2
            GPIO.output(self.step_pin, GPIO.HIGH)
            time.sleep(delay)
            GPIO.output(self.step_pin, GPIO.LOW)
            time.sleep(delay)

            if GPIO.input(self.limit_switch_pin) == GPIO.LOW:
                self.limit_switch_triggered = True
                break

        if self.limit_switch_triggered:
            # Back off from limit switch
            GPIO.output(self.direction_pin, GPIO.HIGH)  # Reverse direction
            for _ in range(back_off_steps):
                GPIO.output(self.step_pin, GPIO.HIGH)
                time.sleep(delay)
                GPIO.output(self.step_pin, GPIO.LOW)
                time.sleep(delay)

            self.position = 0
            self._is_homed = True
            self.limit_switch_triggered = False  # Reset the limit switch flag
            logger.info("Homing completed, motor at zero position")
            self.socketio.emit('motor_status', {'status': 'homed'})

        self.running = False
        self._power_off_motor()

    def get_position(self):
        return self.position

    @property
    def is_homed(self):
        return self._is_homed

    def cleanup(self):
        if not self.cleanup_done:
            self.cleanup_done = True
            self.stop()
            if self.limit_switch_thread and self.limit_switch_thread.is_alive():
                self.limit_switch_thread.join()
            GPIO.cleanup()
            logger.info("Motor controller cleanup completed")

    def go_to_position(self, target_position):
        if not self._is_homed:
            logger.warning("Cannot move to position: Motor not homed")
            self.socketio.emit('motor_status', {'status': 'error', 'message': 'Motor not homed'})
            return

        if self.running:
            self.stop()

        self.running = True
        GPIO.output(self.enable_pin, GPIO.LOW)  # Enable the motor
        
        steps_to_move = target_position - self.position
        GPIO.output(self.direction_pin, GPIO.HIGH if steps_to_move > 0 else GPIO.LOW)
        
        self.thread = threading.Thread(target=self._move_to_position, args=(abs(steps_to_move),))
        self.thread.start()

    def _move_to_position(self, steps):
        steps_per_revolution = 200
        microstep = 2
        while steps > 0 and self.running and not self.limit_switch_triggered:
            delay = (60 / (self.speed * steps_per_revolution * microstep)) / 2
            GPIO.output(self.step_pin, GPIO.HIGH)
            time.sleep(delay)
            GPIO.output(self.step_pin, GPIO.LOW)
            time.sleep(delay)
            self.position += 1 if GPIO.input(self.direction_pin) == GPIO.HIGH else -1
            steps -= 1

        self.running = False
        self._power_off_motor()
        self.socketio.emit('motor_status', {'status': 'stopped', 'position': self.position})

    def activate(self):
        self.is_activated = True
        logger.info("System activated")
        self.socketio.emit('motor_status', {'status': 'activated'})

    def deactivate(self):
        self.is_activated = False
        self.stop()
        logger.info("System deactivated")
        self.socketio.emit('motor_status', {'status': 'deactivated'})