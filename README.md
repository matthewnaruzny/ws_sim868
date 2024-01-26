# ws_sim868
## Interface module for the Waveshare GSM/GPRS/GNSS Pi Hat

## Features
- HTTP GET and POST requests
- Automatically start Modem if turned off

## Overview

## Examples:
### HTTP Get Request

```python
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
```

## Planned Enhancements
- Receive GNSS Location