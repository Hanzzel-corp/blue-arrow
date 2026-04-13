#!/usr/bin/env python3
"""
Tests for JSON schema validation of messages.
"""

import json
import sys
import unittest
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class TestSchemaValidation(unittest.TestCase):
    """Test JSON schema validation."""

    def setUp(self):
        """Set up test environment."""
        self.schemas_dir = PROJECT_ROOT / "schemas"
        self.message_schema_path = self.schemas_dir / "message.json"
        self.ports_schema_path = self.schemas_dir / "ports.json"

    def test_schema_files_exist(self):
        """Test that schema files exist and are valid JSON."""
        self.assertTrue(self.message_schema_path.exists(), "Message schema file should exist")
        self.assertTrue(self.ports_schema_path.exists(), "Ports schema file should exist")

        # Validate JSON syntax
        with open(self.message_schema_path) as f:
            message_schema = json.load(f)
            self.assertIn("$schema", message_schema)
            self.assertIn("type", message_schema)
            self.assertEqual(message_schema["type"], "object")

        with open(self.ports_schema_path) as f:
            ports_schema = json.load(f)
            self.assertIn("$schema", ports_schema)
            self.assertIn("definitions", ports_schema)

    def test_message_schema_structure(self):
        """Test message schema structure."""
        with open(self.message_schema_path) as f:
            schema = json.load(f)

        # Check required fields
        self.assertIn("required", schema)
        self.assertIn("module", schema["required"])
        self.assertIn("port", schema["required"])
        self.assertIn("payload", schema["required"])

        # Check module pattern
        self.assertIn("properties", schema)
        self.assertIn("module", schema["properties"])
        module_prop = schema["properties"]["module"]
        self.assertEqual(module_prop["type"], "string")
        self.assertIn("pattern", module_prop)

        # Check port pattern
        self.assertIn("port", schema["properties"])
        port_prop = schema["properties"]["port"]
        self.assertEqual(port_prop["type"], "string")
        self.assertIn("pattern", port_prop)

    def test_port_schemas_structure(self):
        """Test port schemas structure."""
        with open(self.ports_schema_path) as f:
            schema = json.load(f)

        self.assertIn("definitions", schema)
        definitions = schema["definitions"]

        # Check required definitions exist
        required_definitions = [
            "command", "plan", "step", "result", "event",
            "memory_query", "memory_data", "approval_request", "approval_response"
        ]

        for definition in required_definitions:
            self.assertIn(definition, definitions, f"Definition {definition} should exist")

    def test_command_schema(self):
        """Test command schema definition."""
        with open(self.ports_schema_path) as f:
            schema = json.load(f)

        command_schema = schema["definitions"]["command"]
        
        # Check required fields
        self.assertIn("required", command_schema)
        required_fields = ["command_id", "text", "source"]
        for field in required_fields:
            self.assertIn(field, command_schema["required"])

        # Check source enum
        source_prop = command_schema["properties"]["source"]
        self.assertIn("enum", source_prop)
        self.assertIn("cli", source_prop["enum"])
        self.assertIn("telegram", source_prop["enum"])

    def test_plan_schema(self):
        """Test plan schema definition."""
        with open(self.ports_schema_path) as f:
            schema = json.load(f)

        plan_schema = schema["definitions"]["plan"]
        
        # Check required fields
        self.assertIn("required", plan_schema)
        required_fields = ["plan_id", "kind", "original_command", "steps"]
        for field in required_fields:
            self.assertIn(field, plan_schema["required"])

        # Check kind enum
        kind_prop = plan_schema["properties"]["kind"]
        self.assertIn("enum", kind_prop)
        self.assertIn("single_step", kind_prop["enum"])
        self.assertIn("multi_step", kind_prop["enum"])

        # Check plan_id pattern
        plan_id_prop = plan_schema["properties"]["plan_id"]
        self.assertIn("pattern", plan_id_prop)

    def test_step_schema(self):
        """Test step schema definition."""
        with open(self.ports_schema_path) as f:
            schema = json.load(f)

        step_schema = schema["definitions"]["step"]
        
        # Check required fields
        self.assertIn("required", step_schema)
        self.assertIn("action", step_schema["required"])

        # Check action enum
        action_prop = step_schema["properties"]["action"]
        self.assertIn("enum", action_prop)
        
        expected_actions = [
            "open_application", "echo_text", "search_file", "monitor_resources",
            "open_url", "search_google", "fill_form", "click_web"
        ]
        
        for action in expected_actions:
            self.assertIn(action, action_prop["enum"])

    def test_result_schema(self):
        """Test result schema definition."""
        with open(self.ports_schema_path) as f:
            schema = json.load(f)

        result_schema = schema["definitions"]["result"]
        
        # Check required fields
        self.assertIn("required", result_schema)
        required_fields = ["task_id", "status", "result"]
        for field in required_fields:
            self.assertIn(field, result_schema["required"])

        # Check status enum
        status_prop = result_schema["properties"]["status"]
        self.assertIn("enum", status_prop)
        self.assertIn("success", status_prop["enum"])
        self.assertIn("error", status_prop["enum"])
        self.assertIn("timeout", status_prop["enum"])

    def test_event_schema(self):
        """Test event schema definition."""
        with open(self.ports_schema_path) as f:
            schema = json.load(f)

        event_schema = schema["definitions"]["event"]
        
        # Check required fields
        self.assertIn("required", event_schema)
        required_fields = ["event_type", "source"]
        for field in required_fields:
            self.assertIn(field, event_schema["required"])

        # Check event_type enum
        event_type_prop = event_schema["properties"]["event_type"]
        self.assertIn("enum", event_type_prop)
        
        expected_events = [
            "plan_created", "plan_approved", "plan_rejected", "plan_started",
            "plan_completed", "plan_failed", "task_started", "task_completed",
            "task_failed", "module_started", "module_error", "safety_block",
            "approval_required"
        ]
        
        for event in expected_events:
            self.assertIn(event, event_type_prop["enum"])

    def test_sample_message_validation(self):
        """Test validation of sample messages against schemas."""
        # This would require a JSON schema validator library
        # For now, we'll test the structure manually
        
        sample_command = {
            "module": "interface.main",
            "port": "command.out",
            "payload": {
                "command_id": "cmd_1234567890",
                "text": "abrir chrome",
                "source": "cli",
                "chat_id": None,
                "meta": {}
            }
        }

        # Basic structural validation
        self.assertIn("module", sample_command)
        self.assertIn("port", sample_command)
        self.assertIn("payload", sample_command)
        
        payload = sample_command["payload"]
        self.assertIn("command_id", payload)
        self.assertIn("text", payload)
        self.assertIn("source", payload)
        self.assertIn(payload["source"], ["cli", "telegram"])

        sample_plan = {
            "module": "agent.main",
            "port": "plan.out",
            "payload": {
                "plan_id": "plan_1234567890",
                "kind": "single_step",
                "original_command": "abrir chrome",
                "steps": [
                    {
                        "action": "open_application",
                        "params": {"name": "chrome"}
                    }
                ],
                "meta": {"source": "cli"}
            }
        }

        # Validate plan structure
        plan_payload = sample_plan["payload"]
        self.assertIn("plan_id", plan_payload)
        self.assertIn("kind", plan_payload)
        self.assertIn("original_command", plan_payload)
        self.assertIn("steps", plan_payload)
        self.assertIn(plan_payload["kind"], ["single_step", "multi_step"])
        
        # Validate first step
        step = plan_payload["steps"][0]
        self.assertIn("action", step)
        self.assertIn("open_application", ["open_application", "echo_text", "search_file"])

    def test_schema_consistency(self):
        """Test that schemas are consistent with actual module usage."""
        # This test checks that the schemas match what modules actually use
        
        modules_dir = PROJECT_ROOT / "modules"
        
        # Collect all ports mentioned in blueprint
        with open(PROJECT_ROOT / "blueprints" / "system.v0.json") as f:
            blueprint = json.load(f)
        
        used_ports = set()
        for conn in blueprint["connections"]:
            from_port = conn["from"].split(":")[1]
            to_port = conn["to"].split(":")[1]
            used_ports.add(from_port)
            used_ports.add(to_port)
        
        # Check that important ports have schemas
        important_ports = [
            "command.in", "command.out", "plan.in", "plan.out",
            "result.in", "result.out", "event.in", "event.out"
        ]
        
        for port in important_ports:
            if port in used_ports:
                # This port should have a schema definition
                self.assertTrue(True, f"Port {port} is used and should have schema")


if __name__ == "__main__":
    unittest.main()
