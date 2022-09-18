#!/usr/bin/python3
import argparse
import contextlib
import exif_rename
import hashlib
import io
import itertools
import logging
import logging.handlers
import pytest
import queue
import re
import shlex
import shutil
import sys
import tempfile
import unittest
from collections import ChainMap
from datetime import datetime
from exif_rename import DateSource
from pathlib import Path

datadir = Path(__file__).parent / 'test_data'
exif_rename.logger.setLevel(logging.DEBUG)


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
    args['date_sources'] = \
        [DateSource(s) for s in args['date_sources']]
    return args


@pytest.fixture
def args():
    return args_mock()


@pytest.fixture
def sammy_sleepy():
    return datadir / 'sammy_sleepy.jpg'


@pytest.fixture
def sample_mapping():
    """Return a dict mapping sample input files to their expected
    (possible) names after renaming"""
    return {
        datadir / 'sammy_awake.jpg': ['20190417_174537.jpg',
                                      '20190417_174537-1.jpg'],
        datadir / 'sammy_awake_commented.jpg': ['20190417_174537.jpg',
                                                '20190417_174537-1.jpg'],
        datadir / 'sammy_sleepy.jpg': ['20190207_153710.jpg'],
        datadir / '20191027_121401.jpg': ['20191027_121401.jpg']
    }


@pytest.fixture
def hashed_samples(sample_mapping):
    """Assuming the keys in 'mapping' are Path objects, return a new dict
    with the SHA1 hashes of the file contents as keys and the same
    values.
    """
    hashes = dict()
    for file, names in sample_mapping.items():
        sha = hashlib.sha1()
        sha.update(file.read_bytes())
        hashes[sha.hexdigest()] = names
    return hashes


@pytest.fixture
def sample_files(tmp_path, sample_mapping):
    """Copy files listed in sample_mapping into tmp_path."""
    for f in sample_mapping:
        if not f.is_dir():
            shutil.copy2(f, tmp_path)
    return [x for x in tmp_path.iterdir()
            if x.suffix == '.jpg']


@pytest.fixture
def args_files(sample_files):
    return args_mock(files=sample_files, date_sources=['exif', 'file-name'])


class TestTimestamp:
    def test_sammy_awake(self, args):
        assert (DateSource.EXIF, datetime(2019, 4, 17, 17, 45, 37)) \
            == exif_rename.get_timestamp(datadir / 'sammy_awake.jpg',
                                         args['date_sources'],
                                         args['source_name_format'])

    def test_sammy_sleepy(self, args, sammy_sleepy):
        assert (DateSource.EXIF, datetime(2019, 2, 7, 15, 37, 10)) \
            == exif_rename.get_timestamp(
                sammy_sleepy, args['date_sources'], args['source_name_format'])

    def test_no_exif(self, args):
        args['date_sources'] = [DateSource.EXIF, DateSource.FILE_NAME]
        assert (DateSource.FILE_NAME, datetime(2019, 10, 27, 12, 14, 1)) \
            == exif_rename.get_timestamp(datadir / '20191027_121401.jpg',
                                         args['date_sources'],
                                         args['source_name_format'])

    def test_unparsable_filename(self, args, sammy_sleepy):
        args['date_sources'] = [DateSource.FILE_NAME]
        with pytest.raises(exif_rename.TimestampReadException):
            exif_rename.get_timestamp(
                sammy_sleepy, args['date_sources'], args['source_name_format'])

    def test_fallthrough_ctime(self, args, sammy_sleepy):
        args['date_sources'] = [DateSource.FILE_NAME, DateSource.FILE_CREATED]
        assert \
            (DateSource.FILE_CREATED,
             datetime.fromtimestamp(sammy_sleepy.stat().st_ctime)) \
            == exif_rename.get_timestamp(
                sammy_sleepy, args['date_sources'], args['source_name_format'])

    def test_fallthrough_mtime(self, args, sammy_sleepy):
        args['date_sources'] = [DateSource.FILE_NAME, DateSource.FILE_MODIFIED]
        assert \
            (DateSource.FILE_MODIFIED,
             datetime.fromtimestamp(sammy_sleepy.stat().st_mtime)) \
            == exif_rename.get_timestamp(
                sammy_sleepy, args['date_sources'], args['source_name_format'])

    def test_no_image(self):
        with pytest.raises(exif_rename.TimestampReadException):
            exif_rename.get_exif_timestamp(__file__)

    def test_unknown_source(self, args):
        args['date_sources'] = ['meow']
        with pytest.raises(ValueError):
            exif_rename.get_timestamp(datadir / 'sammy_sleepy.jpg', args)

    @pytest.mark.parametrize("i", range(20))
    def test_match_numbers(self, i):
        timestamp = '20191027_121401'
        ext = '.jpg'
        assert exif_rename.matches_timestamp(
            f'{timestamp}{f"-{i}" if i else ""}{ext}', timestamp, ext)

    @pytest.mark.parametrize(
        "t",
        [
            '20191027_121402.jpg',
            '20191027_121401-a.jpg',
            '20191027_121401--1.jpg'
        ])
    def test_mismatch_names(self, t):
        timestamp = '20191027_121401'
        ext = '.jpg'
        assert not exif_rename.matches_timestamp(t, timestamp, ext)


class TestConfig:
    def test_date_sources(self, args):
        args['date_source'] = 'exif'
        assert exif_rename.parse_date_sources(args) == [DateSource.EXIF]

    def test_date_sources_split(self, args):
        args['date_source'] = 'exif,file-name'
        assert exif_rename.parse_date_sources(args) \
            == [DateSource.EXIF, DateSource.FILE_NAME]

    def test_date_sources_filename_no_format(self, args):
        args['date_source'] = 'exif,file-name'
        args['source_name_format'] = None
        with pytest.raises(exif_rename.CommandLineParseException):
            exif_rename.parse_date_sources(args)

    def test_date_sources_unknown(self, args):
        args['date_source'] = 'meow'
        with pytest.raises(exif_rename.CommandLineParseException):
            exif_rename.parse_date_sources(args)

    def test_empty_config(self):
        conf = exif_rename.read_config(datadir / 'config' / 'empty.conf')
        assert conf == dict()

    def test_full_config(self):
        conf = exif_rename.read_config(datadir / 'config' / 'full.conf')
        assert conf == {
            'pause_on_error': True,
            'mv_cmd': 'meow',
            'date_format': '%Y%m%d_%H%M%S',
            'date_source': 'exif,file-name',
            'source_name_format': '%Y%m%d_%H%M%S'
        }

    def test_partial_config(self, monkeypatch):
        monkeypatch.setenv(
            'EXIF_RENAME_CONF', str(datadir / 'config' / 'partial.conf'))
        parser = argparse.ArgumentParser()
        parser.add_argument("files", nargs="+", metavar="FILE", type=Path,
                            help="List of files to process")
        args = parser.parse_args(['FOO'])
        conf = exif_rename.merge_args(args)
        assert conf['pause_on_error'] is False
        assert conf['mv_cmd'] is None
        assert conf['date_format'] == '%Y%m%d_%H%M%S'
        assert conf['date_source'] == 'exif'
        assert conf['date_sources'] == [DateSource.EXIF]
        assert conf['source_name_format'] == '%Y%m%d_%H%M%S'
        assert conf['files'] == [Path('FOO')]


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
        check_move(Path(self.tempdir.name), self.hashes)

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
        for src, dst in ([Path(p) for p in line.split()]
                         for line in logdata.splitlines()):
            self.assertEqual(src.parent, tempdir)
            self.assertEqual(dst.parent, tempdir)
            self.assertTrue(dst.name in mapping[src.name])
            found += 1
        self.assertEqual(found, len(mapping))

    def test_renamer_no_sources(self):
        # this way there will be no valid timestamp source for
        # 20191027_121401.jpg
        self.args['date_sources'] = [DateSource.EXIF]
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
            set(p.name for p, c in r.files_added_counter.items() if c > 0),
            set(itertools.chain(*(v for k, v in self.mapping.items()
                                  if [k.name] != v))))

        # Also check that the source file names are in the internal
        # list of removed files
        self.assertEqual(
            set(p.name for p, c in r.files_removed_counter.items() if c > 0),
            set(k.name for k, v in self.mapping.items() if [k.name] != v))

    def test_simulate_reuse_filename(self):
        tempdir = Path(self.tempdir.name)
        sleepy = tempdir / 'sammy_sleepy.jpg'
        # this creates a conflict with both (!) "awake" pictures
        sleepy.rename(tempdir / '20190417_174537.jpg')
        # since Python 3.7 dict preserves order
        mapping = dict((tempdir / k, tempdir / v) for k, v in [
            ('20190417_174537.jpg', '20190207_153710.jpg'),
            ('sammy_awake.jpg', '20190417_174537.jpg'),
            ('sammy_awake_commented.jpg', '20190417_174537-1.jpg'),
        ])
        self.args['files'] = mapping.keys()
        self.args['simulate'] = True
        r = exif_rename.Renamer(self.args)

        logger = logging.getLogger('exif_rename')
        q = queue.SimpleQueue()
        handler = logging.handlers.QueueHandler(q)
        logger.addHandler(handler)
        try:
            r.run()
        finally:
            logger.removeHandler(handler)

        for k, v in mapping.items():
            self.assertEqual(q.get_nowait().getMessage(),
                             f'{k!s} -(exif)-> {v!s}')
        self.assertEqual(r.files_added_counter,
                         dict((k, 1) for k in mapping.values()))
        self.assertEqual(dict(r.files_removed_counter),
                         ChainMap(dict((k, 1) for k in mapping.keys()),
                                  dict((k, 0) for k in mapping.values())))


def check_move(tmp_path, hashes):
    found = 0
    for f in tmp_path.iterdir():
        sha = hashlib.sha1()
        sha.update(f.read_bytes())
        fhash = sha.hexdigest()
        if fhash in hashes:
            assert f.name in hashes[fhash]
            found += 1
    assert found == len(hashes)


class TestMain:
    def test_main(self, tmp_path, args_files, hashed_samples):
        # Exact command line parameters!
        args = ['--date-source', 'exif,file-name',
                '--source-name-format', '%Y%m%d_%H%M%S.jpg',
                '--date-format', '%Y%m%d_%H%M%S']
        args.extend(str(f) for f in args_files['files'])
        exif_rename.main(args)
        check_move(tmp_path, hashed_samples)

    def test_main_simulate(self, args_files, sample_mapping, caplog):
        """call main() with --simulate"""
        args = ['--date-source', 'exif,file-name',
                '--source-name-format', '%Y%m%d_%H%M%S.jpg',
                '--date-format', '%Y%m%d_%H%M%S',
                '--simulate']
        args.extend(str(f) for f in args_files['files'])

        with caplog.at_level(logging.INFO, logger='exif_rename'):
            exif_rename.main(args)
        # ensure there are log messages for all expected files
        assert len(caplog.records) == 3

        # capture basenames for source and destination filenames
        # because the directory varies by test run
        log_re = re.compile(
            r'(?:.+/)(?P<source>\w+\.jpg) -\(exif\)-> '
            r'(?:.+/)(?P<dest>\d{8}_\d{6}(?:-\d+)?\.jpg)')

        dest_names = set()
        for r in caplog.records:
            m = log_re.match(r.getMessage())
            assert m is not None
            # check that each reported destination file shows up in
            # the expected names for that file
            source = m.group('source')
            dest = m.group('dest')
            assert dest in sample_mapping[datadir / source]
            dest_names.add(dest)

        # ensure all destination names are unique
        assert len(dest_names) == 3

    def test_main_no_args(self):
        """exit with error on empty command line"""
        with pytest.raises(SystemExit) as cm:
            with contextlib.redirect_stderr(io.StringIO()) as capture:
                exif_rename.main([])
        assert cm.value.code > 0
        s = capture.getvalue()
        assert 'usage: ' in s
        assert 'error: the following arguments are required: FILE' in s

    def test_main_unknown_args(self):
        """exit with error on unknown argument"""
        with pytest.raises(SystemExit) as cm:
            with contextlib.redirect_stderr(io.StringIO()) as capture:
                exif_rename.main(['--woof', 'x.jpg'])
        assert cm.value.code > 0
        s = capture.getvalue()
        assert 'usage: ' in s
        assert 'error: unrecognized arguments: --woof' in s

    def test_main_invalid_date_source(self):
        """exit with error on invalid date source"""
        with pytest.raises(SystemExit) as cm:
            with contextlib.redirect_stderr(io.StringIO()) as capture:
                exif_rename.main(['--date-source', 'guess', 'x.jpg'])
        assert cm.value.code > 0
        s = capture.getvalue()
        assert 'Unknown date source: guess\n' == s

    def test_main_version(self):
        """test --version option"""
        with pytest.raises(SystemExit) as cm:
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                exif_rename.main(['--version'])
        assert cm.value.code == 0
        s = capture.getvalue()
        assert f'(version {exif_rename.__version__})' in s

    def test_main_help(self):
        """test --help option"""
        with pytest.raises(SystemExit) as cm:
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                exif_rename.main(['--help'])
        assert cm.value.code == 0
        s = capture.getvalue()
        assert 'positional arguments:' in s
        assert 'options:' in s
        assert 'Program execution:' in s
        assert 'Date options:' in s


if __name__ == '__main__':
    sys.exit(pytest.main())
