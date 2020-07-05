#!/usr/bin/python3
import exif_rename
import hashlib
import shutil
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

datadir = Path(__file__).parent / 'test_data'


def args_mock(**kwargs):
    args = dict({
        'files': [],
        'date_sources': ['exif'],
        'source_name_format': '%Y%m%d_%H%M%S.jpg',
        'mv_cmd': None,
        'pause_on_error': False,
        'date_format': '%Y%m%d_%H%M%S',
        'simulate': False
    })
    args.update(kwargs)
    return args


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
        self.args['date_sources'] = ['exif', 'file-name']
        self.assertEqual(
            ('file-name', datetime(2019, 10, 27, 12, 14, 1)),
            exif_rename.get_timestamp(datadir / '20191027_121401.jpg',
                                      self.args))

    def test_unparsable_filename(self):
        self.args['date_sources'] = ['file-name']
        self.assertRaises(exif_rename.TimestampReadException,
                          exif_rename.get_timestamp,
                          datadir / 'sammy_sleepy.jpg',
                          self.args)

    def test_fallthrough_ctime(self):
        self.args['date_sources'] = ['file-name', 'file-created']
        sleepy = datadir / 'sammy_sleepy.jpg'
        self.assertEqual(
            ('file-created', datetime.fromtimestamp(sleepy.stat().st_ctime)),
            exif_rename.get_timestamp(sleepy, self.args))

    def test_fallthrough_mtime(self):
        self.args['date_sources'] = ['file-name', 'file-modified']
        sleepy = datadir / 'sammy_sleepy.jpg'
        self.assertEqual(
            ('file-modified', datetime.fromtimestamp(sleepy.stat().st_mtime)),
            exif_rename.get_timestamp(sleepy, self.args))

    def test_no_image(self):
        self.assertRaises(exif_rename.TimestampReadException,
                          exif_rename.get_exif_timestamp,
                          __file__)

    def test_unknown_source(self):
        self.args['date_sources'] = ['meow']
        self.assertRaises(ValueError,
                          exif_rename.get_timestamp,
                          datadir / 'sammy_sleepy.jpg',
                          self.args)

    def test_match_numbers(self):
        timestamp = '20191027_121401'
        ext = '.jpg'
        self.assertTrue(exif_rename.matches_timestamp(
            f'{timestamp}{ext}', timestamp, ext))
        for i in range(1, 20):
            with self.subTest(i=i):
                self.assertTrue(exif_rename.matches_timestamp(
                    f'{timestamp}-{i}{ext}', timestamp, ext))


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.args = args_mock(date_source='exif')

    def test_date_sources(self):
        self.assertEqual(exif_rename.parse_date_sources(self.args), ['exif'])

    def test_date_sources_split(self):
        self.args['date_source'] = 'exif,file-name'
        self.assertEqual(exif_rename.parse_date_sources(self.args),
                         ['exif', 'file-name'])

    def test_date_sources_filename_no_format(self):
        self.args['date_source'] = 'exif,file-name'
        self.args['source_name_format'] = None
        self.assertRaises(exif_rename.CommandLineParseException,
                          exif_rename.parse_date_sources,
                          self.args)

    def test_date_sources_unknown(self):
        self.args['date_source'] = 'meow'
        self.assertRaises(exif_rename.CommandLineParseException,
                          exif_rename.parse_date_sources,
                          self.args)

    def test_empty_config(self):
        conf = exif_rename.read_config(datadir / 'config' / 'empty.conf')
        self.assertEqual(conf, dict())

    def test_full_config(self):
        conf = exif_rename.read_config(datadir / 'config' / 'full.conf')
        self.assertEqual(conf,
                         {
                             'pause_on_error': True,
                             'mv_cmd': 'meow',
                             'date_format': '%Y%m%d_%H%M%S',
                             'date_source': 'exif,file-name',
                             'source_name_format': '%Y%m%d_%H%M%S'
                         })


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
        for f in self.mapping:
            if not f.is_dir():
                shutil.copy2(f, self.tempdir.name)
        filelist = [x for x in Path(self.tempdir.name).iterdir()
                    if x.suffix == '.jpg']
        self.args = args_mock(files=filelist,
                              date_sources=['exif', 'file-name'])

    def tearDown(self):
        self.tempdir.cleanup()

    def test_renamer(self):
        r = exif_rename.Renamer(self.args)
        r.run()
        self.check_move()

    def test_renamer_no_sources(self):
        # this way there will be no valid timestamp source for
        # 20191027_121401.jpg
        self.args['date_sources'] = ['exif']
        r = exif_rename.Renamer(self.args)
        r.run()
        self.check_move()

    def test_main(self):
        # Exact command line parameters!
        args = ['--date-source', 'exif,file-name',
                '--source-name-format', '%Y%m%d_%H%M%S.jpg',
                '--date-format', '%Y%m%d_%H%M%S']
        args.extend(str(f) for f in self.args['files'])
        exif_rename.main(args)
        self.check_move()


if __name__ == '__main__':
    unittest.main(verbosity=2)
