#  Copyright (c) 2023-2024. Matthew Naruzny.
import sys

sys.path.append("../src")

from ws_sim868.modemUnit import ModemUnit
import time

if __name__ == "__main__":
    m = ModemUnit()
    m.apn_config('super', '', '')
    m.network_start()
    res = m.http_get("http://example.com")
    print(res)

    while True:
        time.sleep(0.5)
