import RPi.GPIO as GPIO
import threading
import time
import logging

logger = logging.getLogger(__name__)

class MotorController:
    def __init__(self, socketio):
        self.speed = 50  # Set default speed to 50%
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

        # Add GPIO pins for pumps
        self.whiskey_pump_pin = 23
        self.syrup_pump_pin = 24
        self.bitters_pump_pin = 25

        self.limit_switch_thread = None
        self.setup_gpio()

        # Motor configuration
        self.steps_per_revolution = 200
        self.microstep = 2

        self.pour_positions = {
            'whiskey': 1750,
            'syrup': 2500,
            'bitters': 3250
        }

        self.acceleration = 3000  # Increase acceleration for faster ramp-up
        self.min_speed = 200  # Increase minimum speed to avoid squealing
        self.max_speed = 1500  # Maximum speed in steps/second
        self.current_speed = self.min_speed
        self.target_speed = self.min_speed

        # Conversion factors (seconds per oz)
        self.whiskey_conversion = 1.3  # seconds per oz
        self.syrup_conversion = 2    # seconds per oz
        self.bitters_conversion = 1  # seconds per dash

        self.is_shutting_down = False

        self.load_homing_state()  # Add this line

    def setup_gpio(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # Setup motor control pins
        GPIO.setup(self.enable_pin, GPIO.OUT)
        GPIO.setup(self.direction_pin, GPIO.OUT)
        GPIO.setup(self.step_pin, GPIO.OUT)
        
        # Initialize enable pin to HIGH to disable the motor
        GPIO.output(self.enable_pin, GPIO.HIGH)
        GPIO.output(self.direction_pin, GPIO.LOW)
        GPIO.output(self.step_pin, GPIO.LOW)
        
        GPIO.setup(self.limit_switch_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # Setup and initialize pump GPIO pins
        for pin in [self.whiskey_pump_pin, self.syrup_pump_pin, self.bitters_pump_pin]:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

        logger.info("GPIO setup completed successfully, all pump pins initialized to LOW")

    def set_speed(self, speed):
        self.speed = min(max(speed, 0), 100)
        logger.info(f"Speed set to {self.speed}%")
        self.target_speed = self.min_speed + (self.speed / 100) * (self.max_speed - self.min_speed)

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
        while self.running and not self.limit_switch_triggered:
            if self.speed > 0:
                delay = 1 / (self.speed * self.max_speed / 100)  # Convert speed percentage to delay
                GPIO.output(self.step_pin, GPIO.HIGH)
                time.sleep(delay / 2)
                GPIO.output(self.step_pin, GPIO.LOW)
                time.sleep(delay / 2)
                self.position += 1 if GPIO.input(self.direction_pin) == GPIO.HIGH else -1

        self.running = False
        self._power_off_motor()
        self.socketio.emit('motor_status', {'status': 'stopped', 'position': self.position})

    def _accelerate(self, target_speed, current_speed, acceleration):
        if current_speed < target_speed:
            return min(current_speed + acceleration, target_speed)
        else:
            return max(current_speed - acceleration, target_speed)

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
        while self.running and not self.limit_switch_triggered:
            if self.speed > 0:
                delay = (60 / (self.speed * self.steps_per_revolution * self.microstep)) / 2
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
        if self.is_shutting_down:
            logger.info("Homing aborted: system is shutting down")
            return
        
        if not self.running and not self.limit_switch_triggered:
            self.running = True
            GPIO.output(self.enable_pin, GPIO.LOW)  # Enable the motor
            GPIO.output(self.direction_pin, GPIO.LOW)  # Set direction towards limit switch
            self.thread = threading.Thread(target=self._home_sequence)
            self.thread.start()
            self.thread.join()  # Wait for homing to complete
            self.save_homing_state()  # Add this line

    def _home_sequence(self):
        homing_speed = 50  # Adjust this value to set homing speed
        back_off_steps = 50  # Number of steps to back off after hitting the limit switch

        # Move towards limit switch
        while self.running and not self.limit_switch_triggered:
            delay = (60 / (homing_speed * self.steps_per_revolution * self.microstep)) / 2
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
        self.is_shutting_down = True
        if not self.cleanup_done:
            self.cleanup_done = True
            self.stop()
            if self.limit_switch_thread and self.limit_switch_thread.is_alive():
                self.limit_switch_thread.join(timeout=1)
            # Turn off all pumps
            GPIO.output(self.whiskey_pump_pin, GPIO.LOW)
            GPIO.output(self.syrup_pump_pin, GPIO.LOW)
            GPIO.output(self.bitters_pump_pin, GPIO.LOW)
            # Ensure all used pins are set to LOW
            GPIO.output(self.enable_pin, GPIO.LOW)
            GPIO.output(self.direction_pin, GPIO.LOW)
            GPIO.output(self.step_pin, GPIO.LOW)
            # Use GPIO.cleanup() without arguments to clean up all pins
            GPIO.cleanup()
            logger.info("Motor controller and pump cleanup completed")

    def _move_steps(self, steps, speed):
        direction = GPIO.HIGH if steps > 0 else GPIO.LOW
        GPIO.output(self.direction_pin, direction)

        remaining_steps = abs(steps)
        target_speed = self.min_speed + (speed / 100) * (self.max_speed - self.min_speed)
        
        # Reset acceleration state
        self.current_speed = self.min_speed

        # Calculate acceleration and deceleration distances
        acceleration_distance = int((target_speed**2 - self.min_speed**2) / (2 * self.acceleration))
        deceleration_distance = acceleration_distance

        # Adjust for short movements
        if remaining_steps < 2 * acceleration_distance:
            acceleration_distance = remaining_steps // 2
            deceleration_distance = remaining_steps - acceleration_distance
            target_speed = (2 * self.acceleration * acceleration_distance + self.min_speed**2)**0.5

        while remaining_steps > 0 and self.running and not self.limit_switch_triggered:
            if remaining_steps > deceleration_distance:
                # Accelerate or maintain speed
                self.current_speed = min(self.current_speed + self.acceleration * 0.001, target_speed)
            else:
                # Decelerate
                deceleration_progress = 1 - (remaining_steps / deceleration_distance)
                self.current_speed = max(
                    self.min_speed,
                    target_speed - (target_speed - self.min_speed) * deceleration_progress
                )

            if self.current_speed > 0:
                delay = 1 / self.current_speed
                GPIO.output(self.step_pin, GPIO.HIGH)
                time.sleep(delay / 2)
                GPIO.output(self.step_pin, GPIO.LOW)
                time.sleep(delay / 2)
                self.position += 1 if direction == GPIO.HIGH else -1
                remaining_steps -= 1

        self.running = False
        self._power_off_motor()
        self.socketio.emit('motor_status', {'status': 'stopped', 'position': self.position})

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
        target_speed = self.speed * self.max_speed / 100
        
        self.thread = threading.Thread(target=self._move_steps, args=(steps_to_move, self.speed))
        self.thread.start()

    def pour(self, ingredient, volume):
        logger.info(f"Starting pour sequence for {ingredient} (volume: {volume})")
        if not self._is_homed:
            logger.info("Motor not homed, initiating homing sequence")
            self.home()
            # Wait for homing to complete
            while not self._is_homed:
                time.sleep(0.1)
        
        logger.info("Motor homed, setting speed to 100%")
        self.set_speed(100)  # Set speed to 100% for pouring
        
        if ingredient not in self.pour_positions:
            logger.error(f"Invalid ingredient: {ingredient}")
            return {"status": "error", "message": "Invalid ingredient"}

        target_position = self.pour_positions[ingredient]
        logger.info(f"Moving to position {target_position} for {ingredient}")
        
        self.go_to_position(target_position)
        
        # Wait for the motor to reach the position
        while self.running:
            time.sleep(0.1)

        logger.info(f"Reached position for {ingredient}, activating pump")
        
        # Activate the appropriate pump
        pump_pin = self._get_pump_pin(ingredient)
        if pump_pin:
            pour_time = self.calculate_pour_time(ingredient, volume)
            logger.info(f"Pouring {ingredient} for {pour_time} seconds")
            GPIO.output(pump_pin, GPIO.HIGH)
            time.sleep(pour_time)
            GPIO.output(pump_pin, GPIO.LOW)
        else:
            logger.error(f"No pump associated with ingredient: {ingredient}")
            return {"status": "error", "message": f"No pump for {ingredient}"}

        logger.info(f"Pour sequence completed for {ingredient}")
        
        # Move to position 4900 after pouring
        logger.info("Moving to position 4900")
        self.go_to_position(4900)
        
        # Wait for the motor to reach the position
        while self.running:
            time.sleep(0.1)
        
        logger.info("Reached position 4900")
        return {"status": "success", "message": f"Poured {volume} of {ingredient} and moved to position 4900"}

    def _get_pump_pin(self, ingredient):
        if ingredient == 'whiskey':
            return self.whiskey_pump_pin
        elif ingredient == 'syrup':
            return self.syrup_pump_pin
        elif ingredient == 'bitters':
            return self.bitters_pump_pin
        else:
            return None

    def activate(self):
        self.is_activated = True
        logger.info("System activated")
        self.socketio.emit('motor_status', {'status': 'activated'})

    def deactivate(self):
        self.is_activated = False
        self.stop()
        logger.info("System deactivated")
        self.socketio.emit('motor_status', {'status': 'deactivated'})

    def calculate_pour_time(self, ingredient, volume):
        if ingredient == 'whiskey':
            return volume * self.whiskey_conversion
        elif ingredient == 'syrup':
            return volume * self.syrup_conversion
        elif ingredient == 'bitters':
            return volume * self.bitters_conversion
        else:
            return 0

    def save_homing_state(self):
        with open('/tmp/motor_homed_state.txt', 'w') as f:
            f.write('1' if self._is_homed else '0')
        logger.info(f"Saved homing state: {self._is_homed}")

    def load_homing_state(self):
        try:
            with open('/tmp/motor_homed_state.txt', 'r') as f:
                state = f.read().strip()
                self._is_homed = (state == '1')
            logger.info(f"Loaded homing state: {self._is_homed}")
        except FileNotFoundError:
            self._is_homed = False
            logger.info("No saved homing state found, assuming not homed")

    def set_homed(self, state):
        self._is_homed = state
        self.save_homing_state()