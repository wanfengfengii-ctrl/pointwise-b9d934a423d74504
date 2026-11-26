"""Replay the documented partition change against both HTTP services."""
import json
import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import quote

from tests.support import Site


class PartitionDay(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix="cabinet-partition-")
        self.addCleanup(directory.cleanup)
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        self.site = Site(directory.name)
        self.addCleanup(self.site.stop)
        self.kiosk = self.site.add_kiosk(self.site.cabinet_id)
        self.desk = self.site.desk
        self.start_desk()

    def start_desk(self):
        host, port = self.kiosk.server.server_address
        os.environ["CABINET_PARTITION_PEERS"] = json.dumps({self.site.cabinet_id: f"http://{host}:{port}"})
        self.desk.start()

    def outcome(self, result, status, fields=None):
        code, body = result
        self.assertEqual(code, status, body)
        for name, value in (fields or {}).items():
            self.assertEqual(body.get(name), value, body)
        return body

    def order(self, request_id, shape):
        return {"cabinet_id": self.site.cabinet_id, "request_id": request_id, "target_shape": shape}

    def lookup(self, order):
        ids = [quote(order[key], safe="") for key in ("cabinet_id", "request_id")]
        return self.desk.get("/partitions/" + "/".join(ids))

    def begin(self, order):
        pending = self.outcome(self.desk.post("/partitions", order), 202, {**order, "status": "pending"})
        authorization = pending.get("authorization")
        self.assertIsInstance(authorization, str)
        self.assertTrue(authorization)
        return authorization

    def confirmation(self, order, authorization, observed_shape):
        return {"cabinet_id": order["cabinet_id"], "request_id": order["request_id"],
                "observed_shape": observed_shape, "authorization": authorization}

    def install_receipt(self, order, result):
        body = self.outcome(result, 200, {**order, "status": "installed"})
        receipt = body.get("installation_receipt")
        self.assertIsInstance(receipt, str)
        self.assertTrue(receipt)
        return receipt

    def finalize(self, order, receipt):
        result = self.desk.post("/partitions", {**order, "installation_receipt": receipt})
        self.assertEqual(self.install_receipt(order, result), receipt)

    def test_partition_day(self):
        site = self.site
        form = {**site.install_body(("F", 4), ("L", 4), ("R", 4)), "partitionable": True}
        for endpoint in (self.desk, self.kiosk):
            self.outcome(endpoint.post("/cabinets", form), 200, form)
        fixed = site.issue("fixed", 4)
        self.assertEqual(fixed["slot_id"], "F")
        left_form = site.grant_body("left", 4)
        held_grant = self.desk.hold_response("/grants", left_form)
        self.assertEqual(held_grant.status, 200)
        blocked = self.desk.post("/partitions", self.order("blocked-issued", "merged"))
        self.outcome(blocked, 409)
        left = self.outcome(self.desk.post("/grants", left_form), 200, {"slot_id": "L"})
        self.assertEqual(left, held_grant.observed_body)
        left_deposit = site.deposit(left)
        left_pickup = site.pickup(left_deposit)
        self.assertEqual(site.reconcile(left, pickup=left_pickup)["status"], "pending")
        self.outcome(self.desk.post("/partitions", self.order("blocked-unsettled", "merged")), 409)
        self.assertEqual(site.reconcile(left, deposit=left_deposit)["status"], "closed")
        left_history = site.status(left)

        merge = self.order("merge", "merged")
        merge_authorization = self.begin(merge)
        merge_confirm = self.confirmation(merge, merge_authorization, "merged")
        still_blocked = self.desk.post("/grants", site.grant_body("early", 4))
        self.outcome(still_blocked, 409)
        self.desk.stop()
        fixed_deposit = site.deposit(fixed)
        fixed_pickup = site.pickup(fixed_deposit)
        self.assertEqual(fixed_pickup["slot_id"], "F")
        self.start_desk()

        held_install = self.kiosk.hold_response("/partitions", merge_confirm)
        original_receipt = self.install_receipt(merge, (held_install.status, held_install.observed_body))
        self.desk.stop()
        self.kiosk.restart()
        self.start_desk()
        pending = self.outcome(self.lookup(merge), 202, {**merge, "status": "pending"})
        self.assertEqual(pending.get("authorization"), merge_authorization)
        wide_form = site.grant_body("wide", 6)
        self.outcome(self.desk.post("/grants", wide_form), 409)
        recovered_receipt = self.install_receipt(merge, self.kiosk.post("/partitions", merge_confirm))
        self.assertEqual(recovered_receipt, original_receipt)
        self.finalize(merge, recovered_receipt)
        wide = self.outcome(self.desk.post("/grants", wide_form), 200, {"slot_id": "M"})
        wide_deposit = site.deposit(wide)
        self.assertEqual(wide_deposit["slot_id"], "M")
        self.assertEqual(site.deposit(left), left_deposit)
        self.assertEqual(site.pickup(left_deposit), left_pickup)
        self.assertEqual(site.status(left), left_history)
        wide_pickup = site.pickup(wide_deposit)
        self.assertEqual(wide_pickup["slot_id"], "M")
        self.assertEqual(site.reconcile(wide, wide_deposit, wide_pickup)["status"], "closed")

        split = self.order("split", "split")
        split_authorization = self.begin(split)
        mistaken = self.confirmation(split, split_authorization, "merged")
        self.outcome(self.kiosk.post("/partitions", mistaken), 409)
        self.outcome(self.desk.post("/partitions", {**split, "installation_receipt": recovered_receipt}), 409)
        self.outcome(self.lookup(split), 202, {**split, "status": "pending"})
        correct = self.confirmation(split, split_authorization, "split")
        split_receipt = self.install_receipt(split, self.kiosk.post("/partitions", correct))
        self.finalize(split, split_receipt)
        self.assertEqual(self.install_receipt(merge, self.desk.post("/partitions", merge)), recovered_receipt)
        self.assertEqual(self.install_receipt(merge, self.kiosk.post("/partitions", merge_confirm)), recovered_receipt)
        self.outcome(self.desk.post("/partitions", {**merge, "target_shape": "split"}), 409)
        too_wide = self.desk.post("/grants", site.grant_body("wide-after-split", 6))
        self.outcome(too_wide, 409)
        small = site.issue("small-after-split", 4)
        small_deposit, small_pickup, small_closed = site.complete(small)
        self.assertEqual((small["slot_id"], small_deposit["slot_id"], small_pickup["slot_id"]), ("L", "L", "L"))
        self.assertEqual(small_closed["status"], "closed")
        print("POINTWISE_SCENARIO " + json.dumps({
            "case_id": "partition-day", "unseen_grant_blocks": blocked[0],
            "variable_issue_while_pending": still_blocked[0], "offline_pickup": fixed_pickup["slot_id"],
            "reopened_status_before_receipt": pending["status"], "merged_issue": wide["slot_id"],
            "merged_pickup": wide_pickup["slot_id"], "split_wide_rejection": too_wide[0],
            "split_pickup": small_pickup["slot_id"],
        }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
