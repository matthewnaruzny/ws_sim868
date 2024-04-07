#  Copyright (c) 2024. Matthew Naruzny.

import sys
import unittest

sys.path.append("../src")
from ws_sim868.modemUnit import ModemUnit


class TestSystem(unittest.TestCase):

    def setUp(self):

        # Start Modem
        self.m = ModemUnit()
        self.m.apn_config('super', '', '')
        self.m.network_start()


    def test_http_get(self):
        res = self.m.http_get("http://httpstat.us/200")
        self.assertEqual(res['http_status'], 200)

    def test_http_post(self):
        res = self.m.http_post("http://httpstat.us/200")
        self.assertEqual(res['http_status'], 200)


if __name__ == '__main__':
    unittest.main()
