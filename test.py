#!/usr/bin/python3
import exif_rename
import hashlib
import itertools
import logging
import re
import shlex
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

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

    def test_mismatch_names(self):
        timestamp = '20191027_121401'
        ext = '.jpg'
        tests = ['20191027_121402.jpg', '20191027_121401-a.jpg',
                 '20191027_121401--1.jpg']
        for t in tests:
            with self.subTest(name=t):
                self.assertFalse(
                    exif_rename.matches_timestamp(t, timestamp, ext))


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
        self.tempdir = tempfile.TemporaryDirectory()
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

    def test_renamer_mv_cmd(self):
        """Use test_data/script/mv_log.py to move the files. It logs all
        "src dst" pairs to the given logfile, so we can verify it
        really was the script that moved the files.

        """
        with tempfile.NamedTemporaryFile() as log:
            self.args['mv_cmd'] = \
                (f'{shlex.quote(sys.executable)} '
                 f'{shlex.quote(str(datadir / "script" / "mv_log.py"))} '
                 f'{shlex.quote(log.name)}')
            r = exif_rename.Renamer(self.args)
            r.run()
            logdata = log.read().decode()

        self.check_move()
        tempdir = Path(self.tempdir.name)
        # Replace keys in self.mapping with source file basenames, and
        # remove files not expected to move
        mapping = dict((k.name, v) for k, v in self.mapping.items()
                       if [k.name] != v)
        found = 0
        for src, dst in ([Path(p) for p in l.split()]
                         for l in logdata.splitlines()):
            self.assertEqual(src.parent, tempdir)
            self.assertEqual(dst.parent, tempdir)
            self.assertTrue(dst.name in mapping[src.name])
            found += 1
        self.assertEqual(found, len(mapping))

    def test_renamer_mv_cmd_simulate(self):
        logger = logging.getLogger('exif_rename')
        self.args['mv_cmd'] = 'git mv'
        self.args['simulate'] = True

        with tempfile.SpooledTemporaryFile(mode='w+') as log:
            handler = logging.StreamHandler(stream=log)
            logger.addHandler(handler)
            try:
                r = exif_rename.Renamer(self.args)
                r.run()
            finally:
                logger.removeHandler(handler)
            log.seek(0)
            logdata = log.read()

        dry_re = re.compile(r'^(\[.*\])\s"(.*)"\s".*"$')
        for l in logdata.splitlines():
            m = dry_re.fullmatch(l)
            if m:
                self.assertEqual(m.group(1),
                                 str(shlex.split(self.args['mv_cmd'])))
                self.assertIn(Path(m.group(2)), self.args['files'])

    def test_renamer_no_sources(self):
        # this way there will be no valid timestamp source for
        # 20191027_121401.jpg
        self.args['date_sources'] = ['exif']
        r = exif_rename.Renamer(self.args)
        r.run()
        self.check_move()

    def test_renamer_skip_paths(self):
        tempdir = Path(self.tempdir.name)
        self.args['files'] += [tempdir, tempdir / 'does_not_exist.jpg']
        r = exif_rename.Renamer(self.args)
        r.run()
        self.check_move()

    def test_renamer_simulate(self):
        """Check if the simulated_filelist of a Renamer contains exactly the
        expected items after a run()"""
        self.args['simulate'] = True
        r = exif_rename.Renamer(self.args)
        r.run()
        # To explain the magic below:
        #
        # 1. For the simulation result we only need the basenames,
        # because the full names will vary with the temporary
        # directory.
        #
        # 2. For the expected set we need to filter out files where
        # the names do not change, because those don't show up in the
        # simulation list.
        self.assertEqual(
            set(p.name for p in r.simulated_filelist),
            set(itertools.chain(*(v for k, v in self.mapping.items()
                                  if [k.name] != v))))

    def test_main(self):
        # Exact command line parameters!
        args = ['--date-source', 'exif,file-name',
                '--source-name-format', '%Y%m%d_%H%M%S.jpg',
                '--date-format', '%Y%m%d_%H%M%S']
        args.extend(str(f) for f in self.args['files'])
        exif_rename.main(args)
        self.check_move()


if __name__ == '__main__':
    logging.basicConfig(format='%(filename)s:%(lineno)s: %(message)s',
                        level=logging.DEBUG)
    unittest.main(verbosity=2)
