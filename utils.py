import os

from optrecord import TranslationUnit, Record, Expr, Stmt, SymtabNode

def log(*args):
    print(*args)

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
            if file_.endswith('.opt-record.json.gz'):
                filename = os.path.join(root, file_)
                log(' reading: %r' % filename)
                tus.append(TranslationUnit.from_filename(filename))

    return tus

def get_effective_result(record):
    if record.kind == 'scope':
        if record.children:
            return get_effective_result(record.children[-1])
    return record.kind
