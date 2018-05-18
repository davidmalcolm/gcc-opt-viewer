#!/usr/bin/python3
# TODO: license
import argparse
from collections import Counter
import html
import json
import os
import sys

import pygments.lexers
import pygments.styles
import pygments.formatters

def log(*args):
    print(*args)

def read_records(filename):
    log(' read_records: %r' % filename)
    with open(filename) as f:
        return json.load(f)

def find_records(build_dir):
    log('find_records: %r' % build_dir)

    records = []

    # (os.scandir is Python 3.5 onwards)
    for root, dirs, files in os.walk(build_dir):
        for file_ in files:
            if file_.endswith('.opt-record.json'):
                records += read_records(os.path.join(root, file_))

    return records

def escape(text):
    return text # FIXME

def srcfile_to_html(src_file):
    """
    Generate a .html filename for src_file
    """
    return html.escape("%s.html" % src_file.replace('/', '|'))

def record_sort_key(record):
    if 'count' not in record:
        return 0
    return -record['count']['value']

def get_effective_result(record):
    if record['kind'] == 'scope':
        if record['children']:
            return get_effective_result(record['children'][-1])
    return record['kind']

def write_td_pass(f, record):
    result = get_effective_result(record)
    if result == 'success':
        bgcolor = 'lightgreen'
    elif result == 'failure':
        bgcolor = 'lightcoral'
    else:
        bgcolor = ''
    f.write('    <td bgcolor="%s">\n' % bgcolor)

    impl_url = None
    impl_file = record['impl_location']['file']
    impl_line = record['impl_location']['line']
    # FIXME: something of a hack:
    PREFIX = '../../src/'
    if impl_file.startswith(PREFIX):
        relative_file = impl_file[len(PREFIX):]
        impl_url = ('https://github.com/gcc-mirror/gcc/tree/master/%s#L%i'
                    % (relative_file, impl_line))
    if impl_url:
        f.write('<a href="%s">\n' % impl_url)

    # FIXME: link to GCC source code
    if 'pass' in record:
        f.write(html.escape(record['pass']))

    if impl_url:
        f.write('</a>')

    f.write('    </td>\n')

def write_td_count(f, record, highest_count):
    f.write('    <td style="text-align:right">\n')
    if 'count' in record:
        if 1:
            if highest_count == 0:
                highest_count = 1
            hotness = 100. * record['count']['value'] / highest_count
            f.write(html.escape('%.2f' % hotness))
        else:
            f.write(html.escape(str(int(record['count']['value']))))
        if 0:
            f.write(html.escape(' (%s)' % record['count']['quality']))
    f.write('    </td>\n')

def write_inlining_chain(f, record):
    f.write('    <td><ul class="list-group">\n')
    first = True
    for inline in record.get('inlining_chain', []):
        f.write('  <li class="list-group-item">')
        if not first:
            f.write ('inlined from ')
        f.write('<code>%s</code>' % html.escape(inline['fndecl']))
        site = inline.get('site', None)
        if site:
            f.write(' at <a href="%s">%s:%i:%i</a>'
                    % (url_from_location(site),
                       html.escape(site['file']),
                       site['line'],
                       site['column']))
        f.write('</li>\n')
        first = False
    f.write('    </ul></td>\n')

def url_from_location(loc):
    return '%s#line-%i' % (srcfile_to_html(loc['file']), loc['line'])

def write_html_header(f, title, head_content):
    """
    Write initial part of HTML file using Bootstrap, up to and including
    opening of the <body> element.
    """
    f.write('<!doctype html>\n'
            '<html lang="en">\n'
            '  <head>\n'
            '    <!-- Required meta tags -->\n'
            '    <meta charset="utf-8">\n'
            '    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">\n'
            '\n'
            '    <!-- Bootstrap CSS -->\n'
            '    <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.1.1/css/bootstrap.min.css" integrity="sha384-WskhaSGFgHYWDcbwN70/dfYBj47jz9qbsMId/iRN3ewGhXQFZCSftd1LZCfmhktB" crossorigin="anonymous">\n'
            '\n')
    f.write(head_content)
    f.write('    <title>%s</title>\n' % title)
    f.write('  </head>\n'
            '  <body>\n')

def write_html_footer(f):
    """
    Write final part of HTML file using Bootstrap, closing the </body>
    element.
    """
    # jQuery first, then Popper.js, then Bootstrap JS
    f.write('    <script src="https://code.jquery.com/jquery-3.3.1.slim.min.js" integrity="sha384-q8i/X+965DzO0rT7abK41JStQIAqVgRVzpbzo5smXKp4YfRvH+8abtTE1Pi6jizo" crossorigin="anonymous"></script>\n'
            '    <script src="https://cdnjs.cloudflare.com/ajax/libs/popper.js/1.14.3/umd/popper.min.js" integrity="sha384-ZMP7rVo3mIykV+2+9J3UJ46jBk0WLaUAdn689aCwoqbBJiSnjAK/l8WvCWPIPm49" crossorigin="anonymous"></script>\n'
            '    <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.1.1/js/bootstrap.min.js" integrity="sha384-smHYKdLADwkXOn1EmN1qk/HfnUcbVRZyYmZ4qpPea6sjB/pTJ0euyQp0Mk8ck+5T" crossorigin="anonymous"></script>\n'
            '  </body>\n'
            '</html>\n')

def make_index_html(out_dir, records, highest_count):
    log(' make_index_html')

    # Sort by highest-count down to lowest-count
    records = sorted(records, key=record_sort_key)

    filename = os.path.join(out_dir, "index.html")
    with open(filename, "w") as f:
        write_html_header(f, 'Optimizations', '')
        f.write('<table class="table table-striped table-bordered table-sm">\n')
        f.write('  <tr>\n')
        f.write('    <th>Source Location</th>\n')
        f.write('    <th>Hotness</th>\n')
        f.write('    <th>Function / Inlining Chain</th>\n')
        f.write('    <th>Pass</th>\n')
        f.write('  </tr>\n')
        for record in records:
            f.write('  <tr>\n')

            # Source Location:
            f.write('    <td>\n')
            if 'location' in record:
                loc = record['location']
                f.write('<a href="%s">' % url_from_location (loc))
                f.write(html.escape("%s:%s:%i"
                               % (loc['file'], loc['line'], loc['column'])))
                f.write('</a>')
            f.write('    </td>\n')

            # Hotness:
            write_td_count(f, record, highest_count)

            # Inlining Chain:
            write_inlining_chain(f, record)

            # Pass:
            write_td_pass(f, record)

            f.write('  </tr>\n')
        f.write('</table>\n')
        write_html_footer(f)

def get_html_for_message(record):
    html_for_message = ''
    for item in record['message']:
        if type(item) is dict:
            if 'expr' in item:
                html_for_item = '<code>%s</code>' % html.escape(item['expr'])
            elif 'stmt' in item:
                html_for_item = '<code>%s</code>' % html.escape(item['stmt'])
            else:
                html_for_item = ''
            if 'location' in item:
                loc = item['location']
                html_for_item = ('<a href="%s">%s</a>'
                                 % (url_from_location (loc), html_for_item))
            html_for_message += html_for_item
        else:
            html_for_message += html.escape(str(item))
    if 'children' in record:
        for child in record['children']:
            for line in get_html_for_message(child).splitlines():
                html_for_message += '\n  ' + line
    return html_for_message

def make_per_source_file_html(build_dir, out_dir, records, highest_count):
    log(' make_per_source_file_html')

    # Dict of list of record, grouping by source file
    by_src_file = {}
    for record in records:
        if 'location' not in record:
            continue
        src_file = record['location']['file']
        if src_file not in by_src_file:
            by_src_file[src_file] = []
        by_src_file[src_file].append(record)

    style = pygments.styles.get_style_by_name('default')
    formatter = pygments.formatters.HtmlFormatter()

    # Write style.css
    with open(os.path.join(out_dir, "style.css"), "w") as f:
        f.write(formatter.get_style_defs())

    for src_file in by_src_file:
        log('  generating HTML for %r' % src_file)

        if 0:
            print(src_file)
            print('*' * 76)
        with open(os.path.join(build_dir, src_file)) as f:
            code = f.read()
        if 0:
            print(code)
            print('*' * 76)

        lexer = pygments.lexers.guess_lexer_for_filename(src_file, code)

        # Use pygments to convert it all to HTML:
        code_as_html = pygments.highlight(code, lexer, formatter)

        if 0:
            print(code_as_html)
            print('*' * 76)
            print(repr(code_as_html))
            print('*' * 76)

        EXPECTED_START = '<div class="highlight"><pre>'
        assert code_as_html.startswith(EXPECTED_START)
        code_as_html = code_as_html[len(EXPECTED_START):-1]

        EXPECTED_END = '</pre></div>'
        assert code_as_html.endswith(EXPECTED_END)
        code_as_html = code_as_html[0:-len(EXPECTED_END)]

        html_lines = code_as_html.splitlines()
        if 0:
            for html_line in html_lines:
                print(repr(html_line))
            print('*' * 76)

        # Group by line num
        by_line_num = {}
        for record in by_src_file[src_file]:
            line_num = record['location']['line']
            if line_num not in by_line_num:
                by_line_num[line_num] = []
            by_line_num[line_num].append(record)

        next_id = 0

        with open(os.path.join(out_dir, srcfile_to_html(src_file)), "w") as f:
            write_html_header(f, html.escape(src_file),
                              '<link rel="stylesheet" href="style.css" type="text/css" />\n')
            f.write('<h1>%s</h1>' % html.escape(src_file))
            f.write('<table class="table table-striped table-bordered table-sm">\n')
            f.write('  <tr>\n')
            f.write('    <th>Line</th>\n')
            f.write('    <th>Hotness</th>\n')
            f.write('    <th>Pass</th>\n')
            f.write('    <th>Source</th>\n')
            f.write('    <th>Function / Inlining Chain</th>\n')
            f.write('  </tr>\n')
            for line_num, html_line in enumerate(html_lines, start=1):
                # Add row for the source line itself.

                f.write('  <tr>\n')

                # Line:
                f.write('    <td id="line-%i">%i</td>\n' % (line_num, line_num))

                # Hotness:
                f.write('    <td></td>\n')

                # Pass:
                f.write('    <td></td>\n')

                # Source
                f.write('    <td><div class="highlight"><pre style="margin: 0 0;">')
                f.write(html_line)
                f.write('</pre></div></td>\n')

                # Inlining Chain:
                f.write('    <td></td>\n')

                f.write('  </tr>\n')

                # Add extra rows for any optimization records that apply to
                # this line.
                for record in by_line_num.get(line_num, []):
                    f.write('  <tr>\n')

                    # Line (blank)
                    f.write('    <td></td>\n')

                    # Hotness
                    write_td_count(f, record, highest_count)

                    # Pass:
                    write_td_pass(f, record)

                    # Text
                    column = record['location']['column']
                    html_for_message = get_html_for_message(record)
                    # Column number is 1-based:
                    indent = ' ' * (column - 1)
                    lines = indent + '<span style="color:green;">^</span>'
                    for line in html_for_message.splitlines():
                        lines += line + '\n' + indent
                    f.write('    <td><pre style="margin: 0 0;">')
                    num_lines = lines.count('\n')
                    collapsed =  num_lines > 7
                    if collapsed:
                        f.write('''<button class="btn btn-primary" type="button" data-toggle="collapse" data-target="#collapse-%i" aria-expanded="false" aria-controls="collapse-%i">
    Toggle messages <span class="badge badge-light">%i</span>
  </button>
                        ''' % (next_id, next_id, num_lines))
                        f.write('<div class="collapse" id="collapse-%i">' % next_id)
                        next_id += 1
                    f.write(lines)
                    if collapsed:
                        f.write('</div">')
                    f.write('</pre></td>\n')

                    # Inlining Chain:
                    write_inlining_chain(f, record)

                    f.write('  </tr>\n')

            f.write('</table>\n')
            write_html_footer(f)

def have_any_precise_counts(records):
    for record in records:
        if 'count' in record:
            if record['count']['quality'] == 'precise':
                return True

def filter_non_precise_counts(records):
    precise_records = []
    for record in records:
        if 'count' in record:
            if record['count']['quality'] != 'precise':
                continue
        precise_records.append(record)
    log('  purged %i non-precise records'
        % (len(records) - len(precise_records)))
    return precise_records

def analyze_counts(records):
    """
    Get the highest count, purging any non-precise counts
    if we have any precise counts.
    """
    log(' analyze_counts')

    if have_any_precise_counts(records):
        records = filter_non_precise_counts(records)

    highest_count = 0
    for record in records:
        if 'count' in record:
            value = record['count']['value']
            if value > highest_count:
                highest_count = value

    return records, highest_count

def make_html(build_dir, out_dir, records):
    log('make_html')

    if not os.path.exists(out_dir):
        os.mkdir(out_dir)

    records, highest_count = analyze_counts(records)
    log(' highest_count=%r' % highest_count)

    make_index_html(out_dir, records, highest_count)
    make_per_source_file_html(build_dir, out_dir, records, highest_count)

def print_as_remark(record):
    msg = ''
    loc = record.get('location', None)
    if loc:
        msg += '%s:%i:%i: ' % (loc['file'], loc['line'], loc['column'])
    msg += 'remark: '
    for item in record['message']:
        msg += str(item)
    if 'pass' in record:
        msg += ' [pass=%s]' % record['pass']
    if 'count' in record:
        msg += ' [count(%s)=%i]' % (record['count']['quality'],
                                    record['count']['value'])
    print(msg)

def filter_records(records):
    def criteria(record):
        # Hack to filter things a bit:
        if 'location' in record:
            src_file = record['location']['file']
            if 'pgen.c' in src_file:
                return False
        if 'pass' in record:
            if record['pass'] == 'slp':
                return False
            if record['pass'] == 'profile':
                return False
        return True
    return list(filter(criteria, records))

def summarize_records(records):
    log('records by pass:')
    num_records_by_pass = Counter()
    for record in records:
        num_records_by_pass[record.get('pass', None)] += 1
    for pass_,count in num_records_by_pass.most_common():
        log(' %s: %i' % (pass_, count))

def main(build_dir, out_dir):
    records = find_records(build_dir)

    records = filter_records(records)

    summarize_records(records)
    if 0:
        for record in records:
            print_as_remark(record)
    if 0:
        for record in records:
            print(record)
    make_html(build_dir, out_dir, records)

main(sys.argv[1], sys.argv[2])
