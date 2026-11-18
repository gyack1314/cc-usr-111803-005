"""按订单与回执身份核对履约量：修订、迟到回执、重复接收与历史周报。"""
import json
import tempfile
import unittest
from pathlib import Path
from capture_service.transport import Replay
from capture_service.ledger import connect, receive
from capture_service.view import order_overview
from capture_service.archive import release_fulfillment, get as get_released
from capture_service.domain import fulfillment, normalize_expectations

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
COLLECTION = 'pork-005'


def manifest_sources(name):
    return json.loads((DATA / name).read_text(encoding='utf-8')).get('sources', [])


def replay_into(db, *names):
    expectations = []
    for name in names:
        path = DATA / name
        replay = Replay(path)
        for step in replay.steps:
            request = step['request']
            raw, receipt = replay.request(request['method'], request['url'])
            receive(db, COLLECTION, raw, receipt)
        expectations.extend(manifest_sources(name))
    return expectations


def po7(view):
    return next(order for order in view['orders'] if order['order_id'] == 'PO-7')


class FulfillmentLifecycle(unittest.TestCase):
    def test_initial_state_is_collected_100_and_complete(self):
        db = connect(':memory:')
        expectations = replay_into(db, 'order-initial.json')
        view = order_overview(db, COLLECTION, expectations)
        order = po7(view)
        self.assertTrue(order['verifiable'])
        self.assertEqual(order['heads_requested'], 100)
        self.assertEqual(order['heads_received'], 100)
        self.assertEqual(order['heads_pending'], 0)
        self.assertTrue(order['complete'])
        self.assertEqual(order['status'], '已收齐')
        self.assertEqual(order['order_version'], 'v1')
        self.assertEqual({r['receipt_no']: (r['version'], r['heads_received']) for r in order['receipts']},
                         {'R-A': ('v1', 60), 'R-B': ('v1', 40)})
        db.close()

    def test_order_v2_first_keeps_old_receipts_provisional_and_not_complete(self):
        db = connect(':memory:')
        expectations = replay_into(db, 'order-initial.json', 'order-pending.json', 'order-page-v2.json')
        view = order_overview(db, COLLECTION, expectations)
        order = po7(view)
        self.assertFalse(order['verifiable'])
        self.assertEqual(order['heads_requested'], 95)
        self.assertIsNone(order['heads_received'])
        self.assertIsNone(order['heads_pending'])
        self.assertEqual(order['status'], '尚不能核定')
        self.assertFalse(order['complete'])
        self.assertEqual(order['heads_provisional'], 100)
        gap = next(g for g in order['gaps'] if g['kind'] == 'trade_receipt')
        self.assertEqual(gap['id'], 'trade_receipt-R-A')
        self.assertEqual(gap['expected_revision'], 'v2')
        r_a = next(r for r in order['receipts'] if r['receipt_no'] == 'R-A')
        self.assertTrue(r_a['provisional'])
        r_b = next(r for r in order['receipts'] if r['receipt_no'] == 'R-B')
        self.assertFalse(r_b['provisional'])
        db.close()

    def test_late_receipt_v2_updates_received_90_and_pending_5(self):
        db = connect(':memory:')
        expectations = replay_into(db, 'order-initial.json', 'order-pending.json',
                                   'order-page-v2.json', 'order-complete.json')
        view = order_overview(db, COLLECTION, expectations)
        order = po7(view)
        self.assertTrue(order['verifiable'])
        self.assertEqual(order['heads_requested'], 95)
        self.assertEqual(order['heads_received'], 90)
        self.assertEqual(order['heads_pending'], 5)
        self.assertEqual(order['status'], '待接收')
        self.assertFalse(order['complete'])
        r_a = next(r for r in order['receipts'] if r['receipt_no'] == 'R-A')
        self.assertEqual(r_a['version'], 'v2')
        self.assertEqual(r_a['heads_received'], 50)
        self.assertEqual(r_a['superseded_versions'], ['v1'])
        r_b = next(r for r in order['receipts'] if r['receipt_no'] == 'R-B')
        self.assertEqual(r_b['version'], 'v1')
        self.assertEqual(r_b['heads_received'], 40)
        self.assertEqual(r_b['superseded_versions'], [])
        self.assertEqual(order['superseded_order_versions'], ['v1'])
        self.assertEqual(order['gaps'], [])
        db.close()

    def test_duplicate_reception_does_not_inflate_received(self):
        db = connect(':memory:')
        expectations = replay_into(db, 'order-initial.json', 'order-pending.json',
                                   'order-page-v2.json', 'order-complete.json')
        # 整组清单重复读取，含 R-A、R-B 的再次接收
        replay_into(db, 'order-complete.json', 'order-initial.json')
        view = order_overview(db, COLLECTION, expectations)
        order = po7(view)
        self.assertEqual(order['heads_received'], 90)
        self.assertEqual(order['heads_pending'], 5)
        self.assertEqual(len(order['receipts']), 2)
        raw_count = db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]
        entity_count = db.execute('SELECT COUNT(*) FROM entities').fetchone()[0]
        self.assertEqual(raw_count, 5)
        self.assertEqual(entity_count, 5)
        db.close()

    def test_historical_weekly_report_reproduces_100_with_two_v1_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            db = connect(Path(directory) / 'state.sqlite3')
            initial_expectations = replay_into(db, 'order-initial.json')
            revision = release_fulfillment(db, COLLECTION, initial_expectations)
            # 发布后继续接收修订
            replay_into(db, 'order-pending.json', 'order-page-v2.json', 'order-complete.json')
            snapshot = get_released(db, COLLECTION, revision)
            order = next(o for o in snapshot['orders'] if o['order_id'] == 'PO-7')
            self.assertEqual(order['heads_requested'], 100)
            self.assertEqual(order['heads_received'], 100)
            self.assertEqual(order['heads_pending'], 0)
            self.assertTrue(order['complete'])
            self.assertEqual({r['receipt_no']: r['version'] for r in order['receipts']},
                             {'R-A': 'v1', 'R-B': 'v1'})
            current = po7(order_overview(db, COLLECTION,
                                         initial_expectations + manifest_sources('order-complete.json')))
            self.assertEqual(current['heads_received'], 90)
            self.assertEqual(current['heads_pending'], 5)
            db.close()

    def test_lot_or_session_mismatch_cannot_be_attached_to_po7(self):
        db = connect(':memory:')
        expectations = replay_into(db, 'order-initial.json', 'order-mismatch.json')
        view = order_overview(db, COLLECTION, expectations)
        order = po7(view)
        self.assertEqual(order['heads_received'], 100)
        excluded_nos = {item['receipt_no'] for item in order['excluded_receipts']}
        self.assertEqual(excluded_nos, {'R-C', 'R-D'})
        for item in order['excluded_receipts']:
            self.assertTrue(item['reasons'])
        counted = {r['receipt_no'] for r in order['receipts']}
        self.assertEqual(counted, {'R-A', 'R-B'})
        db.close()

    def test_catalog_gap_makes_pending_undeterminable_not_zero(self):
        db = connect(':memory:')
        expectations = replay_into(db, 'order-initial.json', 'order-pending.json',
                                   'order-page-v2.json', 'order-complete.json',
                                   'order-catalog-gap.json')
        view = order_overview(db, COLLECTION, expectations)
        order = po7(view)
        self.assertFalse(order['verifiable'])
        self.assertIsNone(order['heads_received'])
        self.assertIsNone(order['heads_pending'])
        self.assertEqual(order['heads_provisional'], 90)
        gap = next(g for g in order['gaps'] if g['kind'] == 'procurement_page')
        self.assertEqual(gap['expected_revision'], 'v3')
        self.assertIn('缺页', gap['reason'])
        db.close()

    def test_missing_order_page_is_reported_as_gap(self):
        db = connect(':memory:')
        # 只有回执，没有任何订单页面：消费订单请求但不入库，模拟目录缺页
        expectations = manifest_sources('order-initial.json')
        replay = Replay(DATA / 'order-initial.json')
        for index, step in enumerate(replay.steps):
            request = step['request']
            raw, receipt = replay.request(request['method'], request['url'])
            if index == 0:
                continue
            receive(db, COLLECTION, raw, receipt)
        view = order_overview(db, COLLECTION, expectations)
        order = po7(view)
        self.assertFalse(order['verifiable'])
        self.assertIsNone(order['heads_requested'])
        self.assertIsNone(order['heads_pending'])
        self.assertTrue(any(g['kind'] == 'procurement_page' for g in order['gaps']))
        db.close()

    def test_conflicting_same_version_replay_is_rejected(self):
        db = connect(':memory:')
        replay = Replay(DATA / 'conflict.json')
        first = replay.steps[0]['request']
        raw, receipt = replay.request(first['method'], first['url'])
        receive(db, COLLECTION, raw, receipt)
        before = order_overview(db, COLLECTION)
        second = replay.steps[1]['request']
        other, other_receipt = replay.request(second['method'], second['url'])
        with self.assertRaises(ValueError):
            receive(db, COLLECTION, other, other_receipt)
        self.assertEqual(order_overview(db, COLLECTION), before)
        db.close()

    def test_expectation_normalization_keeps_latest_revision(self):
        sources = (manifest_sources('order-initial.json')
                   + manifest_sources('order-pending.json'))
        normalized = {(item['kind'], item['id']): item['expected_revision']
                      for item in normalize_expectations(sources)}
        self.assertEqual(normalized[('procurement_page', 'procurement_page-PO-7')], 'v2')
        self.assertEqual(normalized[('trade_receipt', 'trade_receipt-R-A')], 'v2')
        self.assertEqual(normalized[('trade_receipt', 'trade_receipt-R-B')], 'v1')

    def test_fulfillment_without_catalog_still_counts_valid_versions(self):
        db = connect(':memory:')
        replay_into(db, 'order-complete.json', 'order-initial.json', 'order-page-v2.json')
        view = order_overview(db, COLLECTION)
        order = po7(view)
        self.assertTrue(order['verifiable'])
        self.assertEqual(order['heads_received'], 90)
        self.assertEqual(order['heads_pending'], 5)
        db.close()


if __name__ == '__main__':
    unittest.main()
