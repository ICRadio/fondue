# hardware.py
import RPi.GPIO as GPIO
import time
import threading

class GPIOController:
    def __init__(self, switch_callback, primary_source="cam1", secondary_source="cam2",
                 button_pin=17, led_pin=27):
        self.primary_source = primary_source
        self.secondary_source = secondary_source
        self.current = primary_source
        self.switch_callback = switch_callback
        self.button_pin = button_pin
        self.led_pin = led_pin

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.button_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(self.led_pin, GPIO.OUT)

        self.running = True
        self.thread = threading.Thread(target=self._listen_button, daemon=True)
        self.thread.start()

    def _listen_button(self):
        while self.running:
            if GPIO.input(self.button_pin) == GPIO.HIGH:
                time.sleep(0.05)  # debounce
                self.toggle_source()
                while GPIO.input(self.button_pin) == GPIO.HIGH:
                    time.sleep(0.1)  # wait for release
            time.sleep(0.05)

    def toggle_source(self):
        self.current = self.secondary_source if self.current == self.primary_source else self.primary_source
        self.switch_callback(self.current)
        self._update_led()

    def _update_led(self):
        if self.current == self.primary_source:
            GPIO.output(self.led_pin, GPIO.HIGH)
        else:
            GPIO.output(self.led_pin, GPIO.LOW)

    def stop(self):
        self.running = False
        GPIO.cleanup()
