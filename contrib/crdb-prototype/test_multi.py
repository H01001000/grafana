"""Cross-instance state/session writes and bounded concurrent API operations."""
from pathlib import Path
import base64,json,urllib.request,urllib.error,http.cookiejar,concurrent.futures,time
ROOT=Path(__file__).resolve().parent; (ROOT/'logs').mkdir(exist_ok=True)
AUTH='Basic '+base64.b64encode(b'admin:disposable-test-only').decode()
RESULTS=[]
def api(node,method,path,body=None,opener=None,auth=True):
 headers={'Content-Type':'application/json'}
 if auth: headers['Authorization']=AUTH
 req=urllib.request.Request('http://127.0.0.1:'+str(13401+node)+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
 try:
  with (opener.open if opener else urllib.request.urlopen)(req,timeout=30) as r: status=r.status; raw=r.read()
 except urllib.error.HTTPError as e: status=e.code; raw=e.read()
 try: value=json.loads(raw)
 except Exception: value=raw.decode(errors='replace')
 RESULTS.append({'node':node,'method':method,'path':path,'status':status,'body':value})
 assert 200<=status<300,(node,status,value)
 return value

def shared_state():
 for node in (0,1):
  assert api(node,'GET','/api/health')['database']=='ok'
  assert api(node,'GET','/api/datasources/uid/rt-datasource')['name']=='Runtime datasource updated'
 jar=http.cookiejar.MozillaCookieJar(str(ROOT/'session.cookies')); jar.load(ignore_discard=True,ignore_expires=True)
 opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
 assert api(1,'GET','/api/user',opener=opener,auth=False)['login']=='runtime-user'
 assert api(1,'GET','/api/user/preferences',opener=opener,auth=False)['theme']=='dark'
 jar.save(ignore_discard=True,ignore_expires=True)
 path=(ROOT/'unified-path.txt').read_text().strip()+'/rt-dashboard'
 doc=api(1,'GET',path); doc['spec']['title']='Written on Grafana B runtime dashboard'
 saved=api(1,'PUT',path,doc)
 deadline=time.time()+15
 while time.time()<deadline:
  read=api(0,'GET',path)
  if read['spec']['title']=='Written on Grafana B runtime dashboard': break
  time.sleep(.5)
 else: raise AssertionError('A did not observe the write from B')
 return {'sharedSession':True,'sharedPreferences':True,'crossInstanceWrite':True,'resourceVersion':saved['metadata']['resourceVersion']}

def concurrent_creates():
 batch=str(time.time_ns())
 def create(n):
  uid='ha-concurrent-'+batch+'-'+str(n)
  body={'dashboard':{'uid':uid,'title':'Concurrent '+str(n),'schemaVersion':41,'version':0,'panels':[]},'folderUid':'rt-folder'}
  api(n%2,'POST','/api/dashboards/db',body)
  return uid
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool: uids=list(pool.map(create,range(40)))
 for n,uid in enumerate(uids):
  assert api((n+1)%2,'GET','/api/dashboards/uid/'+uid)['dashboard']['uid']==uid
 return {'created':len(uids),'readOnOppositeNode':len(uids)}

def applied():
 members=[]
 for node in (0,1):
  response=api(node,'GET','/api/alertmanager/grafana/api/v2/status')
  with urllib.request.urlopen('http://127.0.0.1:'+str(13401+node)+'/metrics',timeout=10) as raw:
   lines=raw.read().decode().splitlines()
  line=next(line for line in lines if line.startswith('grafana_alertmanager_cluster_members '))
  count=float(line.split()[-1]); assert count==2,line
  members.append({'node':node,'clusterMembers':count,'statusApiCluster':response.get('cluster')})
 return members

def main():
 try:
  for name,fn in [('shared state and login cookie',shared_state),('concurrent cross-node dashboard CRUD',concurrent_creates),('Alertmanager gossip membership',applied)]:
   detail=fn(); RESULTS.append({'test':name,'result':'PASS','detail':detail}); print(name,detail,flush=True)
 except Exception as e:
  RESULTS.append({'result':'FAIL','error':str(e)})
  raise
 finally:
  (ROOT/'logs'/'multi-instance.json').write_text(json.dumps(RESULTS,indent=2))

if __name__=="__main__": main()
