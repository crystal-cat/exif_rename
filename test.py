#!/usr/bin/python3
import exif_rename
import unittest
from collections import namedtuple
from datetime import datetime
from pathlib import Path

datadir = Path(__file__).parent / 'test_data'
args_mock = namedtuple('args_mock', ['date_sources', 'source_name_format'])


class TimestampTest(unittest.TestCase):
    def setUp(self):
        self.args = args_mock(['exif'], '%Y%m%d_%H%M%S.jpg')

    def test_sammy_awake(self):
        self.assertEqual(
            ('exif', datetime(2019, 4, 17, 17, 45, 37)),
            exif_rename.get_timestamp(datadir / 'sammy_awake.jpg', self.args))

    def test_sammy_sleepy(self):
        self.assertEqual(
            ('exif', datetime(2019, 2, 7, 15, 37, 10)),
            exif_rename.get_timestamp(datadir / 'sammy_sleepy.jpg', self.args))

    def test_no_exif(self):
        self.args.date_sources.append('file-name')
        self.assertEqual(
            ('file-name', datetime(2019, 10, 27, 12, 14, 1)),
            exif_rename.get_timestamp(datadir / '20191027_121401.jpg',
                                      self.args))

    def test_unparsable_filename(self):
        self.args.date_sources[0] = 'file-name'
        self.assertRaises(exif_rename.TimestampReadException,
                          exif_rename.get_timestamp,
                          datadir / 'sammy_sleepy.jpg',
                          self.args)

    def test_fallthrough_ctime(self):
        self.args.date_sources[0:1] = ['file-name', 'file-created']
        sleepy = datadir / 'sammy_sleepy.jpg'
        self.assertEqual(
            ('file-created', datetime.fromtimestamp(sleepy.stat().st_ctime)),
            exif_rename.get_timestamp(sleepy, self.args))

    def test_fallthrough_mtime(self):
        self.args.date_sources[0:1] = ['file-name', 'file-modified']
        sleepy = datadir / 'sammy_sleepy.jpg'
        self.assertEqual(
            ('file-modified', datetime.fromtimestamp(sleepy.stat().st_mtime)),
            exif_rename.get_timestamp(sleepy, self.args))

    def test_no_image(self):
        self.assertRaises(exif_rename.TimestampReadException,
                          exif_rename.get_exif_timestamp,
                          __file__)

    def test_unknown_source(self):
        self.args.date_sources[0] = 'meow'
        self.assertRaises(ValueError,
                          exif_rename.get_timestamp,
                          datadir / 'sammy_sleepy.jpg',
                          self.args)


if __name__ == '__main__':
    unittest.main(verbosity=2)
