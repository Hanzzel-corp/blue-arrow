#!/usr/bin/env python3
"""
Integration tests for module-to-module communication.
Tests message flow between connected modules.
"""

import json
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock


def assert_js_key(testcase, source: str, key: str, msg: str):
    testcase.assertRegex(
        source,
        rf'(?:"{re.escape(key)}"\s*:|\b{re.escape(key)}\b\s*:|\b{re.escape(key)}\b\s*[,}}])',
        msg,
    )


def module_entry_path(module_id: str) -> Path:
    if module_id not in MODULE_INDEX:
        raise AssertionError(f"Module not found in manifests: {module_id}")
    entry_name = MODULE_INDEX[module_id]["data"].get("entry", "main.js")
    return MODULE_INDEX[module_id]["dir"] / entry_name


# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

MODULES_DIR = PROJECT_ROOT / "modules"


def discover_modules():
    mapping = {}
    for manifest_path in MODULES_DIR.glob("*/manifest.json"):
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        module_id = manifest["id"]
        mapping[module_id] = {
            "dir": manifest_path.parent,
            "manifest": manifest_path,
            "data": manifest,
        }
    return mapping


MODULE_INDEX = discover_modules()


class TestModuleIntegration(unittest.TestCase):
    """Test module integration and communication."""

    def setUp(self):
        """Set up test environment."""
        self.project_root = PROJECT_ROOT
        self.blueprint_path = self.project_root / "blueprints" / "system.v0.json"
        
        with open(self.blueprint_path) as f:
            self.blueprint = json.load(f)

    def test_interface_to_planner_flow(self):
        """Test message flow from interface to planner."""
        # Test that interface.main correctly forwards commands to planner.main
        interface_module = self.project_root / "modules" / "interface" / "main.js"
        self.assertTrue(interface_module.exists())
        
        # Check that interface emits command.out when receiving command.in
        content = interface_module.read_text()
        self.assertIn('command.out', content, "Interface should emit command.out")
        self.assertIn('command.in', content, "Interface should handle command.in")

    def test_planner_to_agent_flow(self):
        """Test message flow from planner to agent."""
        planner_module = self.project_root / "modules" / "planner" / "main.js"
        agent_module = self.project_root / "modules" / "agent" / "main.js"
        
        self.assertTrue(planner_module.exists())
        self.assertTrue(agent_module.exists())
        
        # Check planner outputs
        planner_content = planner_module.read_text()
        self.assertIn('command.out', planner_content, "Planner should emit command.out")
        
        # Check agent inputs
        agent_content = agent_module.read_text()
        self.assertIn('command.in', agent_content, "Agent should handle command.in")

    def test_agent_to_safety_flow(self):
        """Test message flow from agent to safety guard."""
        agent_module = self.project_root / "modules" / "agent" / "main.js"
        safety_module = self.project_root / "modules" / "safety-guard" / "main.js"
        
        self.assertTrue(agent_module.exists())
        self.assertTrue(safety_module.exists())
        
        # Check agent outputs
        agent_content = agent_module.read_text()
        self.assertIn('plan.out', agent_content, "Agent should emit plan.out")
        
        # Check safety inputs
        safety_content = safety_module.read_text()
        self.assertIn('plan.in', safety_content, "Safety guard should handle plan.in")

    def test_safety_to_router_flow(self):
        """Test message flow from safety to router."""
        safety_module = self.project_root / "modules" / "safety-guard" / "main.js"
        router_module = self.project_root / "modules" / "router" / "main.js"
        
        self.assertTrue(safety_module.exists())
        self.assertTrue(router_module.exists())
        
        # Check safety outputs
        safety_content = safety_module.read_text()
        self.assertIn('approved.plan.out', safety_content, "Safety should emit approved.plan.out")
        
        # Check router inputs
        router_content = router_module.read_text()
        self.assertIn('plan.in', router_content, "Router should handle plan.in")

    def test_router_to_workers_flow(self):
        """Test message flow from router to workers."""
        router_module = self.project_root / "modules" / "router" / "main.js"
        
        self.assertTrue(router_module.exists())
        router_content = router_module.read_text()
        
        # Check router outputs to different workers
        self.assertIn('desktop.action.out', router_content, "Router should emit desktop.action.out")
        self.assertIn('system.action.out', router_content, "Router should emit system.action.out")
        self.assertIn('browser.action.out', router_content, "Router should emit browser.action.out")
        
        # Check worker inputs exist (using manifest-based discovery)
        workers = [
            ("worker.python.desktop", "worker.python.desktop"),
            ("worker.python.system", "worker.python.system"),
            ("worker.python.browser", "worker.python.browser"),
        ]

        for worker_module_id, worker_id in workers:
            worker_path = module_entry_path(worker_module_id)
            self.assertTrue(worker_path.exists(), f"Worker {worker_id} should exist at {worker_path}")

            worker_content = worker_path.read_text(encoding="utf-8")
            self.assertIn('action.in', worker_content, f"{worker_id} should handle action.in")

    def test_workers_to_memory_flow(self):
        """Test message flow from workers to memory."""
        memory_module = self.project_root / "modules" / "memory-log" / "main.js"
        self.assertTrue(memory_module.exists())

        memory_content = memory_module.read_text()
        self.assertIn('result.in', memory_content, "Memory should handle result.in")
        self.assertIn('event.in', memory_content, "Memory should handle event.in")
        
        # Check workers emit results
        workers = [
            ("worker.python.desktop", "worker.python.desktop"),
            ("worker.python.system", "worker.python.system"),
            ("worker.python.browser", "worker.python.browser"),
        ]

        for worker_module_id, worker_id in workers:
            worker_path = module_entry_path(worker_module_id)
            worker_content = worker_path.read_text(encoding="utf-8")
            self.assertIn('result.out', worker_content, f"{worker_id} should emit result.out")

    def test_message_schema_consistency(self):
        """Test that messages follow consistent schema across modules."""
        # All messages should have: module, port, payload structure
        
        modules_dir = self.project_root / "modules"
        
        for module_dir in modules_dir.iterdir():
            if not module_dir.is_dir():
                continue
                
            # Find main files
            main_files = list(module_dir.glob("main.*"))
            if not main_files:
                continue
                
            for main_file in main_files:
                content = main_file.read_text()
                
                # Check for emit patterns
                if 'emit(' in content or 'process.stdout.write' in content:
                    # Should include required fields
                    assert_js_key(self, content, "module", f"{main_file.name} should include module field")
                    assert_js_key(self, content, "port", f"{main_file.name} should include port field")
                    assert_js_key(self, content, "payload", f"{main_file.name} should include payload field")

    def _module_id_to_path(self, module_id: str) -> Path:
        """Convert module ID to filesystem path."""
        # Special case mappings for inconsistent naming
        special_mappings = {
            "worker.python.desktop": "worker-python",
            "worker.python.system": "worker-system",
            "worker.python.browser": "worker-browser",
            "worker.python.terminal": "worker.python.terminal",
            "interface.telegram": "telegram-interface",
            "telegram.menu.main": "telegram-menu",
            "telegram.hud.main": "telegram-hud",
            "memory.log.main": "memory-log",
            "memory.menu.main": "memory-menu",
            "safety.guard.main": "safety-guard",
            "ai.assistant.main": "ai-assistant",
            "ai.intent.main": "ai-intent",
            "ai.learning.engine.main": "ai-learning-engine",
            "ai.memory.semantic.main": "ai-memory-semantic",
            "ai.self.audit.main": "ai-self-audit",
            "apps.menu.main": "apps-menu",
            "apps.session.main": "apps-session",
            "system.menu.main": "system-menu",
            "ui.state.main": "ui-state",
            "phase.engine.main": "phase-engine",
            "project.audit.main": "project-audit",
            "plan.runner.main": "plan-runner",
            "verifier.engine.main": "verifier-engine",
        }

        if module_id in special_mappings:
            return self.project_root / "modules" / special_mappings[module_id]

        # Normal case: interface.main -> interface/, agent.main -> agent/
        parts = module_id.split(".")
        if parts[-1] == "main":
            parts.pop()
        return self.project_root / "modules" / "/".join(parts)

    def test_connection_compatibility(self):
        """Test that all connections in blueprint are compatible."""
        for conn in self.blueprint["connections"]:
            from_module, from_port = conn["from"].split(":")
            to_module, to_port = conn["to"].split(":")

            # Check source module exists
            self.assertIn(
                from_module,
                MODULE_INDEX,
                f"Source module {from_module} should exist"
            )
            from_module_path = MODULE_INDEX[from_module]["dir"]
            self.assertTrue(
                from_module_path.exists(),
                f"Source module {from_module} should exist at {from_module_path}"
            )

            # Check target module exists
            self.assertIn(
                to_module,
                MODULE_INDEX,
                f"Target module {to_module} should exist"
            )
            to_module_path = MODULE_INDEX[to_module]["dir"]
            self.assertTrue(
                to_module_path.exists(),
                f"Target module {to_module} should exist at {to_module_path}"
            )

            # Check source emits the port
            from_main = module_entry_path(from_module)
            if from_main.exists():
                from_content = from_main.read_text(encoding="utf-8")
                self.assertIn(
                    from_port,
                    from_content,
                    f"{from_module} should emit {from_port}"
                )

            # Check target handles the port
            to_main = module_entry_path(to_module)
            if to_main.exists():
                to_content = to_main.read_text(encoding="utf-8")
                self.assertIn(
                    to_port,
                    to_content,
                    f"{to_module} should handle {to_port}"
                )

    def test_telegram_integration_flow(self):
        """Test Telegram interface integration."""
        telegram_interface = self.project_root / "modules" / "telegram-interface" / "main.js"
        telegram_menu = self.project_root / "modules" / "telegram-menu" / "main.js"
        
        if telegram_interface.exists():
            telegram_content = telegram_interface.read_text()
            self.assertIn('command.out', telegram_content, "Telegram interface should emit commands")
            self.assertIn('response.in', telegram_content, "Telegram interface should handle responses")
        
        if telegram_menu.exists():
            menu_content = telegram_menu.read_text()
            self.assertIn('callback.in', menu_content, "Telegram menu should handle callbacks")

    def test_memory_persistence_flow(self):
        """Test memory persistence and query flow."""
        memory_module = self.project_root / "modules" / "memory-log" / "main.js"
        self.assertTrue(memory_module.exists())

        memory_content = memory_module.read_text()

        # Check memory handles different input types
        self.assertIn('command.in', memory_content, "Memory should handle commands")
        self.assertIn('event.in', memory_content, "Memory should handle events")
        self.assertIn('result.in', memory_content, "Memory should handle results")
        self.assertIn('query.in', memory_content, "Memory should handle queries")
        
        # Check memory outputs
        self.assertIn('memory.out', memory_content, "Memory should output memory data")

    def test_supervisor_monitoring_flow(self):
        """Test supervisor monitoring flow."""
        supervisor_module = self.project_root / "modules" / "supervisor" / "main.js"
        self.assertTrue(supervisor_module.exists())
        
        supervisor_content = supervisor_module.read_text()
        
        # Check supervisor inputs
        self.assertIn('plan.in', supervisor_content, "Supervisor should handle plans")
        self.assertIn('result.in', supervisor_content, "Supervisor should handle results")
        self.assertIn('event.in', supervisor_content, "Supervisor should handle events")
        
        # Check supervisor outputs
        self.assertIn('event.out', supervisor_content, "Supervisor should emit events")


if __name__ == "__main__":
    unittest.main()
