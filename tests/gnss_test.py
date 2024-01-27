#  Copyright (c) 2024. Matthew Naruzny.
import sys

sys.path.append("../src")

from ws_sim868.modemUnit import ModemUnit
import time

if __name__ == "__main__":
    m = ModemUnit()
    m.gnss_stop()
    time.sleep(2)
    m.gnss_start()

    while True:
        time.sleep(3)
        print(m.get_gnss_loc())

