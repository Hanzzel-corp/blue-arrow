/**
 * Extrae contexto de un payload si existe.
 *
 * Soporta dos formatos:
 * 1. Interno del bus: _trace_id / _meta
 * 2. Formato estándar: trace_id / meta
 */
export function extractContext(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return {
      trace_id: null,
      meta: null,
      cleanPayload: payload
    };
  }

  const {
    _trace_id,
    _meta,
    trace_id,
    meta,
    ...rest
  } = payload;

  const resolvedTraceId = _trace_id || trace_id || null;
  const resolvedMeta =
    (_meta && typeof _meta === "object" && !Array.isArray(_meta) ? _meta : null) ||
    (meta && typeof meta === "object" && !Array.isArray(meta) ? meta : null) ||
    null;

  return {
    trace_id: resolvedTraceId,
    meta: resolvedMeta,
    cleanPayload: rest
  };
}

/**
 * Aplica transformación opcional al payload.
 * Si no hay transform definida, retorna el payload limpio
 * con contexto adjunto en formato interno del bus.
 */
export function applyTransform(name, payload) {
  const { trace_id, meta, cleanPayload } = extractContext(payload);

  if (!name) {
    return {
      ...cleanPayload,
      _trace_id: trace_id,
      _meta: meta
    };
  }

  switch (name) {
    case "identity":
      return {
        ...cleanPayload,
        _trace_id: trace_id,
        _meta: meta
      };

    default:
      throw new Error(`Transform no soportado: ${name}`);
  }
}

/**
 * Crea un mensaje de respuesta estándar con contexto propagado.
 *
 * payload: datos de negocio
 * context: { trace_id, meta }
 * overrides: { trace_id?, meta? }
 */
export function createResponse(payload, context = {}, overrides = {}) {
  const baseMeta =
    context?.meta && typeof context.meta === "object" && !Array.isArray(context.meta)
      ? context.meta
      : {};

  const overrideMeta =
    overrides?.meta && typeof overrides.meta === "object" && !Array.isArray(overrides.meta)
      ? overrides.meta
      : {};

  return {
    ...(payload || {}),
    _trace_id: context?.trace_id || overrides?.trace_id || null,
    _meta: {
      ...baseMeta,
      ...overrideMeta,
      timestamp: overrideMeta.timestamp || new Date().toISOString()
    }
  };
}