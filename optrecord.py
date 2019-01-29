# TODO: license
import gzip
import json

class TranslationUnit:
    """Top-level class for containing optimization records"""
    @staticmethod
    def from_filename(filename):
        with gzip.open(filename) as f:
            content = f.read()
        s = content.decode('utf-8')
        root_obj = json.loads(s)
        return TranslationUnit(filename, root_obj)

    def __init__(self, filename, json_obj):
        self.filename = filename
        self.pass_by_id = {}

        # Expect a 3-tuple
        metadata, passes, records = json_obj

        self.format = metadata['format']
        self.generator = Generator(metadata['generator'])
        self.passes = [Pass(obj, self) for obj in passes]
        self.records = [Record(obj, self) for obj in records]

    def __repr__(self):
        return ('TranslationUnit(%r, %r, %r, %r)'
                % (self.filename, self.generator, self.passes, self.records))

    def iter_all_records(self):
        for r in self.records:
            yield r
            for d in r.iter_all_descendants():
                yield d

class Generator:
    """Metadata about what created the file"""
    def __init__(self, json_obj):
        FIELDS = ['name', 'pkgversion', 'version', 'target']
        for field in FIELDS:
            setattr(self, field, json_obj[field])

    def __repr__(self):
        return ('Generator(%r, %r, %r, %r)'
                % (self.name, self.pkgversion, self.version, self.target))

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

    def __str__(self):
        return '%s:%i: %r' % (self.file, self.line, self.function)

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
        self.value = int(json_obj['value'])

    def __repr__(self):
        return ('Count(%r, %r)'
                % (self.quality, self.value))

    def is_precise(self):
        return self.quality in ('precise', 'adjusted')

class Record:
    """A optimization record: success/failure/note"""
    def __init__(self, json_obj, tu):
        self.kind = json_obj['kind']
        if 'pass' in json_obj:
            self.pass_ = tu.pass_by_id[json_obj['pass']]
        else:
            self.pass_ = None
        self.function = json_obj.get('function', None)
        self.impl_location = from_optional_json_field(ImplLocation, json_obj,
                                                      'impl_location')
        self.message = [Item.from_json(obj) for obj in json_obj['message']]
        self.count = from_optional_json_field(Count, json_obj, 'count')
        self.location = from_optional_json_field(Location, json_obj, 'location')
        if 'inlining_chain' in json_obj:
            self.inlining_chain = [InliningNode(obj)
                                   for obj in json_obj['inlining_chain']]
        else:
            self.inlining_chain = None
        self.children = [Record(child, tu)
                         for child in json_obj.get('children', [])]

    def __repr__(self):
        return ('Record(kind=%r, pass_%r, function=%r, impl_location=%r,'
                ' message=%r, count=%r, location=%r, inlining_chain=%r,'
                ' children=%r)'
                % (self.kind, self.pass_, self.function, self.impl_location,
                   self.message, self.count, self.location, self.inlining_chain,
                   self.children))

    def iter_all_descendants(self):
        for c in self.children:
            yield c
            # Recurse:
            for d in c.iter_all_descendants():
                yield d

class InliningNode:
    """A node within an inlining chain"""
    def __init__(self, json_obj):
        self.fndecl = json_obj['fndecl']
        self.site = from_optional_json_field(Location, json_obj, 'site')

    def __repr__(self):
        return ('InliningNode(%r, %r)'
                % (self.fndecl, self.site))

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
        elif 'symtab_node' in json_obj:
            return SymtabNode(json_obj)
        else:
            raise ValueError('unrecognized item: %r' % json_obj)

class Expr(Item):
    """An expression within a message"""
    def __init__(self, json_obj):
        self.expr = json_obj['expr']
        self.location = from_optional_json_field(Location, json_obj, 'location')

    def __str__(self):
        return self.expr

    def __repr__(self):
        return 'Expr(%r, %r)' % (self.expr, self.location)

class Stmt(Item):
    """A statement within a message"""
    def __init__(self, json_obj):
        self.stmt = json_obj['stmt']
        self.location = from_optional_json_field(Location, json_obj, 'location')

    def __str__(self):
        return self.stmt

    def __repr__(self):
        return 'Stmt(%r, %r)' % (self.stmt, self.location)

class SymtabNode(Item):
    """A symbol table node within a message"""
    def __init__(self, json_obj):
        self.node = json_obj['symtab_node']
        self.location = from_optional_json_field(Location, json_obj, 'location')

    def __str__(self):
        return self.node

    def __repr__(self):
        return 'SymtabNode(%r, %r)' % (self.node, self.location)

