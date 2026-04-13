# Guía de Instalación de Ollama y LLaMA

Guía completa para configurar el motor de IA local (Ollama) con LLaMA para blueprint-v0.

> **Nota sobre módulos IA:** Ollama/modelos locales son requisito directo principalmente para:
> - `ai.assistant.main` - Asistente conversacional
> - `ai.intent.main` - Análisis de intenciones
>
> Otros módulos IA pueden funcionar de forma local, híbrida u opcional según implementación:
> - `ai.memory.semantic.main` - Memoria vectorial / embeddings
> - `ai.self.audit.main` - Auditoría de código
> - `ai.learning.engine.main` - Aprendizaje de patrones
>
> **Sin Ollama** el proyecto puede arrancar igual, pero con capacidades IA reducidas.

---

## 📋 Requisitos del Sistema

- **OS**: Linux (Ubuntu/Debian recomendado)
- **RAM**: Mínimo 8GB (16GB+ recomendado)
- **Disco**: 10GB+ libre para modelos
- **CPU**: Soporte para AVX2 (la mayoría de CPUs modernas)
- **GPU**: Opcional (CUDA para aceleración)

---

## 🚀 Instalación Rápida

### Paso 1: Instalar Ollama

```bash
# Método 1: Script oficial (recomendado)
curl -fsSL https://ollama.com/install.sh | sh

# Método 2: Manual (si el script falla)
# Descargar binario
curl -L https://ollama.com/download/ollama-linux-amd64 -o /usr/local/bin/ollama
chmod +x /usr/local/bin/ollama
```

### Paso 2: Iniciar Servicio

```bash
# Iniciar servidor ollama
ollama serve

# O iniciar como servicio systemd (opcional)
sudo systemctl enable ollama
sudo systemctl start ollama
```

### Paso 3: Descargar Modelo LLaMA

```bash
# Modelo recomendado (balance velocidad/calidad)
ollama pull llama3.2

# Alternativas disponibles:
# ollama pull llama3.2:1b    # Más rápido, menor calidad
# ollama pull llama3.2:3b    # Balance
# ollama pull llama3.2:7b    # Mejor calidad, más lento
# ollama pull codellama      # Especializado en código
# ollama pull mistral        # Alternativa a LLaMA
```

**Nota**: La primera descarga puede tardar varios minutos según tu conexión.

---

## ⚙️ Configuración

### Variables de Entorno (Opcional)

Agregar a `~/.bashrc` o `~/.zshrc`:

```bash
# Modelo por defecto
export OLLAMA_MODEL="llama3.2"

# URL del servidor (si no es localhost)
export OLLAMA_URL="http://localhost:11434"

# Directorio de modelos (opcional)
export OLLAMA_MODELS="/ruta/a/modelos"
```

### Configuración de blueprint-v0

Editar `modules/ai-assistant/manifest.json`:

```json
{
  "config": {
    "model": "llama3.2",
    "ollama_url": "http://localhost:11434",
    "temperature": 0.7,
    "max_history": 20
  }
}
```

Si ai.intent.main consume Ollama directamente, replicar configuración equivalente en su manifest.json
o heredar OLLAMA_MODEL y OLLAMA_URL desde variables de entorno para mantener una única fuente de configuración.

---

## 🧪 Verificación

### Test 1: Ollama Running

```bash
# Verificar que ollama responde
curl http://localhost:11434/api/tags

# Debería mostrar lista de modelos instalados
```

### Test 2: Modelo Funcionando

```bash
# Probar modelo directamente
ollama run llama3.2

# Escribir: "Hola, ¿cómo estás?"
# El modelo debería responder
```

### Test 3: Integración con Blueprint

```bash
# Iniciar blueprint
npm start

# En otra terminal o Telegram:
# Enviar: "Pregúntale a la IA: ¿Qué es la arquitectura modular?"

# Debería responder con un análisis generado por LLaMA
```

---

## 🔧 Solución de Problemas

### Problema: "ollama: command not found"

**Solución**:
```bash
# Verificar instalación
which ollama

# Si no está en PATH
export PATH=$PATH:/usr/local/bin

# O reinstalar
curl -fsSL https://ollama.com/install.sh | sh
```

### Problema: "Connection refused" al puerto 11434

**Solución**:
```bash
# Verificar si ollama está corriendo
ps aux | grep ollama

# Iniciar manualmente
ollama serve &

# O reiniciar servicio
sudo systemctl restart ollama
```

### Problema: Modelo muy lento

**Solución**:
```bash
# Usar modelo más pequeño
ollama pull llama3.2:1b

# O usar cuantización (reduce calidad pero mejora velocidad)
ollama pull llama3.2:1b-q4_0
```

### Problema: Out of Memory

**Solución**:
```bash
# Usar modelo más pequeño
ollama pull llama3.2:1b

# O limitar contexto en manifest.json:
{
  "config": {
    "num_ctx": 2048  # Reducir contexto
  }
}
```

### Problema: "Failed to load model"

**Solución**:
```bash
# Actualizar ollama
ollama --version  # Ver versión actual

# Reinstalar modelo
ollama rm llama3.2
ollama pull llama3.2
```

---

## 📊 Comparación de Modelos

| Modelo | Tamaño | Velocidad | Calidad | Uso Recomendado |
|--------|--------|-----------|---------|-----------------|
| llama3.2:1b | 1GB | ⭐⭐⭐⭐⭐ | ⭐⭐ | Respuestas rápidas, simples |
| llama3.2:3b | 3GB | ⭐⭐⭐⭐ | ⭐⭐⭐ | Balance general |
| llama3.2:7b | 7GB | ⭐⭐⭐ | ⭐⭐⭐⭐ | Calidad superior |
| codellama | 7GB | ⭐⭐⭐ | ⭐⭐⭐⭐ | Generación de código |
| mistral:7b | 7GB | ⭐⭐⭐ | ⭐⭐⭐⭐ | Alternativa a LLaMA |

---

## 💡 Optimización

### Para CPUs Lentas

```bash
# Usar modelo más pequeño
ollama pull llama3.2:1b

# O usar modelo con cuantización Q4
ollama pull llama3.2:3b-q4_0
```

### Para GPUs NVIDIA

```bash
# Instalar drivers CUDA (si no están instalados)
# Ollama detecta GPU automáticamente

# Verificar que usa GPU
ollama ps

# Debería mostrar "100% GPU"
```

### Para Sistemas con Poca RAM

```bash
# Crear swap adicional
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Usar modelo más pequeño
ollama pull llama3.2:1b
```

---

## 🔒 Seguridad

### Acceso Remoto (Opcional)

Si necesitas acceder a ollama desde otra máquina:

```bash
# Configurar ollama para escuchar en todas las interfaces
export OLLAMA_HOST=0.0.0.0:11434
ollama serve

# ⚠️ Advertencia: Esto expone ollama en tu red
# Usar firewall para restringir acceso:
sudo ufw allow from 192.168.1.0/24 to any port 11434
```

### Firewall Local

```bash
# Permitir solo localhost (más seguro)
export OLLAMA_HOST=127.0.0.1:11434
ollama serve
```

---

## 📚 Comandos Útiles

```bash
# Listar modelos instalados
ollama list

# Eliminar modelo
ollama rm llama3.2

# Copiar modelo personalizado
ollama cp llama3.2 mi-modelo-personalizado

# Ver logs
journalctl -u ollama -f

# Actualizar ollama
curl -fsSL https://ollama.com/install.sh | sh
```

---

## 🎯 Comandos de Blueprint que Usan IA

Una vez configurado, puedes usar:

```
# Consultas generales
"Pregúntale a la IA: [tu pregunta]"

# Análisis de código
"Analiza este código: [código]"

# Generación de código
"Genera código Python para [descripción]"

# Explicación de errores
"Explica este error: [mensaje de error]"

# Auditoría del proyecto
"Audita el proyecto"

# Análisis de intención mejorado
"[comando ambiguo]" → IA interpreta y sugiere
```

---

## ✅ Checklist de Instalación

- [ ] Ollama instalado (`ollama --version`)
- [ ] Servicio corriendo (`curl http://localhost:11434/api/tags`)
- [ ] Modelo descargado (`ollama list` muestra llama3.2)
- [ ] Modelo funciona (`ollama run llama3.2` responde)
- [ ] Blueprint configurado (manifest.json con modelo correcto)
- [ ] Prueba de integración exitosa

---

## 📞 Soporte

Si tienes problemas:

1. **Documentación Ollama**: https://github.com/ollama/ollama
2. **Issues**: https://github.com/ollama/ollama/issues
3. **Comunidad**: Discord de Ollama

---

**Nota**: Todo el procesamiento de IA ocurre localmente. No se envían datos a servicios externos.
