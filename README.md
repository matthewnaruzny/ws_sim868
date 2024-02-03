# ws_sim868
## Interface module for the Waveshare GSM/GPRS/GNSS Pi Hat

![PyPI - License](https://img.shields.io/pypi/l/ws-sim868)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/matthewnaruzny/ws_sim868/python-publish.yml)
![PyPI - Version](https://img.shields.io/pypi/v/ws_sim868)

## Features
- HTTP GET and POST requests
- Automatically start Modem if turned off
- Receive GNSS Location

## Instalation
```
pip install ws-sim868
```

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

### Get Location
```python
from ws_sim868.modemUnit import ModemUnit
import time

if __name__ == "__main__":
    m = ModemUnit()
    m.gnss_start()

    while True:
        time.sleep(3)
        print(m.get_gnss_loc())
```
