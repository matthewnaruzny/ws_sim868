#  Copyright (c) 2024. Matthew Naruzny.

import sys

sys.path.append("../src")

from ws_sim868.modemUnit import ModemUnit
import time

if __name__ == "__main__":
    m = ModemUnit()
    print(m.get_imei())

    while True:
        time.sleep(0.5)
