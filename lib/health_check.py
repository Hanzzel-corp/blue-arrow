#!/usr/bin/env python3
"""
Health Check System for Blueprint
Monitors module health and system status
"""

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from lib.logger import StructuredLogger
except ImportError:
    try:
        from logger import StructuredLogger
    except ImportError:
        class StructuredLogger:
            def __init__(self, name):
                self.name = name

            def info(self, msg):
                print(f"INFO [{self.name}]: {msg}", file=sys.stderr)

            def error(self, msg):
                print(f"ERROR [{self.name}]: {msg}", file=sys.stderr)

            def warn(self, msg):
                print(f"WARN [{self.name}]: {msg}", file=sys.stderr)

            def debug(self, msg):
                pass


logger = StructuredLogger("health.check")

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None


def clear_screen() -> None:
    print("\033[2J\033[H", end="")


class HealthChecker:
    """Monitors system and module health"""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = Path(project_root) if project_root else PROJECT_ROOT
        self.checks: List[Dict[str, Any]] = []
        self.last_check: Optional[Dict[str, Any]] = None
        self.status = "unknown"

    def check_system_resources(self) -> Dict[str, Any]:
        """Check CPU, memory, and disk usage"""
        if not PSUTIL_AVAILABLE:
            return {
                "component": "system_resources",
                "status": "warning",
                "warning": "psutil not installed. Install with: pip install psutil",
                "timestamp": datetime.now().isoformat(),
            }

        try:
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage(str(self.project_root))

            status = "healthy"
            issues: List[str] = []

            if cpu > 90:
                status = "critical"
                issues.append(f"CPU usage critical: {cpu}%")
            elif cpu > 70:
                status = "warning"
                issues.append(f"CPU usage high: {cpu}%")

            if memory.percent > 90:
                status = "critical"
                issues.append(f"Memory usage critical: {memory.percent}%")
            elif memory.percent > 80:
                status = "warning"
                issues.append(f"Memory usage high: {memory.percent}%")

            if disk.percent > 90:
                status = "critical"
                issues.append(f"Disk usage critical: {disk.percent}%")
            elif disk.percent > 85:
                status = "warning"
                issues.append(f"Disk usage high: {disk.percent}%")

            return {
                "component": "system_resources",
                "status": status,
                "metrics": {
                    "cpu_percent": cpu,
                    "memory_percent": memory.percent,
                    "memory_available_mb": memory.available // (1024 * 1024),
                    "disk_percent": disk.percent,
                    "disk_free_gb": disk.free // (1024 * 1024 * 1024),
                },
                "issues": issues,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "component": "system_resources",
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def check_dependencies(self) -> Dict[str, Any]:
        """Check if required dependencies are available"""
        deps = {
            "python": self._check_python(),
            "node": self._check_node(),
            "playwright": self._check_python_module("playwright"),
            "psutil": self._check_python_module("psutil"),
            "numpy": self._check_python_module("numpy"),
            "xdotool": self._check_system_cmd("xdotool"),
            "wmctrl": self._check_system_cmd("wmctrl"),
        }

        missing = [k for k, v in deps.items() if not v]
        status = "healthy" if not missing else "warning"

        return {
            "component": "dependencies",
            "status": status,
            "details": deps,
            "missing": missing,
            "timestamp": datetime.now().isoformat(),
        }

    def _check_python(self) -> bool:
        return sys.version_info >= (3, 10)

    def _check_node(self) -> bool:
        try:
            import subprocess
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _check_python_module(self, module: str) -> bool:
        try:
            __import__(module)
            return True
        except Exception:
            return False

    def _check_system_cmd(self, cmd: str) -> bool:
        return shutil.which(cmd) is not None

    def check_blueprint_integrity(self) -> Dict[str, Any]:
        """Check if blueprint is valid"""
        blueprint_path = self.project_root / "blueprints" / "system.v0.json"

        try:
            if not blueprint_path.exists():
                return {
                    "component": "blueprint",
                    "status": "critical",
                    "error": "Blueprint file not found",
                    "timestamp": datetime.now().isoformat(),
                }

            with open(blueprint_path, "r", encoding="utf-8") as f:
                blueprint = json.load(f)

            issues: List[str] = []

            modules = blueprint.get("modules")
            connections = blueprint.get("connections")

            if modules is None:
                issues.append("Missing 'modules' key")
                modules = []
            if connections is None:
                issues.append("Missing 'connections' key")
                connections = []

            if not isinstance(modules, list):
                issues.append("'modules' must be a list")
                modules = []

            if not isinstance(connections, list):
                issues.append("'connections' must be a list")
                connections = []

            seen = set()
            duplicates = []
            for m in modules:
                if m in seen:
                    duplicates.append(m)
                seen.add(m)
            if duplicates:
                issues.append(f"Duplicate module IDs: {duplicates}")

            declared_modules = set(modules)

            malformed_connections = 0
            unknown_module_refs = 0

            for conn in connections:
                if not isinstance(conn, dict):
                    issues.append(f"Invalid connection entry: {conn}")
                    malformed_connections += 1
                    continue

                from_ep = conn.get("from", "")
                to_ep = conn.get("to", "")

                if ":" not in from_ep or ":" not in to_ep:
                    issues.append(f"Malformed connection endpoint: {conn}")
                    malformed_connections += 1
                    continue

                from_mod = from_ep.split(":", 1)[0]
                to_mod = to_ep.split(":", 1)[0]

                if declared_modules and from_mod not in declared_modules:
                    issues.append(f"Connection source module not declared: {from_mod}")
                    unknown_module_refs += 1
                if declared_modules and to_mod not in declared_modules:
                    issues.append(f"Connection target module not declared: {to_mod}")
                    unknown_module_refs += 1

            status = "healthy" if not issues else "warning"

            if malformed_connections > 0:
                status = "critical"

            return {
                "component": "blueprint",
                "status": status,
                "modules_count": len(modules),
                "connections_count": len(connections),
                "malformed_connections": malformed_connections,
                "unknown_module_refs": unknown_module_refs,
                "issues": issues,
                "timestamp": datetime.now().isoformat(),
            }
        except json.JSONDecodeError as e:
            return {
                "component": "blueprint",
                "status": "critical",
                "error": f"Invalid JSON: {e}",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "component": "blueprint",
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def check_module_manifests(self) -> Dict[str, Any]:
        """Check if all module manifests are valid"""
        modules_dir = self.project_root / "modules"
        issues: List[str] = []
        valid = 0
        total = 0

        try:
            if not modules_dir.exists():
                return {
                    "component": "module_manifests",
                    "status": "critical",
                    "error": f"Modules directory not found: {modules_dir}",
                    "timestamp": datetime.now().isoformat(),
                }

            for entry in sorted(modules_dir.iterdir()):
                if not entry.is_dir():
                    continue

                total += 1
                manifest_path = entry / "manifest.json"

                if not manifest_path.exists():
                    issues.append(f"{entry.name}: Missing manifest.json")
                    continue

                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)

                    required = ["id", "language", "entry"]
                    missing = [k for k in required if k not in manifest]

                    if missing:
                        issues.append(f"{entry.name}: Missing keys {missing}")
                        continue

                    entry_file = entry / str(manifest["entry"])
                    if not entry_file.exists():
                        issues.append(f"{entry.name}: Entry file not found ({manifest['entry']})")
                        continue

                    valid += 1

                except json.JSONDecodeError:
                    issues.append(f"{entry.name}: Invalid JSON in manifest")
                except Exception as e:
                    issues.append(f"{entry.name}: Error reading manifest - {e}")

            status = "healthy" if not issues else "warning"

            return {
                "component": "module_manifests",
                "status": status,
                "valid": valid,
                "total": total,
                "issues": issues,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "component": "module_manifests",
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks"""
        checks = [
            self.check_system_resources(),
            self.check_dependencies(),
            self.check_blueprint_integrity(),
            self.check_module_manifests(),
        ]

        statuses = [c["status"] for c in checks]

        if "critical" in statuses:
            overall = "critical"
        elif "error" in statuses:
            overall = "error"
        elif "warning" in statuses:
            overall = "warning"
        else:
            overall = "healthy"

        result = {
            "overall_status": overall,
            "checks": checks,
            "timestamp": datetime.now().isoformat(),
        }

        self.last_check = result
        self.status = overall
        return result

    def print_report(self, result: Dict[str, Any]) -> None:
        """Print formatted health report"""
        status_emoji = {
            "healthy": "✅",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🔴",
            "unknown": "❓",
        }

        print(f"\n{'=' * 60}")
        print(f"{status_emoji.get(result['overall_status'], '❓')} HEALTH CHECK REPORT")
        print(f"{'=' * 60}")
        print(f"Overall Status: {result['overall_status'].upper()}")
        print(f"Timestamp: {result['timestamp']}")
        print(f"{'-' * 60}\n")

        for check in result["checks"]:
            emoji = status_emoji.get(check["status"], "❓")
            print(f"{emoji} {check['component'].upper()}")
            print(f"   Status: {check['status']}")

            if "metrics" in check:
                for k, v in check["metrics"].items():
                    print(f"   {k}: {v}")

            if "details" in check:
                for k, v in check["details"].items():
                    status = "✅" if v else "❌"
                    print(f"   {status} {k}")

            if "issues" in check and check["issues"]:
                print("   Issues:")
                for issue in check["issues"]:
                    print(f"      - {issue}")

            if "missing" in check and check["missing"]:
                print(f"   Missing: {', '.join(check['missing'])}")

            if "error" in check:
                print(f"   Error: {check['error']}")

            print()

        print(f"{'=' * 60}\n")


def main():
    """CLI for health checks"""
    parser = argparse.ArgumentParser(description="Blueprint Health Checker")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--watch", type=int, metavar="SECONDS", help="Watch mode with interval")
    args = parser.parse_args()

    checker = HealthChecker()

    if args.watch:
        print(f"🔍 Health Check Watch Mode (interval: {args.watch}s)")
        print("Press Ctrl+C to stop\n")

        try:
            while True:
                result = checker.run_all_checks()

                if args.json:
                    print(json.dumps(result, ensure_ascii=False))
                else:
                    clear_screen()
                    checker.print_report(result)

                time.sleep(args.watch)
        except KeyboardInterrupt:
            print("\n👋 Health check stopped")
    else:
        result = checker.run_all_checks()

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            checker.print_report(result)

        if result["overall_status"] in ["critical", "error"]:
            sys.exit(1)


if __name__ == "__main__":
    main()
