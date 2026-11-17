"""Isolated tests for asynchronous PBM AI classification."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from engineering.engineering.doctype.plant_breakdown_or_maintenance import (
    auto_failure_classification as classifier,
    ai_classification_requests as requests,
)
from engineering.engineering.doctype.ai_failure_classification_settings import (
    ai_failure_classification_settings as settings_module,
)


class TestAIClassificationWorker(unittest.TestCase):

    def setUp(self):
        self.reason = "PARK BRAKE IS NOT WORKING"
        self.user = "operator@example.test"
        self.request_id = "TEST-REQUEST-001"

        self.settings = SimpleNamespace(
            enabled=1,
            ollama_endpoint="http://127.0.0.1:11434",
            preferred_model="qwen3:8b",
            request_timeout=45,
            allowed_classifications=[
                SimpleNamespace(
                    failure_classification="Braking System"
                )
            ],
        )

    def run_worker(self, answer=None, error=None):
        pending = {
            "user": self.user,
            "reason": self.reason,
            "status": "Queued",
        }

        opener = MagicMock()

        if error:
            opener.open.side_effect = error

        response = {
            "message": {
                "content": classifier.json.dumps({
                    "classification": answer
                })
            }
        }

        with (
            patch.object(
                requests, "get_request",
                return_value=pending,
            ),
            patch.object(
                requests, "update_request",
            ) as update,
            patch.object(
                classifier.frappe, "get_single",
                return_value=self.settings,
            ),
            patch.object(
                classifier.frappe, "get_all",
                return_value=["Braking System"],
            ),
            patch.object(
                settings_module,
                "validate_ollama_endpoint",
                return_value="http://127.0.0.1:11434",
            ),
            patch.object(
                classifier.urllib.request,
                "build_opener",
                return_value=opener,
            ),
            patch.object(
                classifier.json,
                "load",
                return_value=response,
            ),
            patch.object(
                classifier.frappe,
                "logger",
                return_value=MagicMock(),
            ),
        ):
            classifier._run_classification_job(
                self.request_id,
                self.user,
            )

        return update

    def test_worker_success(self):
        update = self.run_worker("Braking System")

        update.assert_any_call(
            self.request_id,
            self.user,
            status="Completed",
            classification="Braking System",
            model="qwen3:8b",
        )

    def test_worker_no_suggestion(self):
        update = self.run_worker(None)

        update.assert_any_call(
            self.request_id,
            self.user,
            status="No Suggestion",
            classification=None,
            model="qwen3:8b",
        )

    def test_worker_failure(self):
        update = self.run_worker(
            error=TimeoutError("Simulated Ollama timeout")
        )

        update.assert_any_call(
            self.request_id,
            self.user,
            status="Failed",
        )

    def test_queue_creates_temporary_request_only(self):
        with (
            patch.object(
                classifier.frappe,
                "has_permission",
                return_value=True,
            ),
            patch.object(
                classifier.frappe,
                "get_single",
                return_value=self.settings,
            ),
            patch.object(
                classifier.frappe,
                "session",
                SimpleNamespace(user=self.user),
            ),
            patch.object(
                requests,
                "create_request",
                return_value=self.request_id,
            ) as create,
            patch.object(
                classifier.frappe,
                "enqueue",
            ) as enqueue,
        ):
            result = classifier.queue_classification(
                self.reason
            )

        self.assertEqual(
            result,
            {
                "status": "Queued",
                "request_id": self.request_id,
            },
        )

        create.assert_called_once_with(
            self.reason,
            self.user,
        )

        enqueue.assert_called_once()

        self.assertEqual(
            enqueue.call_args.kwargs["queue"],
            "long",
        )


if __name__ == "__main__":
    unittest.main()
