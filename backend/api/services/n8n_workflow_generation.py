import json
import re
import uuid
from functools import lru_cache
from pathlib import Path

from api.services.llm import get_ai_service


REPO_ROOT = Path(__file__).resolve().parents[3]
N8N_NODES_DIR = REPO_ROOT / "n8n-engine" / "node_modules" / "n8n-nodes-base" / "dist" / "nodes"
N8N_LANGCHAIN_NODES_DIR = (
    REPO_ROOT / "n8n-engine" / "node_modules" / "@n8n" / "n8n-nodes-langchain" / "dist" / "nodes"
)
NODE_PACKAGE_DIRS = [
    (N8N_NODES_DIR, "n8n-nodes-base"),
    (N8N_LANGCHAIN_NODES_DIR, "@n8n/n8n-nodes-langchain"),
]

CORE_NODE_TYPES = {
    "n8n-nodes-base.manualTrigger",
    "n8n-nodes-base.webhook",
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.respondToWebhook",
    "n8n-nodes-base.httpRequest",
    "n8n-nodes-base.code",
    "n8n-nodes-base.set",
    "n8n-nodes-base.if",
    "n8n-nodes-base.switch",
    "n8n-nodes-base.merge",
    "n8n-nodes-base.stickyNote",
}

COMMON_NODE_HINTS = [
    ("Manual Trigger", "n8n-nodes-base.manualTrigger"),
    ("Webhook", "n8n-nodes-base.webhook"),
    ("Schedule Trigger", "n8n-nodes-base.scheduleTrigger"),
    ("Respond to Webhook", "n8n-nodes-base.respondToWebhook"),
    ("HTTP Request", "n8n-nodes-base.httpRequest"),
    ("Code", "n8n-nodes-base.code"),
    ("Set", "n8n-nodes-base.set"),
    ("If", "n8n-nodes-base.if"),
    ("Switch", "n8n-nodes-base.switch"),
    ("Merge", "n8n-nodes-base.merge"),
    ("Gmail", "n8n-nodes-base.gmail"),
    ("Slack", "n8n-nodes-base.slack"),
    ("Google Sheets", "n8n-nodes-base.googleSheets"),
    ("Google Drive", "n8n-nodes-base.googleDrive"),
    ("Microsoft Outlook", "n8n-nodes-base.microsoftOutlook"),
    ("Microsoft Teams", "n8n-nodes-base.microsoftTeams"),
    ("Notion", "n8n-nodes-base.notion"),
    ("Airtable", "n8n-nodes-base.airtable"),
    ("OpenAI", "n8n-nodes-base.openAi"),
    ("AI Agent", "@n8n/n8n-nodes-langchain.agent"),
    ("Chat Trigger", "@n8n/n8n-nodes-langchain.chatTrigger"),
    ("OpenAI Chat Model", "@n8n/n8n-nodes-langchain.lmChatOpenAi"),
    ("Telegram", "n8n-nodes-base.telegram"),
    ("Discord", "n8n-nodes-base.discord"),
    ("GitHub", "n8n-nodes-base.github"),
    ("Jira", "n8n-nodes-base.jira"),
    ("Postgres", "n8n-nodes-base.postgres"),
    ("MySQL", "n8n-nodes-base.mySql"),
]

N8N_PLAN_PROMPT = """You are an n8n workflow architect for AIMIx.

Create a concise implementation plan for an n8n workflow from the user's request.

Available n8n node types for this instance include:
{node_catalog}

Return ONLY valid JSON with this schema:
{{
  "name": "short workflow name",
  "summary": "one sentence",
  "trigger": {{
    "kind": "webhook|manual|schedule",
    "method": "POST",
    "path": "short-url-safe-path"
  }},
  "steps": [
    {{
      "name": "unique step name",
      "kind": "code|http|integration|set|if|note",
      "nodeType": "exact n8n node type from the list",
      "description": "what this step does",
      "method": "GET",
      "url": "https://example.com",
      "code": "optional JavaScript for a Code node"
    }}
  ],
  "credential_notes": ["credentials the user must connect in n8n"],
  "activation_notes": ["manual configuration or testing notes"]
}}

Rules:
- Use 2 to 7 steps.
- Prefer native integration nodes if available. Use HTTP Request only for custom APIs or unknown services.
- Never include credential values, API keys, passwords, tokens, or secrets.
- If an integration needs credentials or required parameters, still include the node and explain the missing setup in credential_notes or activation_notes.
- JavaScript must be safe pass-through code. Do not fetch external URLs from JavaScript.
- Use webhook trigger when the request says receive/call/webhook/form/API/chat. Use schedule trigger for every/daily/hourly/cron. Otherwise use manual trigger.

User request:
{user_prompt}
"""


class WorkflowGenerationError(Exception):
    pass


def generate_n8n_workflow(prompt):
    prompt = (prompt or "").strip()
    if len(prompt) < 8:
        raise WorkflowGenerationError("Describe the workflow in at least a few words.")

    catalog = discover_local_n8n_node_catalog()
    selected_catalog = select_relevant_nodes(prompt, catalog)
    plan, warning = generate_workflow_plan(prompt, selected_catalog)
    workflow = build_workflow_from_plan(plan, prompt, catalog)

    return {
        "plan": plan,
        "workflow": workflow,
        "warning": warning,
        "node_catalog_size": len(catalog),
        "selected_node_types": [node["type"] for node in selected_catalog],
    }


def generate_workflow_plan(prompt, selected_catalog):
    ai_service, llm, ai_error = get_ai_service()
    if ai_error:
        return build_heuristic_plan(prompt), f"AI provider unavailable: {ai_error}. Created a basic editable draft."

    node_catalog = "\n".join(f"- {node['displayName']}: {node['type']}" for node in selected_catalog)
    ai_prompt = N8N_PLAN_PROMPT.format(node_catalog=node_catalog, user_prompt=prompt)

    try:
        response = ai_service.generate_response(prompt=ai_prompt, llm=llm)
        plan = parse_json_object(response or "")
        if not isinstance(plan, dict):
            raise ValueError("AI response was not a JSON object.")
        return normalize_plan(plan, prompt), ""
    except Exception as exc:
        return build_heuristic_plan(prompt), f"AI plan could not be used: {exc}. Created a basic editable draft."


def parse_json_object(text):
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[index:])
            return parsed
        except json.JSONDecodeError:
            continue
    raise ValueError("No valid JSON object found.")


def build_heuristic_plan(prompt):
    trigger_kind = infer_trigger_kind(prompt)
    name = title_from_prompt(prompt)
    return normalize_plan(
        {
            "name": name,
            "summary": f"Generated workflow draft for: {prompt}",
            "trigger": {
                "kind": trigger_kind,
                "method": "POST",
                "path": slugify(name),
            },
            "steps": [
                {
                    "name": "Prepare Input",
                    "kind": "code",
                    "nodeType": "n8n-nodes-base.code",
                    "description": "Normalize incoming data for the generated workflow.",
                },
                {
                    "name": "Process Request",
                    "kind": "code",
                    "nodeType": "n8n-nodes-base.code",
                    "description": prompt,
                },
            ],
            "credential_notes": [],
            "activation_notes": [
                "Review generated nodes and replace placeholder configuration before activation.",
            ],
        },
        prompt,
    )


def normalize_plan(plan, prompt):
    name = clean_text(plan.get("name")) or title_from_prompt(prompt)
    trigger = plan.get("trigger") if isinstance(plan.get("trigger"), dict) else {}
    trigger_kind = clean_text(trigger.get("kind")).lower()
    if trigger_kind not in {"webhook", "manual", "schedule"}:
        trigger_kind = infer_trigger_kind(prompt)

    method = clean_text(trigger.get("method")).upper() or "POST"
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        method = "POST"

    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    normalized_steps = []
    used_names = set()
    for index, step in enumerate(steps[:7], start=1):
        if not isinstance(step, dict):
            continue
        step_name = clean_text(step.get("name")) or f"Step {index}"
        step_name = unique_name(step_name[:48], used_names)
        normalized_steps.append(
            {
                "name": step_name,
                "kind": normalize_step_kind(step.get("kind")),
                "nodeType": clean_text(step.get("nodeType")),
                "description": clean_text(step.get("description")) or step_name,
                "method": clean_text(step.get("method")).upper() or "GET",
                "url": clean_text(step.get("url")),
                "code": clean_text(step.get("code")),
            }
        )

    if not normalized_steps:
        normalized_steps = build_heuristic_plan(prompt)["steps"]

    return {
        "name": name[:80],
        "summary": clean_text(plan.get("summary")) or f"Generated workflow draft for: {prompt}",
        "trigger": {
            "kind": trigger_kind,
            "method": method,
            "path": slugify(trigger.get("path") or name),
        },
        "steps": normalized_steps,
        "credential_notes": normalize_string_list(plan.get("credential_notes")),
        "activation_notes": normalize_string_list(plan.get("activation_notes")),
    }


def build_workflow_from_plan(plan, user_prompt, catalog):
    available_types = {node["type"] for node in catalog} | CORE_NODE_TYPES
    nodes = []

    note_content = build_note_content(plan, user_prompt)
    nodes.append(
        make_node(
            "AIMIx Build Notes",
            "n8n-nodes-base.stickyNote",
            {"content": note_content, "height": 320, "width": 420, "color": 5},
            [-420, -220],
            1,
        )
    )

    trigger_node = build_trigger_node(plan["trigger"])
    nodes.append(trigger_node)

    chain_nodes = [trigger_node["name"]]
    x_position = 260
    for index, step in enumerate(plan["steps"], start=1):
        node = build_step_node(step, available_types, [x_position, 220 + ((index - 1) % 2) * 140], index)
        nodes.append(node)
        chain_nodes.append(node["name"])
        x_position += 280

    if plan["trigger"]["kind"] == "webhook":
        response_node = make_node(
            "Respond to AIMIx",
            "n8n-nodes-base.respondToWebhook",
            {"respondWith": "firstIncomingItem", "options": {}},
            [x_position, 220],
            1.5,
        )
        nodes.append(response_node)
        chain_nodes.append(response_node["name"])

    return {
        "name": plan["name"],
        "nodes": nodes,
        "connections": build_linear_connections(chain_nodes),
        "settings": {"executionOrder": "v1"},
    }


def build_trigger_node(trigger):
    kind = trigger.get("kind")
    if kind == "webhook":
        return make_node(
            "AIMIx Request",
            "n8n-nodes-base.webhook",
            {
                "httpMethod": trigger.get("method", "POST"),
                "path": trigger.get("path") or "aimix-workflow",
                "responseMode": "responseNode",
                "options": {},
            },
            [0, 220],
            2.1,
        )
    if kind == "schedule":
        return make_node(
            "Workflow Schedule",
            "n8n-nodes-base.scheduleTrigger",
            {"rule": {"interval": [{"field": "days"}]}},
            [0, 220],
            1.3,
        )
    return make_node("Manual Start", "n8n-nodes-base.manualTrigger", {}, [0, 220], 1)


def build_step_node(step, available_types, position, index):
    requested_type = step.get("nodeType") or ""
    node_type = requested_type if requested_type in available_types else ""
    kind = step.get("kind")

    if kind == "http" or node_type == "n8n-nodes-base.httpRequest":
        method = step.get("method") if step.get("method") in {"GET", "POST", "PUT", "PATCH", "DELETE"} else "GET"
        url = step.get("url") or "https://example.com/replace-me"
        return make_node(
            step["name"],
            "n8n-nodes-base.httpRequest",
            {"method": method, "url": url, "authentication": "none", "options": {}},
            position,
            4.4,
        )

    if kind == "integration" and node_type and node_type not in CORE_NODE_TYPES:
        return make_node(
            step["name"],
            node_type,
            {},
            position,
            get_default_node_version(node_type),
        )

    if kind == "set" and "n8n-nodes-base.set" in available_types:
        return make_node(
            step["name"],
            "n8n-nodes-base.set",
            {"options": {}},
            position,
            3.4,
        )

    return make_node(
        step["name"],
        "n8n-nodes-base.code",
        {
            "mode": "runOnceForAllItems",
            "language": "javaScript",
            "jsCode": build_safe_code(step, index),
        },
        position,
        2,
    )


def build_safe_code(step, index):
    description = json.dumps(step.get("description") or step.get("name") or f"Step {index}")
    fallback_code = (
        "const items = $input.all();\n"
        f"const stepDescription = {description};\n"
        "return items.map((item) => ({\n"
        "  json: {\n"
        "    ...item.json,\n"
        f"    aimixStep{index}: stepDescription,\n"
        "    aimixGeneratedAt: new Date().toISOString(),\n"
        "  },\n"
        "  binary: item.binary,\n"
        "}));"
    )

    code = step.get("code") or ""
    if not code or len(code) > 1500:
        return fallback_code
    if re.search(r"\b(fetch|XMLHttpRequest|require\s*\(|process\.env|eval\s*\()", code):
        return fallback_code
    return code


def build_linear_connections(node_names):
    connections = {}
    for source, target in zip(node_names, node_names[1:]):
        connections[source] = {
            "main": [[{"node": target, "type": "main", "index": 0}]],
        }
    return connections


def make_node(name, node_type, parameters, position, type_version):
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "type": node_type,
        "typeVersion": type_version,
        "position": position,
        "parameters": parameters,
    }


def build_note_content(plan, user_prompt):
    credential_notes = plan.get("credential_notes") or ["No credentials identified by the planner."]
    activation_notes = plan.get("activation_notes") or ["Open each generated node and verify required fields before activation."]
    lines = [
        "## AIMIx generated workflow",
        "",
        f"**Request:** {user_prompt[:500]}",
        "",
        f"**Plan:** {plan.get('summary', '')[:500]}",
        "",
        "**Credentials:**",
        *[f"- {note[:180]}" for note in credential_notes[:6]],
        "",
        "**Before activation:**",
        *[f"- {note[:180]}" for note in activation_notes[:6]],
    ]
    return "\n".join(lines)


def select_relevant_nodes(prompt, catalog, limit=70):
    lower_prompt = prompt.lower()
    by_type = {node["type"]: node for node in catalog}
    selected = []

    for display_name, node_type in COMMON_NODE_HINTS:
        selected.append(by_type.get(node_type, {"displayName": display_name, "type": node_type, "version": 1}))

    for node in catalog:
        display = node["displayName"].lower()
        name = node["type"].split(".")[-1].lower()
        if display in lower_prompt or name in lower_prompt:
            selected.append(node)

    deduped = []
    seen = set()
    for node in selected:
        if node["type"] in seen:
            continue
        seen.add(node["type"])
        deduped.append(node)
        if len(deduped) >= limit:
            break
    return deduped


@lru_cache(maxsize=1)
def discover_local_n8n_node_catalog():
    nodes = {}
    for nodes_dir, package_name in NODE_PACKAGE_DIRS:
        if not nodes_dir.exists():
            continue
        for path in nodes_dir.rglob("*.node.js"):
            if re.search(r"V\d+\.node\.js$", path.name):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")[:16000]
            except OSError:
                continue
            description_text = node_description_region(text)
            display = first_regex(description_text, r"displayName:\s*['\"]([^'\"]+)['\"]")
            name = first_regex(description_text, r"name:\s*['\"]([A-Za-z0-9_]+)['\"]")
            if not display or not name:
                continue
            if not name[0].islower():
                continue
            node_type = f"{package_name}.{name}"
            nodes[node_type] = {
                "displayName": display,
                "type": node_type,
                "version": parse_default_version(text),
            }

    for display_name, node_type in COMMON_NODE_HINTS:
        nodes.setdefault(node_type, {"displayName": display_name, "type": node_type, "version": 1})

    return sorted(nodes.values(), key=lambda node: node["displayName"].lower())


def get_default_node_version(node_type):
    for node in discover_local_n8n_node_catalog():
        if node["type"] == node_type:
            return node["version"]
    return 1


def parse_default_version(text):
    default_version = first_regex(text, r"defaultVersion:\s*([0-9.]+)")
    if default_version:
        return number_version(default_version)
    version = first_regex(text, r"version:\s*([0-9.]+)")
    if version:
        return number_version(version)
    version_list = first_regex(text, r"version:\s*\[([^\]]+)\]")
    if version_list:
        versions = re.findall(r"[0-9]+(?:\.[0-9]+)?", version_list)
        if versions:
            return number_version(versions[-1])
    return 1


def node_description_region(text):
    starts = []
    for pattern in (r"\bdescription\s*=\s*\{", r"\bbaseDescription\s*=\s*\{"):
        match = re.search(pattern, text)
        if match:
            starts.append(match.start())
    start = min(starts) if starts else 0
    return text[start : start + 7000]


def number_version(value):
    return float(value) if "." in value else int(value)


def first_regex(text, pattern):
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def normalize_step_kind(value):
    kind = clean_text(value).lower()
    return kind if kind in {"code", "http", "integration", "set", "if", "note"} else "code"


def normalize_string_list(value):
    if not isinstance(value, list):
        return []
    return [clean_text(item) for item in value if clean_text(item)][:8]


def unique_name(name, used_names):
    base = clean_text(name) or "Step"
    candidate = base
    suffix = 2
    while candidate in used_names:
        candidate = f"{base} {suffix}"
        suffix += 1
    used_names.add(candidate)
    return candidate


def infer_trigger_kind(prompt):
    lower_prompt = prompt.lower()
    if re.search(r"\b(every|daily|hourly|weekly|monthly|cron|schedule|scheduled)\b", lower_prompt):
        return "schedule"
    if re.search(r"\b(receive|webhook|api|form|chat|call|incoming|submit)\b", lower_prompt):
        return "webhook"
    return "manual"


def title_from_prompt(prompt):
    words = re.findall(r"[A-Za-z0-9]+", prompt)[:7]
    if not words:
        return "AIMIx Generated Workflow"
    return " ".join(word.capitalize() for word in words)


def slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return (slug or "aimix-workflow")[:54].strip("-") or "aimix-workflow"


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()
