from tests.support import CabinetCase, read_rows, simultaneous


class DeliveryTests(CabinetCase):
    def test_offline_pickup(self):
        self.site.install(('only', 4))
        grant = self.site.issue('evening', 4)
        self.site.desk.stop()
        deposit = self.site.deposit(grant)
        pickup = self.site.pickup(deposit)
        self.assertEqual((deposit['grant_id'], deposit['slot_id']), (grant['grant_id'], 'only'))
        self.assertEqual((pickup['deposit_id'], pickup['slot_id']), (deposit['deposit_id'], 'only'))
        self.assertEqual(self.site.deposit(grant), deposit)
        self.assertEqual(self.site.pickup(deposit), pickup)
        self.site.desk.start()
        self.assertEqual(self.site.reconcile(grant, deposit, pickup)['status'], 'closed')
        self.assertEqual(self.site.status(grant)['credential'], grant['credential'])

    def test_concurrent_actions(self):
        self.site.install(('only', 4))
        grant = self.site.issue('concurrent', 4)
        deposits = simultaneous(*(lambda: self.site.deposit(grant) for _ in range(2)))
        self.assertEqual(deposits[0], deposits[1])
        self.assertEqual(read_rows(self.site.kiosk, 'SELECT deposit_id FROM current_deposits'), [(deposits[0]['deposit_id'],)])
        pickups = simultaneous(*(lambda: self.site.pickup(deposits[0]) for _ in range(2)))
        self.assertEqual(pickups[0], pickups[1])
        self.assertEqual(read_rows(self.site.kiosk, 'SELECT deposit_id FROM deposit_receipts'), [(deposits[0]['deposit_id'],)])
        self.assertEqual(read_rows(self.site.kiosk, 'SELECT pickup_id FROM pickup_receipts'), [(pickups[0]['pickup_id'],)])
        self.assertEqual(read_rows(self.site.kiosk, 'SELECT deposit_id FROM current_deposits'), [])

    def test_pickup_without_match(self):
        self.site.install(('only', 4))
        deposit = self.site.deposit(self.site.issue('waiting', 4))
        result = self.site.kiosk.post('/pickups', {'pickup_ticket': 'never-issued'})
        self.assertEqual(result, (409, {'error': 'pickup_not_found'}))
        self.assertEqual(read_rows(self.site.kiosk, 'SELECT deposit_id FROM current_deposits'), [(deposit['deposit_id'],)])
        self.assertEqual(read_rows(self.site.kiosk, 'SELECT pickup_id FROM pickup_receipts'), [])
        self.assertEqual(self.site.pickup(deposit)['deposit_id'], deposit['deposit_id'])

    def test_wrong_cabinet(self):
        other = self.site.add_kiosk('annex')
        self.site.install(('west', 4), cabinet_id='annex')
        self.site.install(('east', 4))
        grant = self.site.issue('main', 4)
        self.assertEqual(other.post('/deposits', {'credential': grant['credential']}), (409, {'error': 'wrong_cabinet'}))
        for endpoint in (other, self.site.kiosk):
            self.assertEqual(read_rows(endpoint, 'SELECT deposit_id FROM current_deposits'), [])
        self.assertEqual(self.site.deposit(grant)['slot_id'], 'east')

    def test_same_slot_other_cabinet(self):
        other = self.site.add_kiosk('annex')
        self.site.install(('A', 4), cabinet_id='annex')
        self.site.install(('A', 4))
        grant = self.site.issue('home', 4)
        self.assertEqual(other.post('/deposits', {'credential': grant['credential']}), (409, {'error': 'wrong_cabinet'}))
        self.assertEqual(read_rows(other, 'SELECT grant_id FROM deposit_receipts'), [])
        self.assertEqual(read_rows(self.site.kiosk, 'SELECT grant_id FROM deposit_receipts'), [])
        deposit = self.site.deposit(grant)
        self.assertEqual((deposit['cabinet_id'], deposit['slot_id']), (self.site.cabinet_id, 'A'))

    def test_old_pickup_after_reuse(self):
        self.site.install(('only', 4))
        old = self.site.issue('old', 4)
        old_deposit, old_pickup, _ = self.site.complete(old)
        new = self.site.issue('new', 4)
        new_deposit = self.site.deposit(new)
        self.assertEqual(self.site.pickup(old_deposit), old_pickup)
        self.assertEqual(read_rows(self.site.kiosk, 'SELECT deposit_id FROM current_deposits'), [(new_deposit['deposit_id'],)])
        self.assertEqual(self.site.pickup(new_deposit)['grant_id'], new['grant_id'])

    def test_deposit_retry_after_reuse(self):
        self.site.install(('only', 4))
        old = self.site.issue('old', 4)
        old_deposit, _, _ = self.site.complete(old)
        new = self.site.issue('new', 4)
        withheld = self.site.kiosk.hold_request('/deposits', {'credential': old['credential']})
        new_deposit = self.site.deposit(new)
        self.assertEqual(withheld.release(), (200, old_deposit))
        self.assertEqual(read_rows(self.site.kiosk, 'SELECT grant_id FROM current_deposits'), [(new['grant_id'],)])
        self.assertEqual(self.site.pickup(new_deposit)['deposit_id'], new_deposit['deposit_id'])

    def test_pickup_distinct_receipts(self):
        self.site.install(('only', 4))
        old_deposit, old_pickup, _ = self.site.complete(self.site.issue('old', 4))
        new_deposit = self.site.deposit(self.site.issue('new', 4))
        self.assertNotEqual(old_deposit['pickup_ticket'], new_deposit['pickup_ticket'])
        new_pickup = self.site.pickup(new_deposit)
        self.assertNotEqual(old_pickup['pickup_id'], new_pickup['pickup_id'])
        self.assertEqual(new_pickup['deposit_id'], new_deposit['deposit_id'])
        self.assertEqual(old_pickup['deposit_id'], old_deposit['deposit_id'])
        self.assertEqual(self.site.pickup(old_deposit), old_pickup)
        self.assertEqual(self.site.pickup(new_deposit), new_pickup)
        self.assertEqual(read_rows(self.site.kiosk, 'SELECT deposit_id FROM current_deposits'), [])
