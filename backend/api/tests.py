from django.test import SimpleTestCase

from api.services.n8n_workflow_generation import build_heuristic_plan, build_workflow_from_plan
from api.services.workflow_autofix import diagnose_failure


class N8nWorkflowGenerationTests(SimpleTestCase):
    def test_builds_inactive_webhook_draft_with_response_node(self):
        plan = build_heuristic_plan("Receive an invoice webhook and return a summary")
        workflow = build_workflow_from_plan(plan, "Receive an invoice webhook and return a summary", [])

        self.assertEqual(workflow["name"], plan["name"])
        self.assertIn("nodes", workflow)
        self.assertIn("connections", workflow)
        self.assertNotIn("active", workflow)
        self.assertTrue(any(node["type"] == "n8n-nodes-base.webhook" for node in workflow["nodes"]))
        self.assertTrue(any(node["type"] == "n8n-nodes-base.respondToWebhook" for node in workflow["nodes"]))

    def test_schedule_prompt_uses_schedule_trigger(self):
        plan = build_heuristic_plan("Every day fetch reports and prepare a digest")
        workflow = build_workflow_from_plan(plan, "Every day fetch reports and prepare a digest", [])

        self.assertTrue(
            any(node["type"] == "n8n-nodes-base.scheduleTrigger" for node in workflow["nodes"])
        )


class WorkflowAutoFixTests(SimpleTestCase):
    def test_diagnose_failure_uses_top_level_error_node(self):
        workflow = {
            "name": "Broken workflow",
            "nodes": [
                {
                    "name": "HTTP Request",
                    "type": "n8n-nodes-base.httpRequest",
                    "typeVersion": 4,
                    "parameters": {"url": "https://example.com"},
                }
            ],
            "connections": {},
        }
        execution = {
            "data": {
                "resultData": {
                    "lastNodeExecuted": "HTTP Request",
                    "runData": {},
                    "error": {
                        "message": "Bad request",
                        "node": {"name": "HTTP Request"},
                    },
                }
            }
        }

        failure = diagnose_failure(execution, workflow)

        self.assertEqual(failure["node_name"], "HTTP Request")
        self.assertEqual(failure["error_message"], "Bad request")
        self.assertEqual(failure["node_type"], "n8n-nodes-base.httpRequest")
        self.assertEqual(failure["node_parameters"], {"url": "https://example.com"})
