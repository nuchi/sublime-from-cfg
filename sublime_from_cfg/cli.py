import argparse
import os
import re

from . import sublime_from_cfg
from .types import SublimeSyntaxOptions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'input', help='Path to input .sbnf file')
    parser.add_argument(
        '-o', '--output', help='Path to generated output file',
    )
    parser.add_argument(
        'args', nargs='*', help='Optional global arguments')
    parser.usage = parser.format_help()
    args = parser.parse_intermixed_args()

    basename = re.sub(r'\.sbnf$', '', os.path.basename(args.input))
    if args.output is None:
        args.output = re.sub(r'\.sbnf$', '', args.input) + '.sublime-syntax'

    with open(args.input) as f:
        sbnf = f.read()

    options = SublimeSyntaxOptions(basename)
    ss = sublime_from_cfg(sbnf, args.args, options)

    with open(args.output, 'w') as f:
        f.write(ss.dump())
