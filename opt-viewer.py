#!/usr/bin/python3
# TODO: license
import argparse

from static import generate_static_report
from utils import find_records, log

parser = argparse.ArgumentParser(description="Parse the output of GCC's -fsave-optimization-record.")
parser.add_argument('build_dir', metavar='BUILD_DIR', type=str,
                    help='The directory in which to look for .json.gz files')
parser.add_argument('--output-dir', dest='output_dir', metavar='OUTPUT_DIR', type=str, required=False,
                    help='The directory to which to write .html output')
args = parser.parse_args()

if args.output_dir:
    # Static HTML
    generate_static_report(args.build_dir, args.output_dir)
else:
    # Dynamic HTML
    tus = find_records(args.build_dir)
    import server
    server.app.tus = tus
    server.app.run()
