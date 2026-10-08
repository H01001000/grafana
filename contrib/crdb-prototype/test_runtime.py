import urllib.request, urllib.error, http.cookiejar, base64, json, copy, concurrent.futures, sys, time, threading, os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ROOT=ROOT/os.environ.get('GRAFANA_TEST_SUBDIR','')
(ROOT/'logs').mkdir(parents=True,exist_ok=True)
BASE='http://127.0.0.1:'+os.environ.get('GRAFANA_TEST_PORT','13401')
AUTH='Basic '+base64.b64encode(b'admin:disposable-test-only').decode()
RESULTS=[]
def api(method,path,body=None,opener=None,auth=True):
    headers={'Content-Type':'application/json'}
    if auth: headers['Authorization']=AUTH
    request=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
    try:
        with (opener.open if opener else urllib.request.urlopen)(request,timeout=25) as response:
            raw=response.read(); status=response.status
    except urllib.error.HTTPError as error:
        status=error.code; raw=error.read()
    try: value=json.loads(raw)
    except Exception: value=raw.decode(errors='replace')
    RESULTS.append({'method':method,'path':path,'status':status,'body':value})
    return status,value

def check(name,fn):
    try:
        detail=fn(); result={'test':name,'result':'PASS','detail':detail}
    except Exception as error: result={'test':name,'result':'FAIL','detail':str(error)}
    RESULTS.append(result); print(json.dumps(result),flush=True)

def ok(method,path,body=None,statuses=(200,),**kwargs):
    status,value=api(method,path,body,**kwargs)
    assert status in statuses,(status,value)
    return value

def folder():
    f=ok('POST','/api/folders',{'uid':'rt-folder','title':'Runtime folder'} )
    f=ok('GET','/api/folders/rt-folder'); assert f['title']=='Runtime folder'
    ok('PUT','/api/folders/rt-folder',{'title':'Runtime folder updated','version':f['version']})
    return ok('GET','/api/folders/rt-folder')['title']

def dashboard():
    d={'uid':'rt-dashboard','title':'Runtime dashboard','schemaVersion':41,'version':0,'panels':[],'tags':['crdb-runtime']}
    ok('POST','/api/dashboards/db',{'dashboard':d,'folderUid':'rt-folder','overwrite':False})
    saved=ok('GET','/api/dashboards/uid/rt-dashboard'); assert saved['dashboard']['title']==d['title']
    d=saved['dashboard']; d['title']='Runtime dashboard updated'
    ok('POST','/api/dashboards/db',{'dashboard':d,'folderUid':'rt-folder','overwrite':False})
    return ok('GET','/api/dashboards/uid/rt-dashboard')['dashboard']['title']

def conflict():
    saved=ok('GET','/api/dashboards/uid/rt-dashboard')['dashboard']
    def update(n):
        d=copy.deepcopy(saved); d['title']='Concurrent runtime dashboard '+str(n)
        return api('POST','/api/dashboards/db',{'dashboard':d,'folderUid':'rt-folder','overwrite':False})[0]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: statuses=list(pool.map(update,[1,2]))
    assert 200 in statuses and all(s in (200,409,412) for s in statuses),statuses
    read=ok('GET','/api/dashboards/uid/rt-dashboard')['dashboard']
    assert read['title'] in ('Concurrent runtime dashboard 1','Concurrent runtime dashboard 2'),read
    return {'statuses':statuses,'finalTitle':read['title'],'conflictEnforced':any(s in (409,412) for s in statuses)}

def datasource():
    body={'uid':'rt-datasource','name':'Runtime datasource','type':'prometheus','access':'proxy','url':'http://127.0.0.1:9','basicAuth':True,'basicAuthUser':'disposable','secureJsonData':{'basicAuthPassword':'runtime-secret'}}
    ok('POST','/api/datasources',body)
    read=ok('GET','/api/datasources/uid/rt-datasource'); assert read['secureJsonFields']['basicAuthPassword']
    body['name']='Runtime datasource updated'; body['secureJsonData']={}
    ok('PUT','/api/datasources/uid/rt-datasource',body)
    return ok('GET','/api/datasources/uid/rt-datasource')['name']

def login():
    user=ok('POST','/api/admin/users',{'name':'Runtime User','email':'runtime@example.invalid','login':'runtime-user','password':'runtime-user-test-only'},statuses=(200,))
    jar=http.cookiejar.MozillaCookieJar(str(ROOT/'session.cookies'))
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    ok('POST','/login',{'user':'runtime-user','password':'runtime-user-test-only'},opener=opener,auth=False)
    profile=ok('GET','/api/user',opener=opener,auth=False); assert profile['login']=='runtime-user'
    ok('PUT','/api/user/preferences',{'theme':'dark','timezone':'utc','weekStart':'monday'},opener=opener,auth=False)
    pref=ok('GET','/api/user/preferences',opener=opener,auth=False); assert pref['theme']=='dark'
    jar.save(ignore_discard=True,ignore_expires=True)
    return {'id':user['id'],'cookies':len(jar),'theme':pref['theme']}

def alerting():
    rule={'uid':'rt-alert','title':'Runtime paused expression rule','ruleGroup':'runtime-test','folderUID':'rt-folder','condition':'A','data':[{'refId':'A','queryType':'','relativeTimeRange':{'from':0,'to':0},'datasourceUid':'__expr__','model':{'type':'math','expression':'1','refId':'A'}}],'noDataState':'NoData','execErrState':'Error','for':'1m','annotations':{'summary':'disposable runtime test'},'labels':{'test':'runtime'},'isPaused':True}
    ok('POST','/api/v1/provisioning/alert-rules',rule,statuses=(200,201))
    read=ok('GET','/api/v1/provisioning/alert-rules/rt-alert'); assert read['title']==rule['title']
    rule['title']='Runtime paused expression rule updated'
    ok('PUT','/api/v1/provisioning/alert-rules/rt-alert',rule,statuses=(200,202))
    return ok('GET','/api/v1/provisioning/alert-rules/rt-alert')['title']

def notifications():
    cp={'uid':'rt-contact','name':'Runtime sink','type':'webhook','settings':{'url':'http://127.0.0.1:9'},'disableResolveMessage':True}
    ok('POST','/api/v1/provisioning/contact-points',cp,statuses=(200,202))
    allcp=ok('GET','/api/v1/provisioning/contact-points'); assert any(c['uid']=='rt-contact' for c in allcp)
    policy=ok('GET','/api/v1/provisioning/policies')
    policy['routes']=policy.get('routes',[])+[{'receiver':'Runtime sink','object_matchers':[['test','=','runtime']],'group_by':['grafana_folder','alertname']}]
    ok('PUT','/api/v1/provisioning/policies',policy,statuses=(200,202))
    read=ok('GET','/api/v1/provisioning/policies'); assert any(r['receiver']=='Runtime sink' for r in read['routes'])
    return {'contactPoint':'rt-contact','routingPolicySaved':True}

def unified():
    discovery=ok('GET','/apis/dashboard.grafana.app'); versions=[v['version'] for v in discovery['versions']]
    version='v1beta1' if 'v1beta1' in versions else versions[0]
    path='/apis/dashboard.grafana.app/'+version+'/namespaces/default/dashboards'
    listing=ok('GET',path); assert any(d['metadata']['name']=='rt-dashboard' for d in listing.get('items',[]))
    read=ok('GET',path+'/rt-dashboard'); rv=read['metadata']['resourceVersion']; assert rv
    updated=copy.deepcopy(read); updated['spec']['title']='Unified runtime dashboard'
    write=ok('PUT',path+'/rt-dashboard',updated)
    read2=ok('GET',path+'/rt-dashboard'); assert read2['spec']['title']=='Unified runtime dashboard'
    assert read2['metadata']['resourceVersion']!=rv,(rv,read2['metadata']['resourceVersion'])
    (ROOT/'unified-path.txt').write_text(path)
    return {'path':path,'oldResourceVersion':rv,'newResourceVersion':read2['metadata']['resourceVersion']}

def watch():
    path=(ROOT/'unified-path.txt').read_text()
    obj=ok('GET',path+'/rt-dashboard')
    rv=obj['metadata']['resourceVersion']
    req=urllib.request.Request(BASE+path+'?watch=true&timeoutSeconds=6&resourceVersion='+rv,headers={'Authorization':AUTH})
    events=[]; started=threading.Event()
    def reader():
        with urllib.request.urlopen(req,timeout=12) as response:
            assert response.status==200
            started.set()
            for line in response:
                if line.strip(): events.append(json.loads(line))
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(reader)
        started.wait(2)
        obj['spec']['title']='Watch runtime dashboard'
        write=ok('PUT',path+'/rt-dashboard',obj)
        try:
            future.result(timeout=15)
        except urllib.error.HTTPError as error:
            raw=error.read().decode(errors='replace')
            RESULTS.append({'watchStatus':error.code,'body':raw})
            if error.code==405:
                return {'available':False,'status':405,'detail':'Watch is not supported on this exposed API; compare PostgreSQL control.'}
            raise
    RESULTS.append({'watchEvents':events})
    assert not any(e.get('type')=='ERROR' for e in events),events
    assert any(e.get('type') in ('ADDED','MODIFIED') and e.get('object',{}).get('metadata',{}).get('name')=='rt-dashboard' and e.get('object',{}).get('spec',{}).get('title')=='Watch runtime dashboard' for e in events),events
    return {'events':len(events),'types':[e.get('type') for e in events]}

def persistence():
    health=ok('GET','/api/health'); assert health['database']=='ok'
    d=ok('GET','/api/dashboards/uid/rt-dashboard'); assert 'runtime dashboard' in d['dashboard']['title'].lower()
    f=ok('GET','/api/folders/rt-folder'); assert f['title']=='Runtime folder updated'
    ds=ok('GET','/api/datasources/uid/rt-datasource'); assert ds['name']=='Runtime datasource updated'
    r=ok('GET','/api/v1/provisioning/alert-rules/rt-alert'); assert 'updated' in r['title']
    jar=http.cookiejar.MozillaCookieJar(str(ROOT/'session.cookies')); jar.load(ignore_discard=True,ignore_expires=True)
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    u=ok('GET','/api/user',opener=opener,auth=False); assert u['login']=='runtime-user'
    prefs=ok('GET','/api/user/preferences',opener=opener,auth=False); assert prefs['theme']=='dark'
    return {'version':health['version'],'dashboard':d['dashboard']['title'],'sessionUser':u['login'],'theme':prefs['theme']}

def deletion():
    ok('POST','/api/folders',{'uid':'rt-delete-folder','title':'Disposable delete folder'})
    ok('POST','/api/dashboards/db',{'dashboard':{'uid':'rt-delete-dashboard','title':'Disposable delete dashboard','schemaVersion':41,'version':0,'panels':[]},'folderUid':'rt-delete-folder'})
    ok('DELETE','/api/dashboards/uid/rt-delete-dashboard')
    assert api('GET','/api/dashboards/uid/rt-delete-dashboard')[0]==404
    ok('DELETE','/api/folders/rt-delete-folder')
    assert api('GET','/api/folders/rt-delete-folder')[0]==404
    ok('POST','/api/datasources',{'uid':'rt-delete-source','name':'Disposable delete source','type':'prometheus','access':'proxy','url':'http://127.0.0.1:9'})
    ok('DELETE','/api/datasources/uid/rt-delete-source')
    assert api('GET','/api/datasources/uid/rt-delete-source')[0]==404
    rule=ok('GET','/api/v1/provisioning/alert-rules/rt-alert')
    rule.pop('id',None); rule['uid']='rt-delete-alert'; rule['title']='Disposable delete alert'
    ok('POST','/api/v1/provisioning/alert-rules',rule,statuses=(200,201))
    ok('DELETE','/api/v1/provisioning/alert-rules/rt-delete-alert',statuses=(200,204))
    assert api('GET','/api/v1/provisioning/alert-rules/rt-delete-alert')[0]==404
    return 'Dashboard, folder, datasource, and alert rule deletions verified with 404 reads.'

def expression():
    result=ok('POST','/api/ds/query',{'from':'now-1m','to':'now','queries':[{'refId':'A','datasource':{'uid':'__expr__','type':'__expr__'},'type':'math','expression':'1','intervalMs':1000,'maxDataPoints':10}]})
    a=result['results']['A']; assert not a.get('error'),a
    assert a['frames'],a
    return a

stage=sys.argv[1] if len(sys.argv)>1 else 'create'
if stage=='create':
    for name,fn in [('folder create/read/update',folder),('dashboard create/read/update',dashboard),('concurrent dashboard updates',conflict),('datasource with encrypted credentials',datasource),('user login and session preferences',login),('alert rule create/read/update paused',alerting),('contact point and notification policy',notifications),('unified dashboard resource versions',unified),('unified watch availability',watch),('object deletions',deletion),('server expression evaluation',expression)]: check(name,fn)
elif stage=='concurrency': check('concurrent dashboard updates',conflict)
elif stage=='expression': check('server expression evaluation',expression)
else: check(stage+' persistence and session',persistence)
(ROOT/'logs'/('runtime-'+stage+'.json')).write_text(json.dumps(RESULTS,indent=2),encoding='utf-8')
