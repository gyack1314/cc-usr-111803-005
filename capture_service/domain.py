"""解析来源身份及本项目公开资料字段。"""
import json
import re
from pathlib import Path
CONTRACT=json.loads((Path(__file__).resolve().parents[1]/'docs'/'source-contract.json').read_text(encoding='utf-8'))
def decode(raw,receipt):
    doc=json.loads(raw.decode('utf-8'))
    if not all(k in doc for k in ('kind','id','revision')): raise ValueError('资料身份缺失')
    kind=doc['kind']
    if kind not in CONTRACT['roles']: raise ValueError('未知来源类型')
    if any(k not in doc for k in CONTRACT['required_fields'][kind]): raise ValueError('来源业务字段缺失')
    return [{'type':kind,'id':doc['id'],'version':doc['revision'],'payload':{k:v for k,v in doc.items() if k not in ('kind','id','revision')}}]
def assess(rows):
    """按当前双来源契约核对候选关联；后续来源事件仍待业务解释。"""
    left=sorted((r for r in rows if r['type']==CONTRACT['roles'][0]),key=lambda r:r['version'])
    right=sorted((r for r in rows if r['type']==CONTRACT['roles'][1]),key=lambda r:r['version'])
    pairs=[]
    for first in left:
        for second in right:
            a,b=first['payload'],second['payload']
            if a['lot']==b['lot'] and a['session']==b['session'] and b['state']=='accepted':
                pairs.append({'left_id':first['id'],'left_version':first['version'],
                              'right_id':second['id'],'right_version':second['version'],
                              'left_source':first['source'],'right_source':second['source']})
    return {'publishable':bool(pairs),'reasons':[] if pairs else ['同场次批号已有正式回执'],
            'received_types':sorted({r['type'] for r in rows}),
            'received_versions':len(rows),'matched_pairs':pairs,
            'candidate_relations':sorted({str(r['payload'].get(CONTRACT['relation_field'])) for r in rows})}

_ORDER_KIND=CONTRACT['roles'][0]
_RECEIPT_KIND=CONTRACT['roles'][1]
_VERSION_RE=re.compile(r'v?(\d+)$',re.IGNORECASE)

def version_key(version):
    """版次先后：v1 < v2；非标准版次退化为字符串序，绝不与整数混排。"""
    match=_VERSION_RE.fullmatch(str(version))
    return (0,int(match.group(1))) if match else (1,str(version))

def _latest(entity_rows):
    return max(entity_rows,key=lambda row:version_key(row['version']))

def normalize_expectations(manifest_sources):
    """把待采登记（url+kind+expected_revision）归并为订单/回执身份期望。"""
    expectations={}
    for item in manifest_sources or []:
        entity_id=item['url'].rstrip('/').split('/')[-1]
        kind=item['kind']
        if kind not in CONTRACT['roles']:raise ValueError('未知来源类型')
        key=(kind,entity_id)
        revision=item.get('expected_revision')
        prior=expectations.get(key)
        if prior is None or revision is not None and (prior.get('expected_revision') is None
               or version_key(revision)>version_key(prior['expected_revision'])):
            expectations[key]={'kind':kind,'id':entity_id,'expected_revision':revision,
                               'required':bool(item.get('required',True))}
    return list(expectations.values())

def fulfillment(rows, expectations=None):
    """按 order_id 与 receipt_no 计算当前履约量。

    同一订单或同一回执只取版次最高的有效版本；旧版仅保留为历史，不重复计入成交。
    回执与订单的 lot/session/order_id 必须一致且回执 state=accepted 才可归属。
    待采目录登记的版本仍未取得时，当前量不能核定，待收量明确返回 None 而不是零。
    """
    expected={}
    for item in normalize_expectations(expectations):
        expected.setdefault(item['kind'],{})[item['id']]=item
    expected_orders=expected.get(_ORDER_KIND,{})
    expected_receipts=expected.get(_RECEIPT_KIND,{})

    orders={}
    for row in rows:
        if row['type']!=_ORDER_KIND:continue
        payload=row['payload']
        order_id=payload.get('order_id')
        if order_id is None:continue
        orders.setdefault(order_id,[]).append(row)

    receipts={}
    for row in rows:
        if row['type']!=_RECEIPT_KIND:continue
        payload=row['payload']
        order_id=payload.get('order_id')
        receipt_no=payload.get('receipt_no')
        if order_id is None or receipt_no is None:continue
        receipts.setdefault((order_id,receipt_no),[]).append(row)

    order_views=[]
    all_order_ids=set(orders)|{payload_id.split('procurement_page-',1)[-1]
                               for payload_id in expected_orders}
    for order_id in sorted(all_order_ids):
        versions=sorted(orders.get(order_id,()),key=lambda row:version_key(row['version']))
        order_expect=next((item for item in expected_orders.values()
                           if item['id'].split('procurement_page-',1)[-1]==order_id),None)
        if not versions:
            order_views.append({'order_id':order_id,'verifiable':False,'status':'尚不能核定',
                'heads_requested':None,'heads_received':None,'heads_pending':None,'complete':False,
                'order_version':None,'receipts':[],
                'gaps':[{'kind':_ORDER_KIND,'id':order_expect['id'] if order_expect else 'procurement_page-'+order_id,
                         'expected_revision':order_expect['expected_revision'] if order_expect else None,
                         'reason':'订单资料目录缺页'}],
                'excluded_receipts':[]})
            continue
        current_order=_latest(versions)
        order_payload=current_order['payload']
        gaps=[]
        if order_expect is not None and order_expect['expected_revision'] is not None and \
                version_key(current_order['version'])<version_key(order_expect['expected_revision']):
            gaps.append({'kind':_ORDER_KIND,'id':current_order['id'],
                         'expected_revision':order_expect['expected_revision'],
                         'reason':'资料目录缺页：订单新版尚未取得，当前订单不能按旧版核定'})

        receipt_views=[]
        excluded=[]
        for (rid,receipt_no),group in sorted(receipts.items(),key=lambda item:item[0][1]):
            if rid!=order_id:continue
            line=sorted(group,key=lambda row:version_key(row['version']))
            current=_latest(line)
            payload=current['payload']
            receipt_expect=expected_receipts.get(current['id'])
            stale_catalog=(receipt_expect is not None and receipt_expect['expected_revision'] is not None
                           and version_key(current['version'])<version_key(receipt_expect['expected_revision']))
            if stale_catalog:
                gaps.append({'kind':_RECEIPT_KIND,'id':current['id'],
                             'expected_revision':receipt_expect['expected_revision'],
                             'reason':'资料目录缺页：回执新版尚未取得，旧版不能继续计作当前成交'})
            reasons=[]
            if payload.get('lot')!=order_payload.get('lot'):reasons.append('lot 与订单不一致')
            if payload.get('session')!=order_payload.get('session'):reasons.append('采购场次与订单不一致')
            if payload.get('state')!='accepted':reasons.append('回执不是正式成交状态')
            if reasons:
                excluded.append({'receipt_no':receipt_no,'id':current['id'],
                                 'version':current['version'],'heads_received':payload.get('heads_received'),
                                 'reasons':reasons})
                continue
            heads=int(payload.get('heads_received',0))
            receipt_views.append({'receipt_no':receipt_no,'id':current['id'],
                'version':current['version'],'heads_received':heads,
                'superseded_versions':[row['version'] for row in line if row is not current],
                'provisional':stale_catalog})

        verifiable=not gaps
        received=sum(item['heads_received'] for item in receipt_views)
        requested=int(order_payload['heads_requested'])
        if verifiable:
            pending=max(0,requested-received)
            status='已收齐' if received>=requested else '待接收'
        else:
            pending=None
            status='尚不能核定'
        order_views.append({'order_id':order_id,'verifiable':verifiable,'status':status,
            'heads_requested':requested,
            'heads_received':received if verifiable else None,
            'heads_provisional':received,
            'heads_pending':pending,
            'complete':verifiable and received>=requested,
            'order_version':current_order['version'],
            'superseded_order_versions':[row['version'] for row in versions if row is not current_order],
            'receipts':receipt_views,'gaps':gaps,'excluded_receipts':excluded})

    unmatched_receipts=[]
    for (order_id,receipt_no),group in sorted(receipts.items(),key=lambda item:item[0][1]):
        if order_id in all_order_ids:continue
        current=_latest(group)
        unmatched_receipts.append({'order_id':order_id,'receipt_no':receipt_no,'id':current['id'],
                                  'version':current['version'],
                                  'heads_received':current['payload'].get('heads_received'),
                                  'reasons':['找不到同 order_id 的有效订单']})
    return {'orders':order_views,'unmatched_receipts':unmatched_receipts}
