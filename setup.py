#!/usr/bin/env python3
"""
Setup script for Blueprint v0
Automates initial configuration and dependency checks
"""

import os
import sys
import subprocess
import json
from pathlib import Path


def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def print_step(step_num, text):
    print(f"[{step_num}] {text}")


def check_python():
    print_step(1, "Verificando Python 3.11+")
    version = sys.version_info
    if version >= (3, 11):
        print(f"  ✅ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"  ❌ Python {version.major}.{version.minor} encontrado, se requiere 3.11+")
        return False


def check_node():
    print_step(2, "Verificando Node.js 18+")
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.strip().replace("v", "").split(".")[0]
            if int(version) >= 18:
                print(f"  ✅ Node.js {result.stdout.strip()}")
                return True
            else:
                print(f"  ❌ Node.js {result.stdout.strip()} encontrado, se requiere 18+")
                return False
        else:
            print("  ❌ Node.js no instalado")
            return False
    except:
        print("  ❌ Node.js no encontrado")
        return False


def main():
    print_header("Blueprint v0 - Setup")
    
    checks = [
        ("Python", check_python),
        ("Node.js", check_node)
    ]
    
    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"  ❌ Error en {name}: {e}")
            results[name] = False
    
    print_header("Resumen")
    for name, passed in results.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")
    
    if all(results.values()):
        print("\n✅ Setup completado exitosamente\n")
        sys.exit(0)
    else:
        print("\n⚠️  Algunos checks fallaron\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
