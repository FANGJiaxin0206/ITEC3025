"""Local task measurements. Click counts are observations, not a click-through rate."""
import csv
import io
import json
import math
import re
from .core import atomic_json
from .intake_store import _LOCK, _moment


class EvaluationLog:
    def __init__(self,path):self.path=path
    def _load(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {'tasks':{}}
    def photo(self,task_id,event_id=None):
        if not isinstance(task_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}',task_id):
            return None
        with _LOCK:
            store=self._load();task=store['tasks'].get(task_id)
            if not task:
                task={'task_id':task_id,'event_id':event_id,'started_at':_moment(None).isoformat(),
                      'status':'in_progress','photos':[],'clicks':{},'click_rate':None,'click_rate_definition':'Not yet defined'}
                store['tasks'][task_id]=task
            if task['status']!='in_progress':return None
            task['photos'].append({'at':_moment(None).isoformat(),'result':'processing'})
            atomic_json(self.path,store)
        return task_id
    def result(self,task_id,result):
        with _LOCK:
            store=self._load();task=store['tasks'].get(task_id)
            if not task or not task['photos']:return
            task['photos'][-1]['result']=result
            atomic_json(self.path,store)
    def clicks(self,payload):
        if not isinstance(payload,dict):return
        with _LOCK:
            store=self._load();task=store['tasks'].get(payload.get('task_id'))
            if not task:return
            clicks=payload.get('clicks',[])
            if not isinstance(clicks,list):return
            for click in clicks[:100]:
                if not isinstance(click,dict):continue
                try:
                    offset=float(click.get('offset_ms',-1))
                    if not math.isfinite(offset) or not 0<=offset<=86400000:continue
                    if task.get('client_duration_ms') is not None and offset>task['client_duration_ms']:continue
                    key=str(click['id'])[:80];button=str(click['button'])[:80]
                except (ValueError,TypeError,KeyError):continue
                task['clicks'].setdefault(key,{'button':button,'offset_ms':offset,'page':str(click.get('page',''))[:40],'verification_status':str(click.get('verification_status',''))[:30]})
            atomic_json(self.path,store)
    def finish(self,task_id,status,elapsed_ms=None,now=None):
        with _LOCK:
            store=self._load();task=store['tasks'].get(task_id)
            if not task or task['status']!='in_progress':return
            from datetime import datetime
            moment=now or _moment(None);task['status']=status;task['ended_at']=moment.isoformat()
            task['server_duration_seconds']=round((moment-datetime.fromisoformat(task['started_at'])).total_seconds(),3)
            try:
                elapsed=float(elapsed_ms)
                if math.isfinite(elapsed) and 0<=elapsed<=86400000:task['client_duration_ms']=elapsed
            except (TypeError,ValueError):pass
            task['photo_count']=len(task['photos']);task['click_count']=len(task['clicks'])
            atomic_json(self.path,store)
    def csv(self):
        with _LOCK:tasks=list(self._load()['tasks'].values())
        stream=io.StringIO();fields=['task_id','event_id','status','started_at','ended_at','server_duration_seconds','client_duration_ms','photo_count','click_count','click_rate','click_rate_definition']
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader()
        for task in tasks:writer.writerow({**task,'photo_count':len(task['photos']),'click_count':len(task['clicks'])})
        return stream.getvalue()
