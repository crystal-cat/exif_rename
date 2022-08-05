#!/usr/bin/python3
"""scale_img_web

A tool for scaling images to certain maximum dimensions, naming the
output file after date information from the original.

"""

__author__ = "Fiona Klute"
__version__ = "0.1.0"
__copyright__ = "Copyright (C) 2021 Fiona Klute"
__license__ = """
License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>.
This is free software: you are free to change and redistribute it.
There is NO WARRANTY, to the extent permitted by law.
"""
import argparse
import exif_rename
from collections import ChainMap
from contextlib import ExitStack
from pathlib import Path
from PIL import Image


def scale_file(infile, size=(1280, 1280), date_format='%Y%m%d_%H%M%S'):
    timestamp = exif_rename.get_timestamp(
        infile,
        [
            exif_rename.DateSource.EXIF,
            exif_rename.DateSource.FILE_CREATED
        ])[1]

    formatted_date = timestamp.strftime(date_format)
    with ExitStack() as stack:
        # find an available filename based on the timestamp
        out = None
        index = 0
        while out is None:
            outfile = formatted_date + (f'-{index}' if index else '') \
                + infile.suffix
            try:
                # use open with exclusive creation for collision detection
                out = stack.enter_context(open(outfile, 'xb'))
            except FileExistsError:
                index += 1
        print(f'{infile} -> {outfile}')

        img = stack.enter_context(Image.open(infile))
        img.thumbnail(size)
        img.save(out)


if __name__ == '__main__':
    # TODO: configurable size (command line)
    default_dateformat_help = exif_rename.default_dateformat.replace('%', '%%')
    parser = argparse.ArgumentParser()

    # Files to process
    parser.add_argument('files', nargs='+', metavar='FILE', type=Path,
                        help='List of files to process')

    parser.add_argument('-f', '--date-format', action='store',
                        metavar='fmt',
                        help='Specify a custom date format (default '
                        f'{default_dateformat_help}, see man (3) '
                        'strftime for the format specification)')

    # enable bash completion if argcomplete is available
    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    args = parser.parse_args()
    cmd_args = {k: v for k, v in vars(args).items() if v is not None}

    try:
        conf_args = exif_rename.read_config('~/.exif_rename.conf')
    except FileNotFoundError:
        # It's okay if there is no config file.
        conf_args = {}

    combined_args = ChainMap(cmd_args, conf_args, exif_rename.default_conf)

    for f in combined_args['files']:
        scale_file(f, date_format=combined_args['date_format'])
