#!/bin/bash
# Chaos Engineering Test - Ejecuta diagnóstico activo
# Uso: ./run_chaos_test.sh [duracion_minutos]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DURATION=${1:-50}

echo "🔥 CHAOS ENGINEERING & ACTIVE DIAGNOSTIC"
echo "=========================================="
echo "📅 $(date)"
echo "⏱️  Duración: ${DURATION} minutos"
echo "🎯 Objetivos:"
echo "   • Detectar módulos rotos"
echo "   • Encontrar funciones vacías/stub"
echo "   • Buscar código duplicado"
echo "   • Ejecutar acciones reales"
echo "   • Benchmark de funciones"
echo "=========================================="
echo ""

mkdir -p logs

if [ -f "lib/active_diagnostic.py" ]; then
    echo "🚀 Ejecutando diagnóstico activo..."
    echo "   Presiona Ctrl+C para detener"
    echo ""
    
    python3 lib/active_diagnostic.py --duration $((DURATION * 60)) 2>&1 | tee "logs/chaos_test_$(date +%Y%m%d_%H%M%S).log"
    
    EXIT_CODE=${PIPESTATUS[0]}
    
    echo ""
    echo "=========================================="
    if [ $EXIT_CODE -eq 0 ]; then
        echo "✅ Test completado - Sistema saludable"
    elif [ $EXIT_CODE -eq 1 ]; then
        echo "⚠️  Test completado - Problemas menores detectados"
    else
        echo "❌ Test falló - Revisar logs"
    fi
    echo "📁 Logs: logs/"
    echo "=========================================="
    
    exit $EXIT_CODE
else
    echo "❌ Error: No se encontró lib/active_diagnostic.py"
    exit 1
fi
