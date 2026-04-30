# Política de Seguridad

## Versiones Soportadas

| Versión | Soportada |
|---------|-----------|
| 1.0.x   | ✅ Sí     |
| < 1.0   | ❌ No     |

## Reportar Vulnerabilidades

Si descubrís una vulnerabilidad de seguridad en `blue-arrow`, por favor reportala de la siguiente manera:

### Proceso de Reporte

1. **No abras un issue público** - Las vulnerabilidades deben reportarse de forma privada.

2. **Enviar email a:** `hanzzelcorp@gmail.com` 

   Incluir:
   - Descripción del problema
   - Pasos para reproducir
   - Impacto potencial
   - Sugerencias de mitigación (si las tenés)

3. **Esperar respuesta** - Intentaremos responder dentro de 5 días hábiles.

4. **Si no recibís respuesta en ese plazo**, podés reenviar el reporte al mismo correo con el asunto:
   `FOLLOW-UP SECURITY REPORT - blue-arrow` 

5. **Divulgación coordinada** - Una vez solucionado, publicaremos un advisory con crédito al reportero (si así lo desea).

### Alcance

Vulnerabilidades relevantes incluyen:
- Exposición de secretos o credenciales
- Escapes de sandbox en workers
- Inyección de código en el runtime
- Problemas en la validación de seguridad (safety-guard)
- Bypass de circuitos de aprobación

### No Considerado Vulnerabilidad

- Issues en dependencias conocidas (reportar al proyecto upstream)
- Problemas en configuración por parte del usuario
- Exposición intencional de datos por mala configuración

## Mejores Prácticas para Usuarios

- Nunca commitear tokens o credenciales
- Usar `.env` para configuración sensible
- Revisar aprobaciones antes de confirmar acciones
- Mantener dependencias actualizadas

## Contacto de Seguridad

- **Canal de reporte:** `hanzzelcorp@gmail.com` 
- **Idioma:** Español o inglés

---

**Gracias por ayudar a mantener el proyecto seguro.** 🔒
