"""Verify startup refuses missing bootstrap records without executing migrations."""
from pathlib import Path
import json,subprocess
ROOT=Path(__file__).resolve().parent; LOG=ROOT/'logs'; LOG.mkdir(exist_ok=True)
BASE=['docker','--context','desktop-linux','compose','-f',str(ROOT/'compose.yaml')]
def sql(query,dbname='grafana'):
 return subprocess.check_output(BASE+['exec','-T','pg','psql','-h','crdb','-p','26257','-U','grafana','-d',dbname,'-qAt','-v','ON_ERROR_STOP=1','-c',query]).decode().strip()
def run_guard(name,dbname):
 result=subprocess.run(BASE+['run','--rm','--no-deps','-e','GF_DATABASE_NAME='+dbname,'grafana-a'],capture_output=True,text=True,encoding='utf-8',timeout=40)
 (LOG/(name+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
 assert result.returncode!=0,result.stdout
 assert 'manual CRDB bootstrap required' in result.stdout+result.stderr,result.stdout+result.stderr
 return result.returncode
subprocess.run(BASE+['exec','-T','crdb','./cockroach','sql','--insecure','--execute','CREATE DATABASE IF NOT EXISTS grafana_empty; ALTER DATABASE grafana_empty OWNER TO grafana;'],check=True,capture_output=True)
empty=run_guard('guard-empty','grafana_empty')
assert sql("SELECT count(*) FROM information_schema.tables WHERE table_schema='public';",'grafana_empty')=='0'
marker='Change key_path collation of nats_discovery_peers in postgres'
row=json.loads(sql("SELECT row_to_json(migration_log) FROM migration_log WHERE migration_id='"+marker+"';"))
sql("DELETE FROM migration_log WHERE migration_id='"+marker+"';")
try:
 missing=run_guard('guard-missing-record','grafana')
 assert sql("SELECT count(*) FROM migration_log WHERE migration_id='"+marker+"';")=='0'
finally:
 def literal(v):
  if v is None:return 'NULL'
  if isinstance(v,bool):return 'true' if v else 'false'
  if isinstance(v,(int,float)):return str(v)
  return "'"+str(v).replace("'","''")+"'"
 columns=','.join('"'+k+'"' for k in row)
 sql('INSERT INTO migration_log ('+columns+') VALUES ('+','.join(literal(v) for v in row.values())+');')
(LOG/'startup-guards.json').write_text(json.dumps({'emptyDatabaseExit':empty,'emptyDatabaseTablesCreated':0,'missingRecordExit':missing,'missingRecordWasNotRecreatedByGrafana':True,'originalRecordRestored':True},indent=2))
print('PASS: empty and incomplete bootstrap states refused, with no automatic migration writes.')
