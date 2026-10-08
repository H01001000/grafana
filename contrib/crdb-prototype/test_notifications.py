"""Local-only HA webhook deduplication and surviving-node delivery."""
from pathlib import Path
import json,subprocess,time,urllib.request
from test_multi import api,ROOT,RESULTS
BATCH=str(time.time_ns())
BEFORE='before-'+BATCH; AFTER='after-'+BATCH
BASE=['docker','--context','desktop-linux','compose','-f',str(ROOT/'compose.yaml'),'-f',str(ROOT/'acceptance.yaml')]
def events():
 with urllib.request.urlopen('http://127.0.0.1:13403/events',timeout=10) as response: return json.loads(response.read())
def count(phase):
 return sum(any(a.get('labels',{}).get('probe')==phase and a.get('status')=='firing' for a in event.get('alerts',[])) for event in events())
def wait_event(phase):
 end=time.time()+65
 while time.time()<end:
  if count(phase): return
  time.sleep(1)
 raise AssertionError('No local webhook delivered for '+phase)
def rule(phase,node):
 body={'uid':'ha-'+phase,'title':'HA fixture '+phase,'ruleGroup':'ha-prototype-'+BATCH,'folderUID':'rt-folder','condition':'A','data':[{'refId':'A','queryType':'','relativeTimeRange':{'from':0,'to':0},'datasourceUid':'__expr__','model':{'type':'math','expression':'1','refId':'A'}}],'noDataState':'NoData','execErrState':'Error','for':'0s','annotations':{'summary':'local HA prototype acceptance'},'labels':{'test':'ha-prototype-'+BATCH,'probe':phase},'isPaused':False}
 api(node,'POST','/api/v1/provisioning/alert-rules',body)
 return body
try:
 cp={'uid':'ha-fixture-'+BATCH,'name':'HA fixture '+BATCH,'type':'webhook','settings':{'url':'http://webhook-sink:8080/events'},'disableResolveMessage':True}
 api(0,'POST','/api/v1/provisioning/contact-points',cp)
 policy=api(0,'GET','/api/v1/provisioning/policies')
 policy.setdefault('routes',[]).append({'receiver':'HA fixture '+BATCH,'object_matchers':[['test','=','ha-prototype-'+BATCH]],'group_by':['grafana_folder','alertname'],'group_wait':'0s','group_interval':'10s','repeat_interval':'1h'})
 api(0,'PUT','/api/v1/provisioning/policies',policy)
 before=rule(BEFORE,0)
 api(0,'PUT','/api/v1/provisioning/folder/rt-folder/rule-groups/ha-prototype-'+BATCH,{'name':'ha-prototype-'+BATCH,'folderUid':'rt-folder','interval':10,'rules':[before]})
 wait_event(BEFORE)
 print('First local webhook received; checking peer deduplication.',flush=True)
 time.sleep(20)
 assert count(BEFORE)==1,events()
 RESULTS.append({'test':'two-node alert webhook deduplication','result':'PASS','notifications':count(BEFORE)})
 subprocess.run(BASE+['stop','grafana-a'],check=True)
 assert api(1,'GET','/api/health')['database']=='ok'
 after=rule(AFTER,1)
 api(1,'PUT','/api/v1/provisioning/folder/rt-folder/rule-groups/ha-prototype-'+BATCH,{'name':'ha-prototype-'+BATCH,'folderUid':'rt-folder','interval':10,'rules':[before,after]})
 wait_event(AFTER)
 time.sleep(5)
 assert count(AFTER)==1,events()
 RESULTS.append({'test':'surviving B delivers a new firing alert after A stops','result':'PASS','notifications':count(AFTER)})
 print('PASS: one notification with both peers; surviving B delivered after A stopped.',flush=True)
except Exception as error:
 RESULTS.append({'result':'FAIL','error':str(error)})
 raise
finally:
 (ROOT/'logs'/'ha-notifications.json').write_text(json.dumps({'results':RESULTS,'events':events()},indent=2))
 subprocess.run(BASE+['start','grafana-a'],check=True)
