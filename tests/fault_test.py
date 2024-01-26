#  Copyright (c) 2024. Matthew Naruzny.
import logging
import sys
import RPi.GPIO as GPIO

sys.path.append("../src")

import ws_sim868
from ws_sim868.modemUnit import ModemUnit
import time

if __name__ == "__main__":
    apn_config = ws_sim868.modemUnit.APNConfig('super', '', '')
    m = ModemUnit(apn_config=apn_config)

    start_time = time.time()

    triggered_restart = False
    while True:
        if time.time() - start_time > 10 and not triggered_restart:
            triggered_restart = True
            logging.info("RESTART")
            GPIO.setmode(GPIO.BOARD)
            GPIO.setup(7, GPIO.OUT)
            while True:
                GPIO.output(7, GPIO.LOW)
                time.sleep(4)
                GPIO.output(7, GPIO.HIGH)
                break
            GPIO.cleanup()

        time.sleep(0.5)
