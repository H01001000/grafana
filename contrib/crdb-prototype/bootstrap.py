"""Prepare a fresh, disposable CRDB schema from stock Grafana 13.2.3 on PostgreSQL."""
from pathlib import Path
import concurrent.futures, json, re, subprocess, sys, time, urllib.request
ROOT=Path(__file__).resolve().parent
LOG=ROOT/'logs'; LOG.mkdir(exist_ok=True)
BASE=['docker','--context','desktop-linux','compose','-f',str(ROOT/'compose.yaml')]
def dc(*args, data=None):
    return subprocess.check_output(BASE+list(args),input=data,stderr=subprocess.STDOUT)
def psql(query, target='crdb'):
    host=['-h','crdb','-p','26257'] if target=='crdb' else []
    return dc('exec','-T','pg','psql',*host,'-U','grafana','-d','grafana','-v','ON_ERROR_STOP=1','-At',data=query.encode())
def statements(text):
    quote=None; start=0; i=0; line=False; block=False
    while i<len(text):
        c=text[i]; pair=text[i:i+2]
        if line:
            if c=='\n': line=False
        elif block:
            if pair=='*/': block=False; i+=1
        elif quote:
            if c==quote:
                if text[i+1:i+2]==quote: i+=1
                else: quote=None
        elif pair=='--': line=True; i+=1
        elif pair=='/*': block=True; i+=1
        elif c in "'\"": quote=c
        elif c==';':
            yield text[start:i+1]; start=i+1
        i+=1
    if text[start:].strip(): yield text[start:]
def strip_comments(text):
    return re.sub(r'^\s*--[^\n]*(?:\n|$)', '',text,flags=re.M).strip()

dc('up','-d','pg','crdb','bootstrap')
running=dc('ps','--services','--filter','status=running').decode().splitlines()
if any(n in running for n in ['grafana-a','grafana-b']):
    raise RuntimeError('Stop both Grafana instances before manual bootstrap.')
for attempt in range(60):
    try:
        with urllib.request.urlopen('http://127.0.0.1:13400/api/health',timeout=5) as response: health=json.loads(response.read())
        if health.get('database')=='ok': break
    except Exception: pass
    time.sleep(2)
else: raise RuntimeError('PostgreSQL bootstrap did not become healthy')
if health['version']!='13.2.3': raise RuntimeError('Bootstrap must use the pinned Grafana 13.2.3 release')
(LOG/'source-health.json').write_text(json.dumps(health,indent=2))
dc('stop','bootstrap')
for kind,flags in [('schema',['--schema-only']),('data',['--data-only','--column-inserts'])]:
    (ROOT/(kind+'-pg.sql')).write_bytes(dc('exec','-T','pg','pg_dump','-U','grafana','-d','grafana','--no-owner','--no-privileges',*flags))
subprocess.run([sys.executable,str(ROOT/'translate_dump.py')],check=True)
init="CREATE USER IF NOT EXISTS grafana; CREATE DATABASE IF NOT EXISTS grafana; ALTER DATABASE grafana OWNER TO grafana; ALTER ROLE grafana SET autocommit_before_ddl=off; ALTER ROLE grafana SET create_table_with_schema_locked=off;"
(LOG/'init-crdb.txt').write_bytes(dc('exec','-T','crdb','./cockroach','sql','--insecure','--execute',init))
if psql("SELECT count(*) FROM information_schema.tables WHERE table_schema='public';").strip()!=b'0':
    raise RuntimeError('Target has existing tables; bootstrap only accepts a fresh disposable database.')
schema=(ROOT/'schema-crdb.sql').read_text(encoding='utf-8')
# Inline the already-final primary keys to avoid online rowid-to-PK rewrites on empty tables.
primary={}
pattern=r'ALTER TABLE ONLY public\.(\S+)\s+ADD CONSTRAINT (\S+) PRIMARY KEY \((.*?)\);'
for match in re.finditer(pattern,schema,re.S): primary[match[1]]=match[2]+' PRIMARY KEY ('+match[3]+')'
schema=re.sub(pattern,'',schema,flags=re.S)
def inline(match):
    name=match[1]; body=match[2]
    if name in primary: body+=',\n    CONSTRAINT '+primary[name]
    return 'CREATE TABLE public.'+name+' (\n'+body+'\n);'
schema=re.sub(r'CREATE TABLE public\.(\S+) \(\n(.*?)\n\);',inline,schema,flags=re.S)
index_groups={}; other=[]
for statement in statements(schema):
    clean=strip_comments(statement)
    if not clean: continue
    match=re.match(r'CREATE (?:UNIQUE )?INDEX .*? ON public\.(\S+) USING ',clean,re.S)
    if match: index_groups.setdefault(match[1],[]).append(clean)
    else: other.append(clean)
(LOG/'schema-base.txt').write_bytes(psql('\n'.join(other)))
def indexes(item):
    table,sql=item
    return table,psql('\n'.join(sql)).decode(errors='replace')
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results=dict(pool.map(indexes,index_groups.items()))
(LOG/'schema-indexes.json').write_text(json.dumps(results,indent=2))
(ROOT/'bootstrap-schema-optimized.sql').write_bytes(schema.encode())
(LOG/'data-import.txt').write_bytes(psql((ROOT/'data-crdb.sql').read_text(encoding='utf-8')))
subprocess.run([sys.executable,str(ROOT/'verify_transfer.py')],check=True)
print('PASS: pinned schema and records transferred; no Grafana migrations run on CRDB.',flush=True)
if '--prepare-only' not in sys.argv:
    dc('up','-d','grafana-a','grafana-b')
