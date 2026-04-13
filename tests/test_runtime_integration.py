#!/usr/bin/env python3
"""
Integration tests for the complete runtime system.
Tests the full flow from command input to worker execution.
"""

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

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
        entry_name = manifest.get("entry", "main.js")
        mapping[module_id] = {
            "dir": manifest_path.parent,
            "manifest": manifest_path,
            "entry": manifest_path.parent / entry_name,
            "data": manifest,
        }
    return mapping


MODULE_INDEX = discover_modules()


def module_dir(module_id: str) -> Path:
    if module_id not in MODULE_INDEX:
        raise AssertionError(f"Module not found in manifests: {module_id}")
    return MODULE_INDEX[module_id]["dir"]


def module_manifest_path(module_id: str) -> Path:
    return MODULE_INDEX[module_id]["manifest"]


def module_entry_path(module_id: str) -> Path:
    return MODULE_INDEX[module_id]["entry"]


def assert_js_key(testcase, source: str, key: str, msg: str):
    testcase.assertRegex(
        source,
        rf'(?:"{re.escape(key)}"|{re.escape(key)})\s*:',
        msg,
    )


class TestRuntimeIntegration(unittest.TestCase):
    """Test the complete runtime integration."""

    def setUp(self):
        """Set up test environment."""
        self.project_root = PROJECT_ROOT
        self.blueprint_path = self.project_root / "blueprints" / "system.v0.json"
        self.runtime_main = self.project_root / "runtime" / "main.js"

        # Create temporary logs directory
        self.temp_logs = tempfile.mkdtemp()
        self.original_logs = self.project_root / "logs"

        # Backup original logs if exists
        if self.original_logs.exists():
            self.backup_logs = self.original_logs.rename(
                self.project_root / "logs_backup"
            )

        # Create new logs directory
        self.original_logs.mkdir(exist_ok=True)

    def _module_id_to_path(self, module_id: str) -> Path:
        """Convert module ID to filesystem path."""
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

    def tearDown(self):
        """Clean up test environment."""
        # Restore original logs
        if hasattr(self, 'backup_logs'):
            if self.original_logs.exists():
                import shutil
                shutil.rmtree(self.original_logs)
            self.backup_logs.rename(self.original_logs)

    def test_blueprint_validation(self):
        """Test that blueprint JSON is valid and contains required modules."""
        self.assertTrue(self.blueprint_path.exists(), "Blueprint file should exist")
        
        with open(self.blueprint_path) as f:
            blueprint = json.load(f)
        
        # Validate blueprint structure
        self.assertIn("modules", blueprint, "Blueprint should have modules")
        self.assertIn("connections", blueprint, "Blueprint should have connections")
        
        # Check required modules exist
        required_modules = [
            "interface.main",
            "agent.main", 
            "router.main",
            "planner.main",
            "safety.guard.main"
        ]
        
        for module in required_modules:
            self.assertIn(module, blueprint["modules"], f"Required module {module} missing")
        
        # Validate connections format
        for conn in blueprint["connections"]:
            self.assertIn("from", conn, "Connection should have 'from' field")
            self.assertIn("to", conn, "Connection should have 'to' field")
            self.assertIn(":", conn["from"], "From field should have port format")
            self.assertIn(":", conn["to"], "To field should have port format")

    def test_module_manifests_exist(self):
        """Test that all modules have valid manifest.json files."""
        blueprint_path = PROJECT_ROOT / "blueprints" / "system.v0.json"
        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        blueprint_modules = [m for m in blueprint.get("modules", [])]

        for module_id in blueprint_modules:
            self.assertIn(
                module_id,
                MODULE_INDEX,
                f"Manifest missing for module {module_id}"
            )
            manifest_path = module_manifest_path(module_id)
            self.assertTrue(
                manifest_path.exists(),
                f"Manifest missing for module {module_id} at {manifest_path}"
            )

    def test_runtime_syntax_validation(self):
        """Test that all runtime JavaScript files have valid syntax."""
        runtime_files = [
            "runtime/main.js",
            "runtime/bus.js", 
            "runtime/registry.js",
            "runtime/transforms.js"
        ]
        
        for file_path in runtime_files:
            full_path = self.project_root / file_path
            self.assertTrue(full_path.exists(), f"Runtime file {file_path} should exist")
            
            # Use Node.js to check syntax
            result = subprocess.run(
                ["node", "--check", str(full_path)],
                capture_output=True,
                text=True
            )
            
            self.assertEqual(
                result.returncode, 0,
                f"Syntax error in {file_path}: {result.stderr}"
            )

    def test_module_syntax_validation(self):
        """Test that all module files have valid syntax."""
        for module_id, info in MODULE_INDEX.items():
            entry_path = info["entry"]

            self.assertTrue(
                entry_path.exists(),
                f"Entry file missing for module {module_id}: {entry_path}"
            )

            if entry_path.suffix == ".js":
                result = subprocess.run(
                    ["node", "--check", str(entry_path)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"JavaScript syntax error in {module_id} ({entry_path}):\n{result.stderr}"
                )

            elif entry_path.suffix == ".py":
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", str(entry_path)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"Python syntax error in {module_id} ({entry_path}):\n{result.stderr}"
                )

    def test_message_format_validation(self):
        """Test that modules emit messages in correct JSON format."""
        # This test validates the message format structure
        # by checking module source code for emit patterns
        
        modules_dir = self.project_root / "modules"
        
        for module_dir in modules_dir.iterdir():
            if not module_dir.is_dir():
                continue
                
            # Check for emit function pattern
            for entry_file in module_dir.glob("main.*"):
                content = entry_file.read_text()
                
                # Look for emit function usage
                if "emit(" in content or "process.stdout.write" in content:
                    # Basic pattern validation - should have module, port, payload
                    assert_js_key(self, content, "module", f"{entry_file.name} should include module field in messages")
                    assert_js_key(self, content, "port", f"{entry_file.name} should include port field in messages")
                    assert_js_key(self, content, "payload", f"{entry_file.name} should include payload field in messages")

    def test_dependencies_available(self):
        """Test that required dependencies are available."""
        # Check Node.js modules
        node_result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True
        )
        self.assertEqual(node_result.returncode, 0, "Node.js should be available")
        
        # Check Python version
        python_result = subprocess.run(
            [sys.executable, "--version"],
            capture_output=True,
            text=True
        )
        self.assertEqual(python_result.returncode, 0, "Python should be available")
        
        # Check Python packages
        required_packages = ["psutil"]
        for package in required_packages:
            result = subprocess.run(
                [sys.executable, "-c", f"import {package}"],
                capture_output=True
            )
            self.assertEqual(
                result.returncode, 0,
                f"Python package {package} should be available"
            )

    def test_runtime_startup_sequence(self):
        """Test runtime startup sequence without full execution."""
        # This test validates that runtime can load blueprint and discover modules
        # without actually starting all processes
        
        test_script = '''
import { discoverModules } from "./registry.js";
import fs from "fs";
import path from "path";

const baseDir = process.cwd();
const blueprintPath = path.join(baseDir, "blueprints", "system.v0.json");
const blueprint = JSON.parse(fs.readFileSync(blueprintPath, "utf8"));
const registry = discoverModules(baseDir);

console.log(JSON.stringify({
    blueprintLoaded: true,
    modulesCount: blueprint.modules.length,
    connectionsCount: blueprint.connections.length,
    discoveredModules: registry.size
}));
'''
        
        test_file = self.project_root / "test_runtime_startup.js"
        test_file.write_text(test_script)
        
        try:
            result = subprocess.run(
                ["node", str(test_file)],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            self.assertEqual(result.returncode, 0, "Runtime startup test should pass")
            
            output = json.loads(result.stdout.strip())
            self.assertTrue(output["blueprintLoaded"], "Blueprint should load successfully")
            self.assertGreater(output["modulesCount"], 0, "Should have modules in blueprint")
            self.assertGreater(output["connectionsCount"], 0, "Should have connections")
            self.assertEqual(
                output["discoveredModules"],
                output["modulesCount"],
                "All blueprint modules should be discovered"
            )
            
        finally:
            test_file.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
