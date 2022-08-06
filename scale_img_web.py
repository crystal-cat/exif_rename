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
import sys
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
    default_dateformat_help = exif_rename.default_dateformat.replace('%', '%%')
    parser = argparse.ArgumentParser(
        description='Scale images to certain maximum size (larger of width '
        'or height), naming the output file after date and time information '
        'from the original.')

    # Files to process
    parser.add_argument(
        'files', nargs='+', metavar='FILE', type=Path,
        help='List of files to process')

    parser.add_argument(
        '-f', '--date-format', action='store', metavar='FMT',
        help='Specify a custom date format (default '
        f'{default_dateformat_help}, see man (3) strftime for '
        'the format specification)')

    parser.add_argument(
        '-s', '--size', type=int, default=1280,
        help='The maximum dimension of the scaled image')

    # enable bash completion if argcomplete is available
    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    args = parser.parse_args()
    try:
        combined_args = exif_rename.merge_args(args)
    except exif_rename.CommandLineParseException as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    for f in combined_args['files']:
        scale_file(
            f,
            size=(combined_args['size'], combined_args['size']),
            date_format=combined_args['date_format'])
