#!/bin/bash
# Script para ejecutar diagnóstico del sistema
# Uso: ./run_diagnostic.sh [duracion_minutos] [intervalo_segundos]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuración por defecto
DURATION=${1:-50}
INTERVAL=${2:-300}

# Validar números
if ! [[ "$DURATION" =~ ^[0-9]+$ ]]; then
    echo "❌ Error: Duración debe ser un número (minutos)"
    exit 1
fi

if ! [[ "$INTERVAL" =~ ^[0-9]+$ ]]; then
    echo "❌ Error: Intervalo debe ser un número (segundos)"
    exit 1
fi

echo "🔬 BLUEPRINT SYSTEM DIAGNOSTIC"
echo "================================"
echo "📅 Fecha: $(date)"
echo "⏱️  Duración: ${DURATION} minutos"
echo "📊 Reporte cada: ${INTERVAL} segundos"
echo "================================"
echo ""

# Crear logs directory si no existe
mkdir -p logs

# Ejecutar diagnóstico standalone
if [ -f "lib/system_diagnostic.py" ]; then
    echo "🚀 Ejecutando diagnóstico standalone..."
    echo "   Presiona Ctrl+C para detener"
    echo ""
    
    # Ejecutar con timeout automático
    python3 lib/system_diagnostic.py --duration $((DURATION * 60)) --report-interval $INTERVAL 2>&1 | tee "logs/diagnostic_$(date +%Y%m%d_%H%M%S).log"
    
    EXIT_CODE=${PIPESTATUS[0]}
    
    echo ""
    echo "================================"
    if [ $EXIT_CODE -eq 0 ]; then
        echo "✅ Diagnóstico completado exitosamente"
    elif [ $EXIT_CODE -eq 1 ]; then
        echo "⚠️  Diagnóstico completado con advertencias"
    else
        echo "❌ Diagnóstico falló con código $EXIT_CODE"
    fi
    echo "📁 Logs guardados en: logs/"
    echo "================================"
    
    exit $EXIT_CODE
else
    echo "❌ Error: No se encontró lib/system_diagnostic.py"
    exit 1
fi
