#  Copyright (c) 2023-2024. Matthew Naruzny.
import sys

sys.path.append("../src")

from ws_sim868.modemUnit import ModemUnit
import time

if __name__ == "__main__":
    m = ModemUnit()
    m.apn_config('super', '', '')
    m.network_start()
    res = m.http_get("http://httpstat.us/200")
    print("DONE 1")
    print(res)
    res2 = m.http_post("http://httpstat.us/200")
    print("DONE 2")
    print(res2)

    while True:
        time.sleep(0.5)
