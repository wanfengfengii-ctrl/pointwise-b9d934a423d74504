import json

from tests.support import CabinetCase, read_rows, require_ok, simultaneous


class IssuanceTests(CabinetCase):
    def test_exact_fit(self):
        layout, _ = self.site.install(('A', 4), ('B', 4))
        body = self.site.grant_body('exact', 4)
        grant = require_ok(self.site.desk.post('/grants', body))
        deposit = self.site.deposit(grant)
        expected = {'slot_id': 'A', 'width': 4}
        actual = {key: grant[key] for key in expected}
        downstream_expected = {'slot_id': 'A', 'same_grant': True}
        downstream_actual = {'slot_id': deposit['slot_id'], 'same_grant': deposit['grant_id'] == grant['grant_id']}
        self.assertEqual(actual, expected)
        self.assertEqual(downstream_actual, downstream_expected)
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'N1', 'input': {'layout': layout, 'grant': body},
            'expected': expected, 'actual': actual,
            'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
            'code_paths': ['cabinet/layout/fit.py', 'cabinet/layout/order.py', 'cabinet/desk/issue.py', 'cabinet/deposit/intake.py'],
            'oracle': 'Two four-unit slots fit exactly. The first installed slot is A, and the same grant must be deposited there.',
        }, ensure_ascii=False), flush=True)

    def test_same_width_order(self):
        self.site.install(('wide', 8), ('B', 4), ('A', 4))
        first = self.site.issue('first', 3)
        second = self.site.issue('second', 3)
        third = self.site.issue('third', 3)
        self.assertEqual([grant['slot_id'] for grant in (first, second, third)], ['B', 'A', 'wide'])

    def test_concurrent_last_slot(self):
        self.site.install(('only', 4))
        bodies = [self.site.grant_body('one', 4), self.site.grant_body('two', 4)]
        results = simultaneous(*(lambda body=body: self.site.desk.post('/grants', body) for body in bodies))
        self.assertEqual(sorted(status for status, _ in results), [200, 409])
        winner = next(index for index, (status, _) in enumerate(results) if status == 200)
        self.assertEqual(self.site.desk.post('/grants', bodies[winner]), results[winner])
        self.assertEqual(read_rows(self.site.desk, 'SELECT request_id, slot_id FROM grants'), [(bodies[winner]['request_id'], 'only')])

    def test_no_fit(self):
        self.site.install(('only', 4))
        too_wide = self.site.grant_body('fit', 5)
        self.assertEqual(self.site.desk.post('/grants', too_wide), (409, {'error': 'no_fitting_slot'}))
        self.assertEqual(self.site.issue('fit', 4)['slot_id'], 'only')

    def test_invalid_width(self):
        invalid = (None, True, False, '4', 4.0, 1.5, 0, -1)
        for endpoint in (self.site.desk, self.site.kiosk):
            for width in invalid:
                with self.subTest(endpoint=endpoint, install_width=width):
                    self.assertEqual(endpoint.post('/cabinets', self.site.install_body(('only', width)))[0], 422)
            body = self.site.install_body(('only', 4))
            del body['slots'][0]['width']
            self.assertEqual(endpoint.post('/cabinets', body)[0], 422)
        self.site.install(('only', 4))
        for width in invalid:
            with self.subTest(grant_width=width):
                self.assertEqual(self.site.desk.post('/grants', self.site.grant_body('invalid', width))[0], 422)
        missing = self.site.grant_body('invalid', 4)
        del missing['width']
        self.assertEqual(self.site.desk.post('/grants', missing)[0], 422)
        self.assertEqual(self.site.issue('invalid', 4)['slot_id'], 'only')

    def test_width_beyond_sqlite_integer_range(self):
        width = 2 ** 80
        self.site.install(('wide', width + 1), ('exact', width))
        self.site.desk.restart()
        self.site.kiosk.restart()
        grant = self.site.issue('large', width)
        self.assertEqual((grant['slot_id'], grant['width']), ('exact', width))
        self.assertEqual(self.site.deposit(grant)['slot_id'], 'exact')

    def test_resample_installation(self):
        original = self.site.install(('only', 4))
        grant = self.site.issue('first', 4)
        deposit = self.site.deposit(grant)
        self.assertEqual(self.site.install(('only', 4)), original)
        changed = self.site.install_body(('only', 5))
        for endpoint in (self.site.desk, self.site.kiosk):
            self.assertEqual(endpoint.post('/cabinets', changed), (409, {'error': 'cabinet_spec_conflict'}))
        self.assertEqual(self.site.status(grant)['credential'], grant['credential'])
        self.assertEqual(self.site.desk.post('/grants', self.site.grant_body('second', 4))[0], 409)
        self.assertEqual(self.site.deposit(grant), deposit)
        self.assertEqual(self.site.pickup(deposit)['deposit_id'], deposit['deposit_id'])

    def test_changed_order(self):
        original = self.site.install(('B', 4), ('A', 4))
        self.assertEqual(self.site.install(('B', 4), ('A', 4)), original)
        swapped = self.site.install_body(('A', 4), ('B', 4))
        for endpoint in (self.site.desk, self.site.kiosk):
            self.assertEqual(endpoint.post('/cabinets', swapped)[0], 409)
        self.assertEqual(self.site.issue('order', 3)['slot_id'], 'B')

    def test_same_request_changed_width(self):
        self.site.install(('only', 4))
        request = self.site.grant_body('one', 3)
        withheld = self.site.desk.hold_response('/grants', request)
        self.assertEqual(withheld.status, 200)
        for changes in ({'width': 4}, {'work_id': 'new-work'}, {'cabinet_id': 'another-cabinet'}):
            with self.subTest(changes=changes):
                self.assertEqual(self.site.desk.post('/grants', {**request, **changes}), (409, {'error': 'request_conflict'}))
        replay = self.site.issue('one', 3)
        self.assertEqual(replay, withheld.observed_body)
        self.assertEqual(replay['width'], 3)
        self.assertEqual(self.site.deposit(replay)['grant_id'], replay['grant_id'])

    def test_issue_replay_after_reopen(self):
        self.site.install(('F', 4), ('L', 4), ('R', 4))
        self.assertEqual(self.site.issue('fixed', 4)['slot_id'], 'F')
        request = self.site.grant_body('left', 4)
        withheld = self.site.desk.hold_response('/grants', request)
        self.assertEqual(withheld.status, 200)
        self.assertEqual(read_rows(self.site.kiosk, 'SELECT grant_id FROM deposit_receipts'), [])
        self.site.desk.restart()
        self.site.kiosk.restart()
        self.assertEqual(self.site.desk.post('/grants', self.site.grant_body('six', 6)), (409, {'error': 'no_fitting_slot'}))
        self.assertEqual(self.site.issue('right', 4)['slot_id'], 'R')
        self.assertEqual(self.site.desk.post('/grants', self.site.grant_body('extra', 4))[0], 409)
        recovered = require_ok(self.site.desk.post('/grants', request))
        self.assertEqual(recovered, withheld.observed_body)
        self.assertEqual(recovered['slot_id'], 'L')
        deposit, pickup, closed = self.site.complete(recovered)
        self.assertEqual((deposit['slot_id'], pickup['slot_id'], closed['status']), ('L', 'L', 'closed'))
