#!/usr/bin/python3
# TODO: license
import argparse
from collections import Counter
import html
import json
import os
from pprint import pprint
import sys

import pygments.lexers
import pygments.styles
import pygments.formatters

def log(*args):
    print(*args)


class TranslationUnit:
    """Top-level class for containing optimization records"""
    @staticmethod
    def from_filename(filename):
        with open(filename) as f:
            root_obj = json.load(f)
            #pprint(root_obj)
            return TranslationUnit(root_obj)

    def __init__(self, json_obj):
        self.pass_by_id = {}

        # Expect a 3-tuple
        metadata, passes, records = json_obj

        self.format = metadata['format']
        self.generator = metadata['generator']
        self.passes = [Pass(obj, self) for obj in passes]
        self.records = [Record.from_json(obj, self) for obj in records]

    def __repr__(self):
        return ('TranslationUnit(%r, %r, %r)'
                % (self.generator, self.passes, self.records))

    def get_records(self):
        return [obj for obj in self.records if isinstance(obj, Record)]

    def get_states(self):
        return [obj for obj in self.records if isinstance(obj, State)]

class Pass:
    """An optimization pass"""
    def __init__(self, json_obj, tu):
        self.id_ = json_obj['id']
        self.name = json_obj['name']
        self.num = json_obj['num']
        self.optgroups = set(json_obj['optgroups']) # list of strings
        self.type = json_obj['type']
        tu.pass_by_id[self.id_] = self
        self.children = [Pass(child, tu)
                         for child in json_obj.get('children', [])]

    def __repr__(self):
        return ('Pass(%r, %r, %r, %r)'
                % (self.name, self.num, self.optgroups, self.type))

def from_optional_json_field(cls, jsonobj, field):
    if field not in jsonobj:
        return None
    return cls(jsonobj[field])

class ImplLocation:
    """An implementation location (within the compiler itself)"""
    def __init__(self, json_obj):
        self.file = json_obj['file']
        self.line = json_obj['line']
        self.function = json_obj['function']

    def __repr__(self):
        return ('ImplLocation(%r, %r, %r)'
                % (self.file, self.line, self.function))

class Location:
    """A source location"""
    def __init__(self, json_obj):
        self.file = json_obj['file']
        self.line = json_obj['line']
        self.column = json_obj['column']

    def __str__(self):
        return '%s:%i:%i' % (self.file, self.line, self.column)

    def __repr__(self):
        return ('Location(%r, %r, %r)'
                % (self.file, self.line, self.column))

class Count:
    """An execution count"""
    def __init__(self, json_obj):
        self.quality = json_obj['quality']
        self.value = json_obj['value']

    def __repr__(self):
        return ('Count(%r, %r)'
                % (self.quality, self.value))

    def is_precise(self):
        return self.quality in ('precise', 'adjusted')

class BaseRecord:
    """A optimization record: success/failure/note/state"""
    @staticmethod
    def from_json(json_obj, tu):
        if json_obj['kind'] == 'state':
            return State(json_obj, tu)
        else:
            return Record(json_obj, tu)

    def __init__(self, json_obj, tu):
        self.kind = json_obj['kind']
        if 'pass' in json_obj:
            self.pass_ = tu.pass_by_id[json_obj['pass']]
        else:
            self.pass_ = None
        self.function = json_obj.get('function', None)

class InliningNode:
    """A node within an inlining chain"""
    def __init__(self, json_obj):
        self.fndecl = json_obj['fndecl']
        self.site = from_optional_json_field(Location, json_obj, 'site')

class Record(BaseRecord):
    """A optimization record that's not a "state": success/failure/note"""
    def __init__(self, json_obj, tu):
        BaseRecord.__init__(self, json_obj, tu)
        #print('Record.__init: ')
        #pprint(json_obj)
        self.impl_location = from_optional_json_field(ImplLocation, json_obj, 'impl_location')
        self.message = [Item.from_json(obj) for obj in json_obj['message']]
        self.count = from_optional_json_field(Count, json_obj, 'count')
        self.location = from_optional_json_field(Location, json_obj, 'location')
        if 'inlining_chain' in json_obj:
            self.inlining_chain = [InliningNode(obj)
                                   for obj in json_obj['inlining_chain']]
        else:
            self.inlining_chain = None
        self.children = [BaseRecord.from_json(child, tu)
                         for child in json_obj.get('children', [])]

    def __repr__(self):
        return ('Record(%r, %r, %r, %r, %r)'
                % (self.kind, self.message, self.pass_, self.function, self.children))

class Item:
    """Base class for non-string items within a message"""
    @staticmethod
    def from_json(json_obj):
        if isinstance(json_obj, str):
            return json_obj
        if 'expr' in json_obj:
            return Expr(json_obj)
        elif 'stmt' in json_obj:
            return Stmt(json_obj)
        elif 'name' in json_obj:
            return SymtabNode(json_obj)
        else:
            raise ValueError('unrecognized item: %r' % json_obj)

class Expr(Item):
    """An expression within a message"""
    def __init__(self, json_obj):
        self.expr = json_obj['expr']
        self.location = from_optional_json_field(Location, json_obj, 'location')

class Stmt(Item):
    """A statement within a message"""
    def __init__(self, json_obj):
        self.stmt = json_obj['stmt']
        self.location = from_optional_json_field(Location, json_obj, 'location')

class SymtabNode(Item):
    """A symbol table node within a message"""
    def __init__(self, json_obj):
        self.name = json_obj['name']
        self.order = json_obj['order']
        self.location = from_optional_json_field(Location, json_obj, 'location')

    def __str__(self):
        return '%s/%s' % (self.name, self.order)

class State(BaseRecord):
    """The state of a function after a pass has run"""
    def __init__(self, json_obj, tu):
        BaseRecord.__init__(self, json_obj, tu)
        self.cfg = from_optional_json_field(Cfg, json_obj, 'cfg')

    def __repr__(self):
        return 'State(%r, %r)' % (self.function, self.pass_)

class Cfg:
    """A control-flow graph within a State"""
    def __init__(self, json_obj):
        self.blocks = []
        self.block_by_index = {}
        for json_block in json_obj:
            block = Block(json_block)
            self.blocks.append(block)
            self.block_by_index[block.index] = block
        # Create edges once all blocks have been created
        self.edges = []
        for json_block in json_obj:
            src = self.block_by_index[json_block['index']]
            for json_edge in json_block['succs']:
                dest = self.block_by_index[json_edge['dest']]
                e = Edge(src, dest, json_edge)
                self.edges.append(e)

class Block:
    """A basic block within a Cfg"""
    def __init__(self, json_obj):
        self.index = json_obj['index']
        self.flags = set(json_obj['flags'])
        self.stmts = json_obj.get('stmts')
        # "succs" is done later on, once all blocks have been created
        self.succs = []

    def __repr__(self):
        return 'Block(%r, %r)' % (self.index, self.flags)

    def get_nondebug_stmts(self):
        if not self.stmts:
            return ''
        non_debug_lines = []
        for line in self.stmts.splitlines():
            if line.startswith('# DEBUG'):
                continue
            non_debug_lines.append(line)
        return '\n'.join(non_debug_lines)


class Edge:
    """An edge within a Cfg"""
    def __init__(self, src, dest, json_obj):
        self.src = src
        self.dest = dest
        self.flags = set(json_obj['flags'])

    def __repr__(self):
        return ('Edge(%r, %r, %r)'
                % (self.src.index, self.dest.index, self.flags))

def find_records(build_dir):
    """
    Scan build_dir and below, looking for "*.opt-record.json".
    Return a list of TranslationUnit instances.
    """
    log('find_records: %r' % build_dir)

    tus = []

    # (os.scandir is Python 3.5 onwards)
    for root, dirs, files in os.walk(build_dir):
        for file_ in files:
            if file_.endswith('.opt-record.json'):
                filename = os.path.join(root, file_)
                log(' reading: %r' % filename)
                tus.append(TranslationUnit.from_filename(filename))

    return tus

def escape(text):
    return text # FIXME

def srcfile_to_html(src_file):
    """
    Generate a .html filename for src_file
    """
    return html.escape("%s.html" % src_file.replace('/', '|'))

def function_to_html(function):
    """
    Generate a .html filename for function
    """
    return html.escape("%s.html" % function.replace('/', '|'))

def record_sort_key(record):
    if not record.count:
        return 0
    return -record.count.value

def get_effective_result(record):
    if record.kind == 'scope':
        if record.children:
            return get_effective_result(record.children[-1])
    return record.kind

def get_summary_text(record):
    if record.kind == 'scope':
        if record.children:
            return get_summary_text(record.children[-1])
    return get_html_for_message(record)

def write_td_with_color(f, record, html_text):
    result = get_effective_result(record)
    if result == 'success':
        bgcolor = 'lightgreen'
    elif result == 'failure':
        bgcolor = 'lightcoral'
    else:
        bgcolor = ''
    f.write('    <td bgcolor="%s">%s</td>\n' % (bgcolor, html_text))

def write_td_pass(f, record):
    html_text = ''
    impl_url = None
    impl_file = record.impl_location.file
    impl_line = record.impl_location.line
    # FIXME: something of a hack:
    PREFIX = '../../src/'
    if impl_file.startswith(PREFIX):
        relative_file = impl_file[len(PREFIX):]
        impl_url = ('https://github.com/gcc-mirror/gcc/tree/master/%s#L%i'
                    % (relative_file, impl_line))
    if impl_url:
        html_text += '<a href="%s">\n' % impl_url

    # FIXME: link to GCC source code
    if record.pass_:
        html_text += html.escape(record.pass_.name)

    if impl_url:
        html_text += '</a>'

    write_td_with_color(f, record, html_text)

def write_td_count(f, record, highest_count):
    f.write('    <td style="text-align:right">\n')
    if record.count:
        if 1:
            if highest_count == 0:
                highest_count = 1
            hotness = 100. * record.count.value / highest_count
            f.write(html.escape('%.2f' % hotness))
        else:
            f.write(html.escape(str(int(record.count.value))))
        if 0:
            f.write(html.escape(' (%s)' % record.count.quality))
    f.write('    </td>\n')

def write_inlining_chain(f, record):
    f.write('    <td><ul class="list-group">\n')
    first = True
    if record.inlining_chain:
        for inline in record.inlining_chain:
            f.write('  <li class="list-group-item">')
            if not first:
                f.write ('inlined from ')
            f.write('<code>%s</code>' % html.escape(inline.fndecl))
            site = inline.site
            if site:
                f.write(' at <a href="%s">%s</a>'
                        % (url_from_location(site),
                           html.escape(str(site))))
            f.write('</li>\n')
            first = False
    f.write('    </ul></td>\n')

def url_from_location(loc):
    return '%s#line-%i' % (srcfile_to_html(loc.file), loc.line)

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

def make_index_html(out_dir, tus, highest_count):
    log(' make_index_html')

    # Gather all records
    records = []
    for tu in tus:
        records += tu.get_records()

    # Sort by highest-count down to lowest-count
    records = sorted(records, key=record_sort_key)

    filename = os.path.join(out_dir, "index.html")
    with open(filename, "w") as f:
        write_html_header(f, 'Optimizations', '')
        f.write('<table class="table table-striped table-bordered table-sm">\n')
        f.write('  <tr>\n')
        f.write('    <th>Summary</th>\n')
        f.write('    <th>Source Location</th>\n')
        f.write('    <th>Hotness</th>\n')
        f.write('    <th>Function / Inlining Chain</th>\n')
        f.write('    <th>Pass</th>\n')
        f.write('  </tr>\n')
        for record in records:
            f.write('  <tr>\n')

            # Summary
            write_td_with_color(f, record, get_summary_text(record))

            # Source Location:
            f.write('    <td>\n')
            if record.location:
                loc = record.location
                f.write('<a href="%s">' % url_from_location (loc))
                f.write(html.escape(str(loc)))
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
    for item in record.message:
        if isinstance(item, str):
            html_for_message += html.escape(str(item))
        else:
            if isinstance(item, Expr):
                html_for_item = '<code>%s</code>' % html.escape(item.expr)
            elif isinstance(item, Stmt):
                html_for_item = '<code>%s</code>' % html.escape(item.stmt)
            elif isinstance(item, SymtabNode):
                html_for_item = ('<code>%s/%i</code>'
                                 % (html.escape(item.name), item.order))
            else:
                raise TypeError('unknown message item: %r' % item)
            if item.location:
                html_for_item = ('<a href="%s">%s</a>'
                                 % (url_from_location (item.location), html_for_item))
            html_for_message += html_for_item

    if record.children:
        for child in record.children:
            for line in get_html_for_message(child).splitlines():
                html_for_message += '\n  ' + line
    return html_for_message

def make_per_source_file_html(build_dir, out_dir, tus, highest_count):
    log(' make_per_source_file_html')

    # Gather all records
    records = []
    for tu in tus:
        records += tu.get_records()

    # Dict of list of record, grouping by source file
    by_src_file = {}
    for record in records:
        if not record.location:
            continue
        src_file = record.location.file
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
            line_num = record.location.line
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
                    column = record.location.column
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

def write_cfg_view(f, view_id, cfg):
    # see http://visjs.org/docs/network/
    f.write('<div id="%s"></div>' % view_id)
    f.write('<script type="text/javascript">\n')
    f.write('  var nodes = new vis.DataSet([\n')
    for block in cfg.blocks:
        if block.stmts:
            label = block.get_nondebug_stmts()
        elif block.index == 0:
            label = 'ENTRY'
        elif block.index == 1:
            label = 'EXIT'
        else:
            label = 'Block %i' % block.index
        f.write("    {id: %i, label: %r},\n"
                % (block.index, label)) # FIXME: Python vs JS escaping?
    f.write('    ]);\n')
    f.write('  var edges = new vis.DataSet([\n')
    for edge in cfg.edges:
        label = ' '. join(str(flag) for flag in edge.flags)
        f.write('    {from: %i, to: %i, label: %r},\n'
                % (edge.src.index, edge.dest.index, label))
    f.write(' ]);\n')
    f.write("  var container = document.getElementById('%s');"
            % view_id)
    f.write("""
  var data = {
    nodes: nodes,
    edges: edges
  };
  var options = {
    nodes:{
      shape: 'box',
      font: {'face': 'monospace', 'align': 'left'},
      scaling: {
        label:true
      },
      shadow: true
    },
    edges:{
      arrows: 'to',
    },
    layout:{
      hierarchical: true
    }
  };
  var network = new vis.Network(container, data, options);
</script>
""")

def make_per_function_html(build_dir, out_dir, tus):
    log(' make_per_function_html')

    functions = set()
    for tu in tus:
        for state in tu.get_states():
            functions.add(state.function)

    states_by_function = {}
    for function in functions:
        states_by_function[function] = []
    for tu in tus:
        for state in tu.get_states():
            states_by_function[state.function].append(state)

    fns_dir = os.path.join(out_dir, 'functions')

    if not os.path.exists(fns_dir):
        os.mkdir(fns_dir)

    for function in functions:
        log('  generating HTML for %r' % function)

        with open(os.path.join(fns_dir, function_to_html(function)), "w") as f:
            write_html_header(f, html.escape(function),
                              ('<link rel="stylesheet" href="style.css" type="text/css" />\n'
                               '<script type="text/javascript" src="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.js"></script>\n'
                               '<link href="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.css" rel="stylesheet" type="text/css" />\n'))

            f.write('<h1>%s</h1>' % html.escape(function))

            f.write("""
<div>
  <div class="row">
    <div class="col-4">
      <nav id="navbar-passes" class="navbar navbar-light bg-light flex-column">
        <a class="navbar-brand" href="#">After Pass</a>
        <nav class="nav nav-pills flex-column">
""")
            for state in states_by_function[function]:
                f.write('<a class="nav-link" href="#%s">%s</a>\n'
                        % (state.pass_.id_, state.pass_.name))
                # FIXME: show pass nesting
            f.write("""
        </nav>
      </nav>
    </div>
    <div class="col-8">
      <div data-spy="scroll" data-target="#navbar-passes" data-offset="0">
                """)
            for state in states_by_function[function]:
                f.write('<div class="shadow-lg p-3 mb-5 bg-white rounded">')
                f.write('<h4 id="%s">%s</h4>'
                        % (state.pass_.id_, html.escape(state.pass_.name)))
                # TODO: show messages
                if state.cfg:
                    f.write('<div class="border border-info">')
                    write_cfg_view(f, 'cfg-%s' % state.pass_.id_, state.cfg)
                    f.write('</div>')
                else:
                    f.write('<p>No CFG</p>')
                f.write('</div>')
                # FIXME: *changes* to state are more interesting
            f.write("""
      </div>
    </div>
  </div>
</div>
            """)

            write_html_footer(f)

def have_any_precise_counts(tus):
    for tu in tus:
        for record in tu.records:
            if isinstance(record, Record):
                if record.count:
                    if record.count.is_precise():
                        return True

def filter_non_precise_counts(tus):
    precise_records = []
    num_filtered = 0
    for tu in tus:
        for record in tu.records:
            if isinstance(record, Record):
                if record.count:
                    if not record.count.is_precise():
                        num_filtered += 1
                        continue
            precise_records.append(record)
    log('  purged %i non-precise records' % num_filtered)
    return precise_records

def analyze_counts(tus):
    """
    Get the highest count, purging any non-precise counts
    if we have any precise counts.
    """
    log(' analyze_counts')

    if have_any_precise_counts(tus):
        records = filter_non_precise_counts(tus)

    highest_count = 0
    for tu in tus:
        for record in tu.records:
            if isinstance(record, Record):
                if record.count:
                    value = record.count.value
                    if value > highest_count:
                        highest_count = value

    return highest_count

def make_html(build_dir, out_dir, tus):
    log('make_html')

    if not os.path.exists(out_dir):
        os.mkdir(out_dir)

    highest_count = analyze_counts(tus)
    log(' highest_count=%r' % highest_count)

    make_index_html(out_dir, tus, highest_count)
    make_per_source_file_html(build_dir, out_dir, tus, highest_count)
    make_per_function_html(build_dir, out_dir, tus)

############################################################################

SGR_START = "\33["
SGR_END   = "m\33[K"

def SGR_SEQ(str):
    return SGR_START + str + SGR_END

SGR_RESET = SGR_SEQ("")

COLOR_SEPARATOR  = ";"
COLOR_BOLD       = "01"
COLOR_FG_GREEN   = "32"
COLOR_FG_CYAN    = "36"

def with_color(color, text):
    if os.isatty(sys.stdout.fileno()):
        return SGR_SEQ(color) + text + SGR_RESET
    else:
        return text

def remark(text):
    return with_color(COLOR_FG_GREEN + COLOR_SEPARATOR  + COLOR_BOLD, text)

def note(text):
    return with_color(COLOR_BOLD + COLOR_SEPARATOR + COLOR_FG_CYAN, text)

def bold(text):
    return with_color(COLOR_BOLD, text)

def print_as_remark(record):
    msg = ''
    loc = record.location
    if loc:
        msg += bold('%s: ' % loc)
        msg += remark('remark: ')
    for item in record.message:
        if isinstance(item, str):
            msg += item
        elif isinstance(item, Expr):
            msg += "'" + bold(item.expr) + "'"
        elif isinstance(item, Stmt):
            msg += "'" + bold(item.stmt) + "'"
        elif isinstance(item, SymtabNode):
            msg += "'" + bold(str(item)) + "'"
        else:
            raise TypeError('unknown message item: %r' % item)
    if record.pass_:
        msg += ' [' + remark('pass=%s' % record.pass_.name) + ']'
    if record.count:
        msg += (' ['
                + note('count(%s)=%i'
                       % (record.count.quality, record.count.value))
                + ']')
    print(msg)

############################################################################

def filter_records(tus):
    def criteria(record):
        if isinstance(record, State):
            return True
        # Hack to filter things a bit:
        if record.location:
            src_file = record.location.file
            if 'pgen.c' in src_file:
                return False
        if record.pass_:
            if record.pass_.name in ('slp', 'fre', 'pre', 'profile',
                                     'cunroll', 'cunrolli', 'ivcanon'):
                return False
        return True
    for tu in tus:
        tu.records = list(filter(criteria, tu.records))

def summarize_records(tus):
    log('records by pass:')
    num_records_by_pass = Counter()
    for tu in tus:
        for record in tu.get_records():
            #print(record)
            if record.pass_:
                num_records_by_pass[record.pass_.name] += 1
    for pass_,count in num_records_by_pass.most_common():
        log(' %s: %i' % (pass_, count))

def main(build_dir, out_dir):
    tus = find_records(build_dir)

    summarize_records(tus)

    filter_records(tus)

    summarize_records(tus)
    if 0:
        for tu in tus:
            for record in tu.records:
                print_as_remark(record)
    if 0:
        for tu in tus:
            for record in tu.records:
                print(record)
    make_html(build_dir, out_dir, tus)

main(sys.argv[1], sys.argv[2])
