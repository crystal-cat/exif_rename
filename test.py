#!/usr/bin/python3
import argparse
import exif_rename
import hashlib
import itertools
import logging
import logging.handlers
import pytest
import re
import shlex
import shutil
import sys
import tempfile
from collections import ChainMap
from datetime import datetime
from exif_rename import DateSource
from pathlib import Path

datadir = Path(__file__).parent / 'test_data'
exif_rename.logger.setLevel(logging.DEBUG)


@pytest.fixture
def args(request):
    """Generic mock-up of parsed arguments. You can use the
    'modify_args' marker to modify it."""
    args = dict({
        'files': [],
        'date_sources': ['exif'],
        'source_name_format': '%Y%m%d_%H%M%S.jpg',
        'mv_cmd': None,
        'pause_on_error': False,
        'date_format': '%Y%m%d_%H%M%S',
        'simulate': False
    })

    marker = request.node.get_closest_marker("modify_args")
    if marker is not None:
        args.update(marker.args[0])

    args['date_sources'] = [DateSource(s) for s in args['date_sources']]
    return args


@pytest.fixture(scope='session')
def sammy_sleepy():
    """Sample file: picture of sleepy Sammy. For reading only."""
    return datadir / 'sammy_sleepy.jpg'


@pytest.fixture(scope='session')
def sample_mapping():
    """A dict mapping sample input files to their expected (possible)
    names after renaming."""
    return {
        datadir / 'sammy_awake.jpg': ['20190417_174537.jpg',
                                      '20190417_174537-1.jpg'],
        datadir / 'sammy_awake_commented.jpg': ['20190417_174537.jpg',
                                                '20190417_174537-1.jpg'],
        datadir / 'sammy_sleepy.jpg': ['20190207_153710.jpg'],
        datadir / '20191027_121401.jpg': ['20191027_121401.jpg']
    }


@pytest.fixture(scope='session')
def hashed_samples(sample_mapping):
    """Based on sample_mapping provide a dict with the SHA1 hashes of
    the files contents as keys and the same values.

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
def args_files(args, sample_files):
    """Arguments mock-up with the file provided by sample_files as
    files to handle and date sources set to EXIF and filename."""
    args['files'] = sample_files
    args['date_sources'] = [DateSource.EXIF, DateSource.FILE_NAME]
    return args


class TestTimestamp:
    @pytest.mark.parametrize(
        ['sample', 'expected'],
        [
            (datadir / 'sammy_awake.jpg',
             (DateSource.EXIF, datetime(2019, 4, 17, 17, 45, 37))),
            (datadir / 'sammy_sleepy.jpg',
             (DateSource.EXIF, datetime(2019, 2, 7, 15, 37, 10))),
            pytest.param(
                datadir / '20191027_121401.jpg',
                (DateSource.FILE_NAME, datetime(2019, 10, 27, 12, 14, 1)),
                marks=pytest.mark.modify_args(
                    {'date_sources': ['exif', 'file-name']})),
        ]
    )
    def test_timestamp(self, args, sample, expected):
        assert expected == exif_rename.get_timestamp(
            sample, args['date_sources'], args['source_name_format'])

    def test_unparsable_filename(self, args, sammy_sleepy):
        args['date_sources'] = [DateSource.FILE_NAME]
        with pytest.raises(exif_rename.TimestampReadException):
            exif_rename.get_timestamp(
                sammy_sleepy, args['date_sources'], args['source_name_format'])

    @pytest.mark.modify_args({'date_sources': ['file-name', 'file-created']})
    def test_fallthrough_ctime(self, args, sammy_sleepy):
        assert \
            (DateSource.FILE_CREATED,
             datetime.fromtimestamp(sammy_sleepy.stat().st_ctime)) \
            == exif_rename.get_timestamp(
                sammy_sleepy, args['date_sources'], args['source_name_format'])

    @pytest.mark.modify_args({'date_sources': ['file-name', 'file-modified']})
    def test_fallthrough_mtime(self, args, sammy_sleepy):
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


class TestMove:
    def test_renamer(self, tmp_path, args_files, hashed_samples):
        r = exif_rename.Renamer(args_files)
        r.run()
        check_move(tmp_path, hashed_samples)

    def test_renamer_mv_cmd(
            self, tmp_path, args_files, sample_mapping, hashed_samples):
        """Use test_data/script/mv_log.py to move the files. It logs all
        "src dst" pairs to the given logfile, so we can verify it
        really was the script that moved the files.

        """
        with tempfile.NamedTemporaryFile() as log:
            args_files['mv_cmd'] = \
                (f'{shlex.quote(sys.executable)} '
                 f'{shlex.quote(str(datadir / "script" / "mv_log.py"))} '
                 f'{shlex.quote(log.name)}')
            r = exif_rename.Renamer(args_files)
            r.run()
            logdata = log.read().decode()

        check_move(tmp_path, hashed_samples)
        # Replace keys in sample_mapping with source file basenames,
        # and remove files not expected to move
        mapping = dict((k.name, v) for k, v in sample_mapping.items()
                       if [k.name] != v)
        found = 0
        for src, dst in ([Path(p) for p in line.split()]
                         for line in logdata.splitlines()):
            assert src.parent == tmp_path
            assert dst.parent == tmp_path
            assert dst.name in mapping[src.name]
            found += 1
        assert found == len(mapping)

    @pytest.mark.modify_args({'date_sources': ['exif']})
    def test_renamer_no_sources(self, tmp_path, args_files, hashed_samples):
        # there will be no valid timestamp source for 20191027_121401.jpg
        r = exif_rename.Renamer(args_files)
        r.run()
        check_move(tmp_path, hashed_samples)

    def test_renamer_skip_paths(self, tmp_path, args_files, hashed_samples):
        args_files['files'] += [tmp_path, tmp_path / 'does_not_exist.jpg']
        r = exif_rename.Renamer(args_files)
        r.run()
        check_move(tmp_path, hashed_samples)

    @pytest.mark.modify_args({'simulate': True})
    def test_renamer_simulate(
            self, args_files, sample_mapping):
        """Check if the simulated_filelist of a Renamer contains exactly the
        expected items after a run()"""
        r = exif_rename.Renamer(args_files)
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
        assert set(p.name for p, c in r.files_added_counter.items() if c > 0) \
            == set(itertools.chain(*(v for k, v in sample_mapping.items()
                                     if [k.name] != v)))

        # Also check that the source file names are in the internal
        # list of removed files
        assert \
            set(p.name for p, c in r.files_removed_counter.items() if c > 0) \
            == set(k.name for k, v in sample_mapping.items() if [k.name] != v)

    def test_simulate_reuse_filename(
            self, tmp_path, args_files, caplog):
        sleepy = tmp_path / 'sammy_sleepy.jpg'
        # this creates a conflict with both (!) "awake" pictures
        sleepy.rename(tmp_path / '20190417_174537.jpg')
        # since Python 3.7 dict preserves order
        mapping = dict((tmp_path / k, tmp_path / v) for k, v in [
            ('20190417_174537.jpg', '20190207_153710.jpg'),
            ('sammy_awake.jpg', '20190417_174537.jpg'),
            ('sammy_awake_commented.jpg', '20190417_174537-1.jpg'),
        ])
        args_files['files'] = mapping.keys()
        args_files['simulate'] = True
        r = exif_rename.Renamer(args_files)

        with caplog.at_level(logging.INFO, logger='exif_rename'):
            r.run()

        logs = list(caplog.records)
        for k, v in mapping.items():
            assert logs.pop(0).getMessage() == f'{k!s} -(exif)-> {v!s}'
        assert r.files_added_counter == dict((k, 1) for k in mapping.values())
        assert dict(r.files_removed_counter) \
            == ChainMap(dict((k, 1) for k in mapping.keys()),
                        dict((k, 0) for k in mapping.values()))


class TestMain:
    def test_main(self, tmp_path, sample_files, hashed_samples):
        # Exact command line parameters!
        args = ['--date-source', 'exif,file-name',
                '--source-name-format', '%Y%m%d_%H%M%S.jpg',
                '--date-format', '%Y%m%d_%H%M%S']
        args.extend(str(f) for f in sample_files)
        exif_rename.main(args)
        check_move(tmp_path, hashed_samples)

    def test_main_simulate(self, sample_files, sample_mapping, caplog):
        """call main() with --simulate"""
        args = ['--date-source', 'exif,file-name',
                '--source-name-format', '%Y%m%d_%H%M%S.jpg',
                '--date-format', '%Y%m%d_%H%M%S',
                '--simulate']
        args.extend(str(f) for f in sample_files)

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

    def test_main_no_args(self, capsys):
        """exit with error on empty command line"""
        with pytest.raises(SystemExit) as cm:
            exif_rename.main([])
        assert cm.value.code > 0
        s = capsys.readouterr().err
        assert 'usage: ' in s
        assert 'error: the following arguments are required: FILE' in s

    def test_main_unknown_args(self, capsys):
        """exit with error on unknown argument"""
        with pytest.raises(SystemExit) as cm:
            exif_rename.main(['--woof', 'x.jpg'])
        assert cm.value.code > 0
        s = capsys.readouterr().err
        assert 'usage: ' in s
        assert 'error: unrecognized arguments: --woof' in s

    def test_main_invalid_date_source(self, capsys):
        """exit with error on invalid date source"""
        with pytest.raises(SystemExit) as cm:
            exif_rename.main(['--date-source', 'guess', 'x.jpg'])
        assert cm.value.code > 0
        assert 'Unknown date source: guess\n' == capsys.readouterr().err

    def test_main_version(self, capsys):
        """test --version option"""
        with pytest.raises(SystemExit) as cm:
            exif_rename.main(['--version'])
        assert cm.value.code == 0
        assert f'(version {exif_rename.__version__})' \
            in capsys.readouterr().out

    def test_main_help(self, capsys):
        """test --help option"""
        with pytest.raises(SystemExit) as cm:
            exif_rename.main(['--help'])
        assert cm.value.code == 0
        s = capsys.readouterr().out
        assert 'positional arguments:' in s
        assert 'options:' in s
        assert 'Program execution:' in s
        assert 'Date options:' in s


if __name__ == '__main__':
    sys.exit(pytest.main())
