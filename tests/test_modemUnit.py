#  Copyright (c) 2023. Matthew Naruzny.

from unittest import TestCase
from ws_sim868.modemUnit import ModemUnit


class TestModemUnit(TestCase):

    def test_startup(self):
        self.modem = ModemUnit()

