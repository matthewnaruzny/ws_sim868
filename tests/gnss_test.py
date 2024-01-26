#  Copyright (c) 2024. Matthew Naruzny.
import sys

sys.path.append("../src")

import ws_sim868
from ws_sim868.modemUnit import ModemUnit
import time

if __name__ == "__main__":
    m = ModemUnit()
    m.gnss_start()

    while True:
        time.sleep(0.5)
