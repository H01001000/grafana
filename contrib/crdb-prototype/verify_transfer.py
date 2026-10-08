from pathlib import Path
import re,subprocess,json,hashlib
root=Path(__file__).resolve().parent
compose=str(root/'compose.yaml')
base=['docker','--context','desktop-linux','compose','-f',compose,'exec','-T','pg','psql','-U','grafana','-d','grafana','-At','-v','ON_ERROR_STOP=1']
def sql(query,target):
    args=base+(['-h','crdb','-p','26257'] if target=='crdb' else [])+['-c',query]
    r=subprocess.run(args,capture_output=True,text=True,encoding='utf-8')
    if r.returncode: raise RuntimeError(r.stderr)
    return r.stdout.strip()
tables=re.findall(r'^CREATE TABLE public\.(\S+) \(', (root/'schema-pg.sql').read_text(encoding='utf-8-sig'),re.M)
counts=' UNION ALL '.join("SELECT '"+table.replace("'","''")+"' AS table_name, count(*) AS rows FROM public."+table for table in tables)
source=sql(counts,'pg'); target=sql(counts,'crdb')
source_map=dict(line.split('|',1) for line in source.splitlines())
target_map=dict(line.split('|',1) for line in target.splitlines())
result={'tables':len(tables),'allTableRowCountsMatch':source_map==target_map,'sourceRows':source_map,'targetRows':target_map,'migrationTables':{}}
indexes="SELECT tablename||'|'||indexname FROM pg_indexes WHERE schemaname='public' ORDER BY tablename,indexname"
source_indexes=set(sql(indexes,'pg').splitlines()); target_indexes=set(sql(indexes,'crdb').splitlines())
result['sourceIndexCount']=len(source_indexes)
result['missingSourceIndexes']=sorted(source_indexes-target_indexes)
result['extraTargetIndexes']=sorted(target_indexes-source_indexes)
for table in ['migration_log','resource_migration_log','secret_migration_log','unifiedstorage_migration_log']:
    query='SELECT json_agg(t) FROM (SELECT migration_id,sql,success,error FROM '+table+' ORDER BY migration_id) t'
    a=json.loads(sql(query,'pg')); b=json.loads(sql(query,'crdb'))
    # PG locale ordering differs from CRDB default ordering; compare by identity.
    a=sorted(a or [],key=lambda r:r['migration_id']); b=sorted(b or [],key=lambda r:r['migration_id'])
    result['migrationTables'][table]={'rows':len(a or []),'recordsMatch':a==b,'sha256':hashlib.sha256(json.dumps(a,sort_keys=True).encode()).hexdigest()}
(root/'logs'/'transfer-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
assert result['allTableRowCountsMatch'], 'Table row counts differ'
assert not result['missingSourceIndexes'], 'Missing source indexes'
assert all(v['recordsMatch'] for v in result['migrationTables'].values()),'Migration records differ'
print(json.dumps({k:v for k,v in result.items() if k not in ['sourceRows','targetRows']},indent=2))
