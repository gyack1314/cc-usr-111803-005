"""按本项目约定展示已接收资料与明确缺口。"""
from .ledger import entities
from .domain import assess, fulfillment

def overview(c,collection):
    rows=entities(c,collection)
    result=assess(rows)
    result['collection']=collection
    result['records']=[{'type':r['type'],'id':r['id'],'version':r['version'],'source_sha256':r['source']} for r in rows]
    return result

def order_overview(c,collection,expectations=None):
    """当前订单履约状态：每个回执身份只计有效版本，缺口显式标注为不能核定。"""
    rows=entities(c,collection)
    result=fulfillment(rows,expectations)
    result['collection']=collection
    result['records']=[{'type':r['type'],'id':r['id'],'version':r['version'],'source_sha256':r['source']} for r in rows]
    return result
