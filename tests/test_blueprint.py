from __future__ import annotations

import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_manifests() -> dict[str, dict]:
    out = {}
    for p in sorted((PROJECT_ROOT / "modules").glob("*/manifest.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        mid = data.get("id")
        assert mid, f"manifest sin id: {p}"
        out[mid] = data
    return out


def _parse_endpoint(endpoint: str) -> tuple[str, str]:
    assert ":" in endpoint, f"endpoint inválido (falta :): {endpoint!r}"
    mod, port = endpoint.split(":", 1)
    assert mod and port, f"endpoint vacío: {endpoint!r}"
    return mod, port


class TestBlueprint(unittest.TestCase):
    def test_blueprint_json_loads(self):
        path = PROJECT_ROOT / "blueprints" / "system.v0.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("modules", data)
        self.assertIn("connections", data)
        self.assertIsInstance(data["modules"], list)
        self.assertIsInstance(data["connections"], list)

    def test_blueprint_modules_exist_and_match_manifests(self):
        manifests = _load_manifests()
        blueprint = json.loads(
            (PROJECT_ROOT / "blueprints" / "system.v0.json").read_text(encoding="utf-8")
        )
        for mid in blueprint["modules"]:
            self.assertIn(mid, manifests, f"módulo en blueprint sin manifest: {mid}")

        manifest_ids = set(manifests)
        listed_set = set(blueprint["modules"])
        # Optional diagnostic/testing modules allowed but not required in blueprint
        optional_modules = {"chaos.tester", "coherence.analyzer", "diagnostic.main", "plan.runner.main"}
        orphan = manifest_ids - listed_set - optional_modules
        self.assertFalse(
            orphan,
            f"módulos con manifest pero no listados en blueprint: {sorted(orphan)}",
        )

    def test_blueprint_connections_reference_valid_modules_and_ports(self):
        manifests = _load_manifests()
        blueprint = json.loads(
            (PROJECT_ROOT / "blueprints" / "system.v0.json").read_text(encoding="utf-8")
        )

        for i, conn in enumerate(blueprint["connections"]):
            frm = conn.get("from")
            to = conn.get("to")
            self.assertTrue(frm and to, f"conexión #{i} incompleta: {conn}")

            src_mod, src_port = _parse_endpoint(frm)
            dst_mod, dst_port = _parse_endpoint(to)

            self.assertIn(src_mod, manifests, f"from desconocido: {frm}")
            self.assertIn(dst_mod, manifests, f"to desconocido: {to}")

            src = manifests[src_mod]
            dst = manifests[dst_mod]

            outs = src.get("outputs")
            if outs is not None:
                self.assertIn(
                    src_port,
                    outs,
                    f"{frm}: puerto {src_port!r} no declarado en outputs de {src_mod}: {outs}",
                )

            inp = dst.get("inputs")
            if inp is not None:
                self.assertIn(
                    dst_port,
                    inp,
                    f"{to}: puerto {dst_port!r} no declarado en inputs de {dst_mod}: {inp}",
                )


if __name__ == "__main__":
    unittest.main()
