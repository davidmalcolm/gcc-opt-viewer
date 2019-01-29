from flask import Flask, render_template, Markup
import pygments.lexers
import pygments.styles
import pygments.formatters

app = Flask(__name__)

def record_sort_key(record):
    if not record.count:
        return 0
    return -record.count.value

def iter_all_records(app):
    for tu in app.tus:
        for r in tu.iter_all_records():
            yield r

@app.route("/")
def index():
    # Gather all records
    records = list(iter_all_records(app))

    # Sort by highest-count down to lowest-count
    records = sorted(records, key=record_sort_key)

    return render_template('index.html', records=records)

@app.route("/all-tus")
def all_tus():
    return "tus: %r" % app.tus

@app.route("/pass/<passname>")
def pass_(passname):
    # Gather records from the given pass
    records = [r for r in iter_all_records(app)
               if r.pass_.name == passname]

    # Sort by highest-count down to lowest-count
    records = sorted(records, key=record_sort_key)

    return render_template('pass.html',
                           records=records,
                           passname=passname)

@app.route("/sourcefile/<sourcefile>")
def sourcefile(sourcefile):
    # FIXME: this allows arbitrary reading of files on this machine:
    with open(sourcefile) as f:
        code = f.read()

    style = pygments.styles.get_style_by_name('default')
    formatter = pygments.formatters.HtmlFormatter()
    lexer = pygments.lexers.guess_lexer_for_filename(sourcefile, code)

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

    html_lines = [Markup(line) for line in code_as_html.splitlines()]

    return render_template('sourcefile.html',
                           sourcefile=sourcefile,
                           lines=html_lines,
                           css = formatter.get_style_defs())
