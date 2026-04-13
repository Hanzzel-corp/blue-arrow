#!/bin/bash
# Coherence Check - Análisis de coherencia entre los 3 planos
# Uso: ./run_coherence_check.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🔬 COHERENCE DIAGNOSTIC"
echo "======================="
echo "📅 $(date)"
echo ""
echo "Este diagnóstico analiza la coherencia entre:"
echo "  📁 Plano FÍSICO:    Archivos y carpetas"
echo "  🧠 Plano LÓGICO:    Módulos y blueprint"  
echo "  ⚡ Plano OPERATIVO: Procesos y salud"
echo ""
echo "Mide COHERENCIA, no cantidades."
echo "======================="
echo ""

mkdir -p logs

if [ -f "lib/coherence_diagnostic.py" ]; then
    python3 lib/coherence_diagnostic.py 2>&1 | tee "logs/coherence_$(date +%Y%m%d_%H%M%S).log"
    
    EXIT_CODE=${PIPESTATUS[0]}
    
    echo ""
    echo "======================="
    if [ $EXIT_CODE -eq 0 ]; then
        echo "✅ Sistema coherente (Grade A/B)"
    elif [ $EXIT_CODE -eq 1 ]; then
        echo "⚠️  Coherencia regular (Grade C) - mejoras recomendadas"
    elif [ $EXIT_CODE -eq 2 ]; then
        echo "❌ Coherencia débil (Grade D/F) - atención requerida"
    else
        echo "💥 Error en diagnóstico"
    fi
    echo "📁 Ver logs/ para reporte detallado"
    echo "======================="
    
    exit $EXIT_CODE
else
    echo "❌ Error: lib/coherence_diagnostic.py no encontrado"
    exit 1
fi
