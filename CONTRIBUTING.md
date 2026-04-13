# Guía de Contribución

> Cómo contribuir a `blueprint-v0` (blue-arrow)

---

## 🚀 Primeros Pasos

1. **Fork** el repositorio
2. **Clona** tu fork: `git clone https://github.com/TU-USUARIO/blue-arrow.git`
3. **Crea** una rama: `git checkout -b feature/nombre-de-tu-feature`
4. **Haz** tus cambios
5. **Agrega** los archivos modificados: `git add .`
6. **Commit**: `git commit -m "Descripción clara del cambio"`
7. **Push**: `git push origin feature/nombre-de-tu-feature`
8. **Abre** un Pull Request

---

## 📋 Estándares de Código

### JavaScript (Node.js)
- Usar **ES Modules** (`import`/`export`)
- **async/await** para código asíncrono
- Logs estructurados con niveles (`debug`, `info`, `warn`, `error`)

### Python
- Compatible con **Python 3.11+**
- Usar **type hints** donde sea posible
- Seguir **PEP 8** (formateo con Black)

### Mensajes de Commit
```
tipo: descripción corta

Descripción más larga si es necesaria.
```

Tipos: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`

---

## 🧪 Testing

```bash
# Tests completos
npm run test:all

# Solo Node.js
npm run test:node

# Solo Python
npm run test:py

# Smoke test
npm run smoke
```

---

## 📝 Agregar un Nuevo Módulo

1. Crear directorio: `modules/tu-modulo/`
2. Crear `manifest.json` con puertos declarados
3. Implementar `main.js` o `main.py`
4. Documentar en `docs/TU_MODULO.md`
5. Agregar tests en `tests/`

Ver `docs/DEVELOPMENT.md` para más detalles.

---

## ❓ Preguntas

- Abre un **Issue** para bugs o features
- Discute cambios grandes antes de implementar
- Respeta el código de conducta
- **No abras issues públicos para vulnerabilidades de seguridad**; ver `SECURITY.md`

---

**Gracias por contribuir!** 🎉
