import json
import unittest
from pathlib import Path

from tests.support import CabinetCase, require_ok


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DayTests(CabinetCase):
    def site_options(self):
        config = json.loads((PROJECT_ROOT / 'run.json').read_text(encoding='utf-8'))
        self.sample = json.loads((PROJECT_ROOT / config['sample']).read_text(encoding='utf-8'))
        return {
            'cabinet_id': self.sample['installation']['cabinet_id'],
            'grant_key': config['grant_key'].encode('utf-8'),
            'receipt_key': config['receipt_key'].encode('utf-8'),
        }

    def test_day(self):
        installation = self.sample['installation']
        for endpoint in (self.site.desk, self.site.kiosk):
            self.assertEqual(require_ok(endpoint.post('/cabinets', installation)), installation)
        small, wide = [require_ok(self.site.desk.post('/grants', body)) for body in self.sample['works']]
        assigned = [small['slot_id'], wide['slot_id']]
        self.assertEqual(assigned, ['B', 'wide'])

        self.site.desk.stop()
        small_deposit = self.site.deposit(small)
        small_pickup = self.site.pickup(small_deposit)
        wide_deposit = self.site.deposit(wide)
        wide_pickup = self.site.pickup(wide_deposit)
        self.assertEqual([small_pickup['slot_id'], wide_pickup['slot_id']], assigned)

        self.site.desk.start()
        self.assertEqual(self.site.reconcile(small, pickup=small_pickup)['status'], 'pending')
        closed = self.site.reconcile(small, deposit=small_deposit)
        self.assertEqual(closed['closure'], {'deposit_id': small_deposit['deposit_id'], 'pickup_id': small_pickup['pickup_id']})
        self.assertEqual(self.site.reconcile(wide, wide_deposit, wide_pickup)['status'], 'closed')

        self.site.desk.restart()
        self.site.kiosk.restart()
        next_grant = require_ok(self.site.desk.post('/grants', self.sample['next_work']))
        historical = self.site.status(small)
        downstream_expected = {'old_status': 'closed', 'old_receipts_preserved': True, 'next_slot': 'B', 'new_grant': True}
        downstream_actual = {
            'old_status': historical['status'],
            'old_receipts_preserved': (
                historical['credential'] == small['credential']
                and historical['deposit_receipt'] == small_deposit['deposit_receipt']
                and historical['pickup_receipt'] == small_pickup['pickup_receipt']
            ),
            'next_slot': next_grant['slot_id'],
            'new_grant': next_grant['grant_id'] != small['grant_id'],
        }
        self.assertEqual(downstream_actual, downstream_expected)
        self.assertEqual(self.site.complete(next_grant)[2]['status'], 'closed')
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'N7', 'input': self.sample, 'expected': ['B', 'wide'], 'actual': assigned,
            'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
            'code_paths': ['cabinet/desk/allocation.py', 'cabinet/pickup/redeem.py', 'cabinet/settle/reconcile.py', 'cabinet/settle/status.py'],
            'oracle': 'B precedes A at width 4 and beats the wider slot. A six-unit work only fits wide. After both receipts are verified the old B grant stays readable and B is first choice again.',
        }, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
