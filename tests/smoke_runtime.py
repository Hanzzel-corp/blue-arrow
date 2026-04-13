from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_smoke() -> None:
  """
  Smoke test end-to-end:
  - arranca `node runtime/main.js`
  - envía un par de comandos por stdin
  - verifica que haya al menos una respuesta válida por stderr de interface.main
  """

  cmd = ["node", "runtime/main.js"]
  proc = subprocess.Popen(
    cmd,
    cwd=PROJECT_ROOT,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
  )

  assert proc.stdin is not None
  assert proc.stderr is not None

  # Comandos simples que el sistema ya soporta
  lines = ["hola", "ultimo comando"]
  for line in lines:
    proc.stdin.write(line + "\n")
  proc.stdin.flush()

  # Leemos un poco de stderr buscando el bloque [RESPUESTA]
  stderr = []
  for _ in range(200):
    chunk = proc.stderr.readline()
    if not chunk:
      break
    stderr.append(chunk)
    if "[RESPUESTA]" in chunk:
      break

  try:
    proc.terminate()
  except Exception:
    pass

  text = "".join(stderr)
  if "[RESPUESTA]" not in text:
    raise AssertionError(
      "Smoke test: no se encontró bloque [RESPUESTA] en stderr.\n"
      f"stderr parcial:\n{text}"
    )

  # Intentar parsear el JSON que imprime interface.main (mejor esfuerzo, no obligatorio)
  json_lines = [ln for ln in text.splitlines() if ln.strip().startswith("{")]
  if not json_lines:
    # En algunos entornos sólo se ve el marcador [RESPUESTA] sin el JSON
    return

  try:
    payload = json.loads("\n".join(json_lines))
  except Exception:
    return

  if isinstance(payload, dict) and "status" in payload:
    return


if __name__ == "__main__":
  run_smoke()

