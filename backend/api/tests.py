from django.test import SimpleTestCase

from api.services.n8n_workflow_generation import build_heuristic_plan, build_workflow_from_plan


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
