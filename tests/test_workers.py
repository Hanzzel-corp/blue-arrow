from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _python_exe() -> str:
    venv_py = PROJECT_ROOT / ".venv" / "bin" / "python3"
    return str(venv_py) if venv_py.is_file() else sys.executable


def _run_worker_line(main_py: Path, message: dict, *, timeout: float = 25.0) -> list[dict]:
    r = subprocess.run(
        [_python_exe(), str(main_py)],
        input=json.dumps(message) + "\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=main_py.parent,
        timeout=timeout,
    )
    out: list[dict] = []
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    if r.returncode != 0 and not out:
        raise AssertionError(f"worker falló rc={r.returncode} stderr={r.stderr!r}")
    return out


def _find_result(messages: list[dict]) -> dict | None:
    for msg in messages:
        if msg.get("port") == "result.out":
            return msg
    return None


class TestPythonWorkers(unittest.TestCase):
    def test_system_monitor_resources(self):
        main_py = PROJECT_ROOT / "modules" / "worker.python.system" / "main.py"
        line = {
            "port": "action.in",
            "payload": {
                "task_id": "t_unittest",
                "action": "monitor_resources",
                "params": {},
                "meta": {"source": "unittest"},
            },
        }
        out = _run_worker_line(main_py, line)
        res = _find_result(out)
        self.assertIsNotNone(res, out)
        self.assertEqual(res["payload"].get("status"), "success")

    def test_desktop_echo_text(self):
        main_py = PROJECT_ROOT / "modules" / "worker.python.desktop" / "main.py"
        line = {
            "port": "action.in",
            "payload": {
                "task_id": "t_echo",
                "action": "echo_text",
                "params": {"text": "unittest"},
                "meta": {},
            },
        }
        out = _run_worker_line(main_py, line)
        res = _find_result(out)
        self.assertIsNotNone(res, out)
        self.assertEqual(res["payload"].get("status"), "success")

    def test_browser_unknown_action_no_launch(self):
        main_py = PROJECT_ROOT / "modules" / "worker.python.browser" / "main.py"
        line = {
            "port": "action.in",
            "payload": {
                "task_id": "t_browser",
                "action": "nonexistent_action",
                "params": {},
                "meta": {},
            },
        }
        out = _run_worker_line(main_py, line)
        res = _find_result(out)
        self.assertIsNotNone(res, out)
        self.assertEqual(res["payload"].get("status"), "error")

    def test_system_search_file(self):
        main_py = PROJECT_ROOT / "modules" / "worker.python.system" / "main.py"
        line = {
            "port": "action.in",
            "payload": {
                "task_id": "t_search",
                "action": "search_file",
                "params": {"filename": "manifest.json", "base_path": str(PROJECT_ROOT)},
                "meta": {},
            },
        }
        out = _run_worker_line(main_py, line)
        res = _find_result(out)
        self.assertIsNotNone(res, out)
        self.assertEqual(res["payload"].get("status"), "success")
        matches = res["payload"].get("result", {}).get("matches")
        self.assertIsInstance(matches, list)
        self.assertTrue(any("manifest.json" in m for m in matches))

    def test_desktop_two_messages_on_stdin(self):
        main_py = PROJECT_ROOT / "modules" / "worker.python.desktop" / "main.py"
        lines = [
            json.dumps(
                {
                    "port": "action.in",
                    "payload": {
                        "task_id": f"t_multi_{i}",
                        "action": "echo_text",
                        "params": {"text": f"pulse-{i}"},
                        "meta": {},
                    },
                }
            )
            for i in range(2)
        ]
        r = subprocess.run(
            [_python_exe(), str(main_py)],
            input="\n".join(lines) + "\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=main_py.parent,
            timeout=25,
        )
        results: list[dict] = []
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            if msg.get("port") == "result.out":
                results.append(msg)
        self.assertEqual(len(results), 2, (r.stderr, r.stdout))
        self.assertEqual(results[0]["payload"]["task_id"], "t_multi_0")
        self.assertEqual(results[1]["payload"]["task_id"], "t_multi_1")


if __name__ == "__main__":
    unittest.main()
