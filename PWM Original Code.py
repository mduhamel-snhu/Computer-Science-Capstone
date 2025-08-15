# Maria Duhamel - 03/14/2025 - Milestone1.py - This is the Python code template that will be used
# for Milestone 1, demonstrating the use of PWM to fade an LED in and out. 
# This code works with the test circuit that was built for Assignment 1-4.
# Load the GPIO interface from the Raspberry Pi Python Module
# The GPIO interface will be available through the GPIO object
import RPi.GPIO as GPIO

# Load the time module so that we can utilize the sleep method to 
# inject a pause into our operation
import time

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(18, GPIO.OUT)

# Configure a PWM instance on GPIO line 18, with a frequency of 60Hz
pwm18 = GPIO.PWM(18, 60)

# Start the PWM instance on GPIO line 18 with 0% duty cycle
pwm18.start(50)

# Configure the loop variable so that we can exit cleanly when the user
# issues a keyboard interrupt (CTRL-C)
#
repeat = True
while repeat:
    try:
        # Loop from 0 to 100 in increments of 5, and update the dutyCycle
        # accordingly, pausing 1/10th of a second between each update

	for duty_cycle in range(0, 101, 5):
   	 pwm18.ChangeDutyCycle(duty_cycle)
  	  time.sleep(0.1)

        # Loop from 100 to 0 in increments of -5, and update the dutyCycle
        # accordingly, pausing 1/10th of a second between each update

	for duty_cycle in range(100, -1, -5):
  	  pwm18.ChangeDutyCycle(duty_cycle)
  	  time.sleep(0.1)

    except KeyboardInterrupt:
        # Stop the PWM instance on GPIO line 18
        print('Stopping PWM and Cleaning Up')
        pwm18.stop()
        GPIO.cleanup()
        repeat = False
# Cleanup the GPIO pins used in this application and exit
GPIO.cleanup()
