from pathlib import Path
import re, subprocess, json
root=Path(__file__).resolve().parent
schema=(root/'schema-pg.sql').read_text(encoding='utf-8-sig')
data=(root/'data-pg.sql').read_text(encoding='utf-8-sig')
changes=[]
def strip_prologue(s, is_schema):
    # pg_dump session directives and psql safety markers are outside SQL string data.
    s=re.sub(r'^\\(?:un)?restrict[^\n]*\n?', '', s, flags=re.M)
    if is_schema:
        s=re.sub(r'^SET [^;]+;\s*', '', s, flags=re.M)
        s=re.sub(r"^SELECT pg_catalog.set_config\([^;]+;\s*", '', s, flags=re.M)
    else:
        first=s.find('INSERT INTO ')
        prefix=s[:first]
        prefix=re.sub(r'^SET [^;]+;\s*', '', prefix, flags=re.M)
        prefix=re.sub(r"^SELECT pg_catalog.set_config\([^;]+;\s*", '', prefix, flags=re.M)
        s=prefix+s[first:]
    return s
schema=strip_prologue(schema,True)
data=strip_prologue(data,False)
# OWNED BY is PostgreSQL sequence dependency metadata, not sequence values/defaults.
schema,n=re.subn(r'^ALTER SEQUENCE [^;]+ OWNED BY [^;]+;\s*','',schema,flags=re.M)
changes.append({'change':'remove PostgreSQL sequence OWNED BY metadata','count':n})
schema,n=re.subn(r' COLLATE pg_catalog."C"', '', schema)
changes.append({'change':'replace PostgreSQL C collation with CRDB default string comparison','count':n})
(root/'schema-crdb.sql').write_bytes(schema.encode('utf-8'))
(root/'data-crdb.sql').write_bytes(data.encode('utf-8'))
(root/'translation.json').write_text(json.dumps(changes,indent=2),encoding='utf-8')
print('Prepared schema and data; sequences and migration records retained.')
