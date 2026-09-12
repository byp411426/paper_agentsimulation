"""Lossless reading copy of an anonymous case; repeated values point backwards.

No event, field, message or reasoning is selected or discarded. The original case
remains the evidence source. Round-trip equality is checked before a copy is written.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

MARKER='$same_as_earlier_json_pointer'


def pointer(parent, key):
    return parent+'/'+str(key).replace('~','~0').replace('/','~1')


def compact(value):
    seen={}
    def walk(obj, path):
        if isinstance(obj,dict) and MARKER in obj:
            raise ValueError('Reserved marker already occurs in original data')
        key=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        if len(key)>=160 and key in seen:
            return {MARKER:seen[key]}
        if isinstance(obj,dict):
            result={k:walk(v,pointer(path,k)) for k,v in obj.items()}
        elif isinstance(obj,list):
            result=[walk(v,pointer(path,i)) for i,v in enumerate(obj)]
        else:
            result=obj
        if len(key)>=160:
            seen[key]=path
        return result
    result=walk(value,'#')
    assert restore(result)==value, 'Lossless reading copy did not reconstruct original'
    return result


def restore(value):
    prior={}
    def walk(obj,path):
        if isinstance(obj,dict) and set(obj)=={MARKER}:
            result=deepcopy(prior[obj[MARKER]])
        elif isinstance(obj,dict):
            result={k:walk(v,pointer(path,k)) for k,v in obj.items()}
        elif isinstance(obj,list):
            result=[walk(v,pointer(path,i)) for i,v in enumerate(obj)]
        else:
            result=obj
        prior[path]=result
        return result
    return walk(value,'#')


def write_copy(source,destination):
    if destination.exists():
        raise FileExistsError(destination)
    raw=source.read_bytes()
    obj=json.loads(raw)
    copy=compact(obj)
    destination.write_text(json.dumps(copy,ensure_ascii=False,separators=(',',':'))+'\n')
    return {'case_file':source.name,'case_sha256':hashlib.sha256(raw).hexdigest(),
        'reading_copy':destination.name,'reading_copy_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
        'exact_round_trip':True,'original_bytes':len(raw),'reading_bytes':destination.stat().st_size}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source',type=Path);ap.add_argument('destination',type=Path)
    args=ap.parse_args();print(json.dumps(write_copy(args.source,args.destination)))


if __name__=='__main__':
    main()
