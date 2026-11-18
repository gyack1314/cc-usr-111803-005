"""只读重放合成的来源交互并展示当前接收状态。"""
import argparse
import json
from .transport import Replay
from .ledger import connect,receive
from .view import overview,order_overview

def _replay(db, collection, manifest_path):
    replay=Replay(manifest_path)
    for step in replay.steps:
        request=step['request']
        raw,receipt=replay.request(request['method'],request['url'])
        receive(db,collection,raw,receipt)
    document=json.loads(open(manifest_path,encoding='utf-8').read())
    return document.get('sources',[])

def main():
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['inspect','orders'])
    p.add_argument('manifests',nargs='+')
    args=p.parse_args()
    db=connect(':memory:')
    collection='pork-005'
    expectations=[]
    for manifest in args.manifests:
        expectations.extend(_replay(db,collection,manifest))
    if args.command=='inspect':
        view=overview(db,collection)
    else:
        view=order_overview(db,collection,expectations)
    print(json.dumps(view,ensure_ascii=False,indent=2))
    db.close()

if __name__=='__main__':main()
