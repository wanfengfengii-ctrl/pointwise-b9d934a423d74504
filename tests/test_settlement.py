from tests.support import CabinetCase, read_rows


class SettlementTests(CabinetCase):
    def test_deposit_only(self):
        self.site.install(('only', 4))
        grant = self.site.issue('held', 4)
        deposit = self.site.deposit(grant)
        partial = self.site.reconcile(grant, deposit=deposit)
        self.assertEqual(partial['status'], 'pending')
        self.assertEqual(partial['deposit_receipt'], deposit['deposit_receipt'])
        self.assertIsNone(partial['pickup_receipt'])
        self.assertIsNone(partial['closure'])
        self.assertEqual(self.site.reconcile(grant, deposit=deposit), partial)
        self.assertEqual(self.site.status(grant)['status'], 'pending')
        self.assertEqual(self.site.desk.post('/grants', self.site.grant_body('later', 4))[0], 409)

    def test_picked_up_before_sync(self):
        self.site.install(('only', 4))
        grant = self.site.issue('held', 4)
        deposit = self.site.deposit(grant)
        pickup = self.site.pickup(deposit)
        self.assertEqual(read_rows(self.site.kiosk, 'SELECT deposit_id FROM current_deposits'), [])
        self.assertEqual(self.site.reconcile(grant, deposit=deposit)['status'], 'pending')
        blocked = self.site.grant_body('later', 4)
        self.assertEqual(self.site.desk.post('/grants', blocked)[0], 409)
        settled = self.site.reconcile(grant, pickup=pickup)
        self.assertEqual(settled['closure'], {'deposit_id': deposit['deposit_id'], 'pickup_id': pickup['pickup_id']})
        self.assertEqual(self.site.issue('later', 4)['slot_id'], 'only')

    def test_pickup_only_then_deposit(self):
        self.site.install(('only', 4))
        grant = self.site.issue('held', 4)
        deposit = self.site.deposit(grant)
        pickup = self.site.pickup(deposit)
        partial = self.site.reconcile(grant, pickup=pickup)
        self.assertEqual(partial['status'], 'pending')
        self.assertIsNone(partial['deposit_receipt'])
        self.assertEqual(partial['pickup_receipt'], pickup['pickup_receipt'])
        self.assertEqual(self.site.status(grant)['pickup_receipt'], pickup['pickup_receipt'])
        self.assertEqual(self.site.reconcile(grant, pickup=pickup), partial)
        self.assertEqual(self.site.desk.post('/grants', self.site.grant_body('later', 4))[0], 409)
        self.site.desk.restart()
        self.assertEqual(self.site.reconcile(grant, deposit=deposit)['status'], 'closed')
        self.assertEqual(self.site.issue('later', 4)['slot_id'], 'only')

    def test_mixed_original_receipts(self):
        self.site.install(('only', 4))
        _, old_pickup, _ = self.site.complete(self.site.issue('old', 4))
        grant = self.site.issue('new', 4)
        deposit = self.site.deposit(grant)
        mixed = self.site.reconcile_body(grant, deposit=deposit, pickup=old_pickup)
        for expected_state in ('issued', 'pending'):
            with self.subTest(expected_state=expected_state):
                if expected_state == 'pending':
                    self.site.reconcile(grant, deposit=deposit)
                before = self.site.status(grant)
                self.assertEqual(before['status'], expected_state)
                self.assertEqual(self.site.desk.post('/reconcile', mixed), (409, {'error': 'receipt_pair_conflict'}))
                self.assertEqual(self.site.status(grant), before)
                self.assertEqual(self.site.desk.post('/grants', self.site.grant_body('later', 4))[0], 409)
        pickup = self.site.pickup(deposit)
        self.assertEqual(self.site.reconcile(grant, deposit, pickup)['closure']['pickup_id'], pickup['pickup_id'])

    def test_reconcile_wrong_cabinet_and_wrong_purpose(self):
        self.site.install(('only', 4))
        grant = self.site.issue('authentic', 4)
        deposit = self.site.deposit(grant)
        pickup = self.site.pickup(deposit)
        initial = self.site.status(grant)
        wrong_cabinet = {**self.site.reconcile_body(grant, deposit, pickup), 'cabinet_id': 'annex'}
        self.assertEqual(self.site.desk.post('/reconcile', wrong_cabinet), (409, {'error': 'wrong_cabinet'}))
        swapped = {'cabinet_id': grant['cabinet_id'], 'deposit_receipt': pickup['pickup_receipt']}
        self.assertEqual(self.site.desk.post('/reconcile', swapped), (409, {'error': 'invalid_evidence'}))
        self.assertEqual(self.site.status(grant), initial)
        self.assertEqual(self.site.reconcile(grant, deposit, pickup)['status'], 'closed')

    def test_reassign_after_restart(self):
        self.site.install(('only', 4))
        old = self.site.issue('old', 4)
        deposit, pickup, closed = self.site.complete(old)
        self.assertEqual(closed['status'], 'closed')
        self.site.desk.restart()
        self.site.kiosk.restart()
        new = self.site.issue('new', 4)
        self.assertEqual(new['slot_id'], old['slot_id'])
        self.assertNotEqual(new['grant_id'], old['grant_id'])
        self.assertEqual(self.site.issue('old', 4), old)
        historical = self.site.status(old)
        self.assertEqual(historical['credential'], old['credential'])
        self.assertEqual(historical['deposit_receipt'], deposit['deposit_receipt'])
        self.assertEqual(historical['pickup_receipt'], pickup['pickup_receipt'])
        self.assertEqual(historical['closure'], closed['closure'])
        self.assertEqual(self.site.deposit(old), deposit)
        self.assertEqual(self.site.pickup(deposit), pickup)
        self.assertEqual(self.site.complete(new)[2]['status'], 'closed')

    def test_replay_reconcile(self):
        self.site.install(('only', 4))
        grant = self.site.issue('old', 4)
        deposit, pickup, closed = self.site.complete(grant)
        self.site.desk.restart()
        self.site.kiosk.restart()
        new = self.site.issue('new', 4)
        self.assertEqual(self.site.reconcile(grant, deposit, pickup), closed)
        self.assertEqual(self.site.reconcile(grant, pickup=pickup), closed)
        self.assertEqual(self.site.status(new)['status'], 'issued')
        self.assertEqual(self.site.desk.post('/grants', self.site.grant_body('third', 4))[0], 409)
        self.assertEqual(read_rows(self.site.desk, 'SELECT grant_id FROM closures'), [(grant['grant_id'],)])

    def test_closed_status_after_reuse(self):
        self.site.install(('only', 4))
        old = self.site.issue('old', 4)
        old_deposit, old_pickup, _ = self.site.complete(old)
        self.site.desk.restart()
        self.site.kiosk.restart()
        new = self.site.issue('new', 4)
        new_deposit = self.site.deposit(new)
        self.site.reconcile(new, deposit=new_deposit)
        old_status = self.site.status(old)
        new_status = self.site.status(new)
        self.assertEqual(old_status['status'], 'closed')
        self.assertEqual(old_status['deposit_receipt'], old_deposit['deposit_receipt'])
        self.assertEqual(old_status['pickup_receipt'], old_pickup['pickup_receipt'])
        self.assertEqual(new_status['status'], 'pending')
        self.assertEqual(new_status['credential'], new['credential'])
        self.assertEqual(new_status['deposit_receipt'], new_deposit['deposit_receipt'])
        self.assertIsNone(new_status['pickup_receipt'])

    def test_unknown_status(self):
        self.site.install(('only', 4))
        grant = self.site.issue('known', 4)
        self.assertEqual(self.site.desk.get('/grants/unknown'), (404, {'error': 'unknown_grant'}))
        self.assertEqual(self.site.status(grant)['grant_id'], grant['grant_id'])
