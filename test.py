#!/usr/bin/python3
import exif_rename
import unittest
from datetime import datetime
from pathlib import Path

datadir = Path(__file__).parent / 'test_data'

class TimestampTest(unittest.TestCase):
    def test_sammy_awake(self):
        self.assertEqual(
            datetime(2019, 4, 17, 17, 45, 37),
            exif_rename.get_exif_timestamp(str(datadir / 'sammy_awake.jpg')))

    def test_sammy_sleepy(self):
        self.assertEqual(
            datetime(2019, 2, 7, 15, 37, 10),
            exif_rename.get_exif_timestamp(str(datadir / 'sammy_sleepy.jpg')))

    def test_no_exif(self):
        self.assertRaises(exif_rename.TimestampReadException,
                          exif_rename.get_exif_timestamp,
                          str(datadir / '20191027_121401.jpg'))

    def test_no_image(self):
        self.assertRaises(exif_rename.TimestampReadException,
                          exif_rename.get_exif_timestamp,
                          __file__)

if __name__ == '__main__':
    unittest.main(verbosity=2)
