# Maria Duhamel - 07/25/2025
# Introduced a moving average using collections.deque to smooth out temperature readings.
# Replaced all calls to the original getFahrenheit() with the new get_smoothed_fahrenheit() function.
# Updated logic in updateLights(), manageMyDisplay(), and setupSerialOutput() to use the smoothed temperature.

# === Added: For moving average smoothing ===
from collections import deque
import json
import logging
import sqlite3
from time import sleep
from datetime import datetime
from statemachine import StateMachine, State
import board
import adafruit_ahtx0
import digitalio
import adafruit_character_lcd.character_lcd as characterlcd
import serial
from gpiozero import Button, PWMLED
from threading import Thread
from math import floor

# === Added: Load configuration from external JSON file ===
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

# === Added: Set up structured logging ===
logging.basicConfig(
    filename='thermostat.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# === Added: Set up SQLite database for logging temperature data ===
conn = sqlite3.connect('temperature_log.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS temperature_readings (
        timestamp TEXT,
        state TEXT,
        temperature INTEGER,
        set_point INTEGER
    )
''')
conn.commit()

# === UPDATED: Initialize I2C and sensor with error handling ===
i2c = board.I2C()
try:
    thSensor = adafruit_ahtx0.AHTx0(i2c)
except Exception as e:
    logging.error(f"Failed to initialize temperature sensor: {e}")
    raise

# === UPDATED: Initialize UART with error handling ===
try:
    ser = serial.Serial(
        port=config["serial_port"],
        baudrate=config["baudrate"],
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS,
        timeout=1
    )
except Exception as e:
    logging.error(f"Failed to initialize serial port: {e}")
    raise

# === UPDATED: Use config values for GPIO pins ===
redLight = PWMLED(config["red_led_pin"])
blueLight = PWMLED(config["blue_led_pin"])

# === LCD Display class ===
class ManagedDisplay():
    def __init__(self):
        self.lcd_rs = digitalio.DigitalInOut(board.D17)
        self.lcd_en = digitalio.DigitalInOut(board.D27)
        self.lcd_d4 = digitalio.DigitalInOut(board.D5)
        self.lcd_d5 = digitalio.DigitalInOut(board.D6)
        self.lcd_d6 = digitalio.DigitalInOut(board.D13)
        self.lcd_d7 = digitalio.DigitalInOut(board.D26)
        self.lcd_columns = 16
        self.lcd_rows = 2
        self.lcd = characterlcd.Character_LCD_Mono(
            self.lcd_rs, self.lcd_en, self.lcd_d4, self.lcd_d5,
            self.lcd_d6, self.lcd_d7, self.lcd_columns, self.lcd_rows
        )
        self.lcd.clear()

    def cleanupDisplay(self):
        self.lcd.clear()
        for pin in [self.lcd_rs, self.lcd_en, self.lcd_d4, self.lcd_d5, self.lcd_d6, self.lcd_d7]:
            pin.deinit()

    def updateScreen(self, message):
        try:
            self.lcd.clear()
            self.lcd.message = message
        except Exception as e:
            logging.error(f"LCD update failed: {e}")

screen = ManagedDisplay()

# === Added: Initialize deque for temperature smoothing ===
temp_history = deque(maxlen=5)

# === Added: Smoothed temperature reading function ===
def get_smoothed_fahrenheit():
    try:
        raw_temp = ((9/5) * thSensor.temperature) + 32
        temp_history.append(raw_temp)
        smoothed_temp = sum(temp_history) / len(temp_history)
        return smoothed_temp
    except Exception as e:
        logging.error(f"Temperature read failed: {e}")
        return 0

# === Thermostat state machine ===
class TemperatureMachine(StateMachine):
    off = State(initial=True)
    heat = State()
    cool = State()

    setPoint = config["default_set_point"]

    cycle = (off.to(heat) | heat.to(cool) | cool.to(off))

    def on_enter_heat(self):
        redLight.on()
        blueLight.off()
        logging.info("State changed to HEAT")

    def on_exit_heat(self):
        redLight.off()

    def on_enter_cool(self):
        blueLight.on()
        redLight.off()
        logging.info("State changed to COOL")

    def on_exit_cool(self):
        blueLight.off()

    def on_enter_off(self):
        redLight.off()
        blueLight.off()
        logging.info("State changed to OFF")

    def processTempStateButton(self):
        logging.info("Cycling thermostat state")
        self.cycle()

    def processTempIncButton(self):
        self.setPoint += 1
        logging.info(f"Increased set point to {self.setPoint}")
        self.updateLights()

    def processTempDecButton(self):
        self.setPoint -= 1
        logging.info(f"Decreased set point to {self.setPoint}")
        self.updateLights()

    def updateLights(self):
        try:
            temp = floor(get_smoothed_fahrenheit())  # === UPDATED: Use smoothed temperature ===
        except Exception as e:
            logging.error(f"Temperature read failed: {e}")
            return

        redLight.off()
        blueLight.off()

        if self.current_state == self.heat:
            redLight.pulse() if temp < self.setPoint else redLight.on()
        elif self.current_state == self.cool:
            blueLight.pulse() if temp > self.setPoint else blueLight.on()

        logging.debug(f"State: {self.current_state.id}, Temp: {temp}, SetPoint: {self.setPoint}")

    def run(self):
        Thread(target=self.manageMyDisplay).start()

    def setupSerialOutput(self):
        try:
            return f"{self.current_state.id},{floor(get_smoothed_fahrenheit())},{self.setPoint}"  # === UPDATED ===
        except Exception as e:
            logging.error(f"Serial output failed: {e}")
            return "error,error,error"

    endDisplay = False

    def manageMyDisplay(self):
        counter = 1
        altCounter = 1

        while not self.endDisplay:
            try:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                temp = floor(get_smoothed_fahrenheit())  # === UPDATED ===
                lcd_line_1 = current_time
                lcd_line_2 = f"Temp: {temp}°F" if altCounter < 6 else f"{self.current_state.id} {self.setPoint}°F"
                altCounter = 1 if altCounter >= 10 else altCounter + 1

                screen.updateScreen(f"{lcd_line_1}\n{lcd_line_2}")

                if (counter % 30) == 0:
                    output = self.setupSerialOutput()
                    ser.write(output.encode())
                    cursor.execute("INSERT INTO temperature_readings VALUES (?, ?, ?, ?)",
                                   (current_time, self.current_state.id, temp, self.setPoint))
                    conn.commit()
                    counter = 1
                else:
                    counter += 1

                sleep(1)
            except Exception as e:
                logging.error(f"Display loop error: {e}")

        screen.cleanupDisplay()

# === Initialize state machine and buttons ===
tsm = TemperatureMachine()
tsm.run()

greenButton = Button(config["state_button_pin"])
greenButton.when_pressed = tsm.processTempStateButton

redButton = Button(config["increase_button_pin"])
redButton.when_pressed = tsm.processTempIncButton

blueButton = Button(config["decrease_button_pin"])
blueButton.when_pressed = tsm.processTempDecButton

# === Main loop ===
repeat = True
while repeat:
    try:
        sleep(30)
    except KeyboardInterrupt:
        logging.info("Shutting down system...")
        repeat = False
        tsm.endDisplay = True
        sleep(1)
        conn.close()
