#!/usr/bin/python3
# TODO: license
import argparse
import html
import json
import os
import sys

import pygments.lexers
import pygments.styles
import pygments.formatters

def read_records(filename):
    with open(filename) as f:
        return json.load(f)

def find_records(build_dir):
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
    # FIXME: escape directory separators in filename
    return "%s.html" % src_file

def record_sort_key(record):
    if 'count' not in record:
        return 0
    return -record['count']['value']

def write_td_pass(f, record):
    if record['kind'] == 'success':
        bgcolor = 'lightgreen'
    elif record['kind'] == 'failure':
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

def write_td_count(f, record):
    f.write('    <td style="text-align:right">\n')
    if 'count' in record:
        f.write(html.escape(str(int(record['count']['value']))))
    f.write('    </td>\n')

def url_from_location(loc):
    return '%s#line-%i' % (srcfile_to_html(loc['file']), loc['line'])

def make_index_html(out_dir, records):
    # Sort by highest-count down to lowest-count
    records = sorted(records, key=record_sort_key)

    filename = os.path.join(out_dir, "index.html");
    with open(filename, "w") as f:
        f.write('<html>\n')
        f.write('<body>\n')
        f.write('<table>\n')
        f.write('  <tr>\n')
        f.write('    <th>Source Location</th>\n')
        f.write('    <th>Execution Count</th>\n')
        f.write('    <th>Function</th>\n')
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

            # Execution Count:
            write_td_count(f, record)

            # Function:
            f.write('    <td>\n')
            f.write(html.escape(record['function']))
            f.write('    <td>\n')

            # Pass:
            write_td_pass(f, record)

            f.write('  </tr>\n')
        f.write('</table>\n')
        f.write('</body>\n')
        f.write('</html>\n')

def get_html_for_message(record):
    html_for_message = ''
    for item in record['message']:
        if type(item) is dict:
            text = ''
            if 'expr' in item:
                text = item['expr']
            elif 'stmt' in item:
                text = item['stmt']
            html_for_item = html.escape(text)
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

def make_per_source_file_html(build_dir, out_dir, records):
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
        f.write('''
table {
    border-collapse: collapse;
}

table, td, th, tr {
    border: 1px solid lightgrey;
}
''')

    for src_file in by_src_file:
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

        with open(os.path.join(out_dir, srcfile_to_html(src_file)), "w") as f:
            f.write('<html>\n')
            f.write('<link rel="stylesheet" href="style.css" type="text/css" />\n')
            f.write('<body>\n')
            f.write('<h1>%s</h1>' % html.escape(src_file))
            f.write('<table>\n')
            f.write('  <tr>\n')
            f.write('    <th>Line</th>\n')
            f.write('    <th>Hotness</th>\n')
            f.write('    <th>Pass</th>\n')
            f.write('    <th>Source</th>\n')
            f.write('    <th>Inlining Chain</th>\n')
            f.write('  </tr>\n')
            for line_num, html_line in enumerate(html_lines, start=1):
                # Add row for the source line itself.

                f.write('  <tr>\n')

                # Line:
                f.write('    <td id="line-%i">%i</td>\n' % (line_num, line_num))

                # Execution Count:
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

                    # Execution Count
                    write_td_count(f, record)

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
                    f.write('    <td><pre style="margin: 0 0;">%s</pre></td>\n'
                            % lines)

                    # Inlining Chain:
                    f.write('    <td><table>\n')
                    first = True
                    for inline in record.get('inlining_chain', []):
                        f.write('  <tr><td>')
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
                        f.write('</td></tr>\n')
                        first = False
                    f.write('    </table></td>\n')

                    f.write('  </tr>\n')

            f.write('</table>\n')
            f.write('</body>\n')
            f.write('</html>\n')

def make_html(build_dir, out_dir, records):
    if not os.path.exists(out_dir):
        os.mkdir(out_dir)
    make_index_html(out_dir, records)
    make_per_source_file_html(build_dir, out_dir, records)

def main(build_dir, out_dir):
    records = find_records(build_dir)
    if 0:
        for record in records:
            print(record)
    make_html(build_dir, out_dir, records)

main(sys.argv[1], sys.argv[2])
