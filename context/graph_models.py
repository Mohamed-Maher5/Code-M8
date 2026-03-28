"""Graph RAG data models for code context retrieval."""


class Relationship:
    def __init__(self, relat_type, target):
        self.relat_type = relat_type
        self.target = target


class Chunk:
    def __init__(self, name, start_line, end_line, code, relationships=None, docstring=None):
        self.name = name
        self.start_line = start_line
        self.end_line = end_line
        self.code = code
        self.relationships = relationships if relationships is not None else []
        self.docstring = docstring


class File:
    def __init__(self, path, chunks, last_parsed_hash, imports_from=None):
        self.path = path
        self.chunks = chunks
        self.last_parsed_hash = last_parsed_hash
        self.imports_from = imports_from
