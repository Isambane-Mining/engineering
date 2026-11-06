import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from engineering.controllers import engineering_legals_sharepoint_retry as retry


class TestSharePointRetry(unittest.TestCase):

    def test_unauthorized_user_rejected(self):
        with (
            patch.dict(retry.frappe.__dict__, {
                "session": SimpleNamespace(user="supplier@example.com")
            }),
            patch.object(retry.frappe, "get_roles", return_value=["Supplier"]),
            patch.object(retry.frappe, "throw", side_effect=PermissionError),
        ):
            with self.assertRaises(PermissionError):
                retry._eligible()

    def test_only_permitted_records_queued(self):
        with (
            patch.object(retry, "_authorized"),
            patch.object(retry.frappe, "get_all", return_value=["A", "B"]),
            patch.object(retry.frappe, "get_doc") as get_doc,
            patch.object(retry.frappe, "enqueue") as enqueue,
        ):
            allowed = MagicMock()
            allowed.has_permission.return_value = True

            denied = MagicMock()
            denied.has_permission.return_value = False

            get_doc.side_effect = [allowed, denied]

            result = retry.retry_unsynced_sharepoint(preview=0)

            self.assertEqual(result["queued"], 1)
            enqueue.assert_called_once()
            self.assertEqual(enqueue.call_args.kwargs["docname"], "A")

    def test_preview_does_not_enqueue(self):
        with (
            patch.object(retry, "_eligible", return_value=["A", "B"]),
            patch.object(retry.frappe, "enqueue") as enqueue,
        ):
            result = retry.retry_unsynced_sharepoint(preview=1)
            self.assertEqual(result["eligible"], 2)
            enqueue.assert_not_called()


if __name__ == "__main__":
    unittest.main()
