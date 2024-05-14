#  Copyright (c) 2024. Matthew Naruzny.

import sys
import unittest

sys.path.append("../src")
from ws_sim868.modemUnit import ModemUnit


class TestSystem(unittest.TestCase):

    m = None

    @classmethod
    def setUpClass(cls):

        # Start Modem
        cls.m = ModemUnit()
        cls.m.apn_config('super', '', '')
        cls.m.network_start()


    def test_http_get(self):
        res = self.m.http_get("http://httpstat.us/200")
        self.assertEqual(res['http_status'], 200)
        print("Done!")

    def test_http_post(self):
        res = self.m.http_post("http://httpstat.us/200")
        self.assertEqual(res['http_status'], 200)
        print("Done!")


if __name__ == '__main__':
    unittest.main()
