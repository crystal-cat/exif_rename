#!/usr/bin/python3
import exif_rename
import hashlib
import shutil
import unittest
from collections import namedtuple
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

datadir = Path(__file__).parent / 'test_data'
args_mock = namedtuple(
    'args_mock',
    [
        'files',
        'date_sources',
        'source_name_format',
        'mv_cmd',
        'pause_on_error',
        'date_format',
        'simulate'
    ],
    defaults=[
        [],
        ['exif'],
        '%Y%m%d_%H%M%S.jpg',
        None,
        None,
        '%Y%m%d_%H%M%S',
        False
    ]
)


class TimestampTest(unittest.TestCase):
    def setUp(self):
        self.args = args_mock()

    def test_sammy_awake(self):
        self.assertEqual(
            ('exif', datetime(2019, 4, 17, 17, 45, 37)),
            exif_rename.get_timestamp(datadir / 'sammy_awake.jpg', self.args))

    def test_sammy_sleepy(self):
        self.assertEqual(
            ('exif', datetime(2019, 2, 7, 15, 37, 10)),
            exif_rename.get_timestamp(datadir / 'sammy_sleepy.jpg', self.args))

    def test_no_exif(self):
        args = self.args._replace(date_sources=['exif', 'file-name'])
        self.assertEqual(
            ('file-name', datetime(2019, 10, 27, 12, 14, 1)),
            exif_rename.get_timestamp(datadir / '20191027_121401.jpg',
                                      args))

    def test_unparsable_filename(self):
        args = self.args._replace(date_sources=['file-name'])
        self.assertRaises(exif_rename.TimestampReadException,
                          exif_rename.get_timestamp,
                          datadir / 'sammy_sleepy.jpg',
                          args)

    def test_fallthrough_ctime(self):
        args = self.args._replace(date_sources=['file-name', 'file-created'])
        sleepy = datadir / 'sammy_sleepy.jpg'
        self.assertEqual(
            ('file-created', datetime.fromtimestamp(sleepy.stat().st_ctime)),
            exif_rename.get_timestamp(sleepy, args))

    def test_fallthrough_mtime(self):
        args = self.args._replace(date_sources=['file-name', 'file-modified'])
        sleepy = datadir / 'sammy_sleepy.jpg'
        self.assertEqual(
            ('file-modified', datetime.fromtimestamp(sleepy.stat().st_mtime)),
            exif_rename.get_timestamp(sleepy, args))

    def test_no_image(self):
        self.assertRaises(exif_rename.TimestampReadException,
                          exif_rename.get_exif_timestamp,
                          __file__)

    def test_unknown_source(self):
        args = self.args._replace(date_sources=['meow'])
        self.assertRaises(ValueError,
                          exif_rename.get_timestamp,
                          datadir / 'sammy_sleepy.jpg',
                          args)


class MoveTest(unittest.TestCase):
    # The mapping contains expected (possible) file names for each
    # input file
    mapping = {
        datadir / 'sammy_awake.jpg': ['20190417_174537.jpg',
                                      '20190417_174537-1.jpg'],
        datadir / 'sammy_awake_commented.jpg': ['20190417_174537.jpg',
                                                '20190417_174537-1.jpg'],
        datadir / 'sammy_sleepy.jpg': ['20190207_153710.jpg'],
        datadir / '20191027_121401.jpg': ['20191027_121401.jpg']
    }

    @staticmethod
    def hash_files(mapping):
        """Assuming the keys in 'mapping' are Path objects, return a new dict
        with the SHA1 hashes of the file contents as keys and the same
        values.
        """
        hashes = dict()
        for file, names in mapping.items():
            sha = hashlib.sha1()
            sha.update(file.read_bytes())
            hashes[sha.hexdigest()] = names
        return hashes

    def check_move(self):
        found = 0
        for f in Path(self.tempdir.name).iterdir():
            sha = hashlib.sha1()
            sha.update(f.read_bytes())
            fhash = sha.hexdigest()
            if fhash in self.hashes:
                self.assertTrue(f.name in self.hashes[fhash])
                found += 1
        self.assertEqual(found, len(self.hashes))

    @classmethod
    def setUpClass(cls):
        # The hashes are used to identify files after moving
        cls.hashes = cls.hash_files(cls.mapping)

    def setUp(self):
        self.tempdir = TemporaryDirectory()
        shutil.copytree(datadir, self.tempdir.name, dirs_exist_ok=True)
        filelist = [x for x in Path(self.tempdir.name).iterdir()
                    if x.suffix == '.jpg']
        self.args = args_mock(filelist, ['exif', 'file-name'])

    def tearDown(self):
        self.tempdir.cleanup()

    def test_main(self):
        exif_rename.main(self.args)
        self.check_move()

    def test_main_no_sources(self):
        # this way there will be no valid timestamp source for
        # 20191027_121401.jpg
        args = self.args._replace(date_sources=['exif'])
        exif_rename.main(args)
        self.check_move()


if __name__ == '__main__':
    unittest.main(verbosity=2)
