from flask import Flask, render_template

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
