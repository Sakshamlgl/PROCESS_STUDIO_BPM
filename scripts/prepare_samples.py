"""Rebuild documented examples with the same application service used by the UI."""
import json
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'backend'))
import store
from service import dispatch

samples={
 'onboarding':'user: Receive application\nservice: Verify identity\nif Application approved?\nparallel\nuser: Prepare contract\nbranch\nservice: Open account\nendparallel\nuser: Welcome customer\nelse\nuser: Explain rejection\nendif\nservice: Archive application',
 'procurement':'user[Requester]: Submit requisition\nuser[Finance]: Approve budget\nparallel\nuser[Procurement]: Evaluate supplier\nbranch\nservice[Operations]: Check stock availability\nendparallel\nuser[Procurement]: Issue purchase order\nuser[Operations]: Confirm receipt\nuser[Finance]: Reconcile invoice\nservice[Finance]: Schedule payment',
 'insurance':'user: Register claim\nservice: Check policy coverage\nif Covered by policy?\nuser: Assess damage\nif Investigation needed?\nuser: Investigate claim\nelse\nservice: Calculate settlement\nendif\nuser: Approve settlement\nelse\nuser: Explain rejection\nendif\nservice: Close claim'
}
results={}
with tempfile.TemporaryDirectory() as directory:
 db=Path(directory)/'samples.sqlite';store.migrate(db)
 for name,source in samples.items():
  compiled=dispatch(db,'POST','/api/compile',{'source':source,'name':name.title()})[1]
  family=dispatch(db,'POST','/api/families',{'source':source,'name':name.title(),'xml':compiled['xml'],'generation':compiled['generation']})[1]
  family=dispatch(db,'POST','/api/variant',{'family':family['id'],'revision':1,'name':'Additional review','context':{'Segment':'Business'},'operations':[{'id':'Compliance','action':'insert','target':'N2','name':'Review compliance','type':'userTask'}]})[1]
  backup=dispatch(db,'GET','/api/families/'+family['id']+'/backup')[1]
  (ROOT/'samples'/f'{name}.txt').write_text(source,encoding='utf-8')
  (ROOT/'samples'/f'{name}.bpmn').write_text(compiled['xml'],encoding='utf-8')
  (ROOT/'samples'/f'{name}-family.json').write_text(json.dumps(backup,indent=2),encoding='utf-8')
  results[name]=compiled['analysis']
(ROOT/'samples/analysis-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print('Prepared',len(results),'independent workflows and restorable process families.')
