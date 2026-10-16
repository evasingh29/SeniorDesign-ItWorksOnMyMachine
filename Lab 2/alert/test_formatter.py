from datetime import datetime
import unittest
from formatter import format_alert


class FormatterTests(unittest.TestCase):
    def test_clock_and_calendar(self):
        for hour, expected in [(0, '12:05 AM'), (9, '09:05 AM'),
                               (12, '12:05 PM'), (23, '11:05 PM')]:
            with self.subTest(hour=hour):
                self.assertEqual(format_alert(datetime(2026, 1, 2, hour, 5)),
                                 f'Critical Safety Event at {expected} on 01/02/2026')

    def test_leap_day(self):
        self.assertEqual(format_alert(datetime(2028, 2, 29, 15, 42)),
                         'Critical Safety Event at 03:42 PM on 02/29/2028')
