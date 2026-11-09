-- Copyright © 2026 Cristian Rodriguez
-- All rights reserved.
-- Unauthorized copying, modification, distribution, or use is prohibited
-- without prior written permission.

-- ============================================================================
-- MEGALODON — SQLite Temporal para Desarrollo (FASE 2)
-- ============================================================================
-- ⚠️  TEMPORAL PARA DESARROLLO — NO USAR EN PRODUCCIÓN
-- Este schema está en SQLite para desarrollo local rápido.
-- En producción se migra a PostgreSQL + PostGIS en Supabase.
-- ============================================================================
-- Contiene PARTES de los catálogos reales extraídos de PDFs oficiales:
--   • CFE 2026 — Catálogo de Precios Unitarios (Comisión Federal de Electricidad)
--   • CMIC 2026 — Rehabilitación de Pozos (Cámara Mexicana de la Construcción)
--   • CONAGA SGIH 2026 — Por Gerencia (Comisión Nacional del Agua)
--   • Salarios Profesionales — Por categoría (referencia mercado obra pública)
--   • Maquinaria y Equipo — Por tipo y capacidad (referencia mercado)
-- ============================================================================

-- Habilitar foreign keys
PRAGMA foreign_keys = ON;

-- ============================================================================
-- 0. PLATFORM CORE
-- ============================================================================

CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    config TEXT, -- JSON
    branding TEXT, -- JSON
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    full_name TEXT NOT NULL,
    rfc TEXT,
    curp TEXT,
    role TEXT DEFAULT 'tecnico',
    is_active INTEGER DEFAULT 1,
    is_verified INTEGER DEFAULT 0,
    last_login TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS entidades (
    id TEXT PRIMARY KEY,
    clave TEXT UNIQUE NOT NULL,
    nombre TEXT NOT NULL,
    nombre_corto TEXT,
    tipo TEXT NOT NULL, -- FEDERAL, ESTATAL, MUNICIPAL, ORGANISMO
    direccion TEXT,
    email TEXT,
    telefono TEXT,
    config TEXT, -- JSON
    branding TEXT, -- JSON
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS unidades_administrativas (
    id TEXT PRIMARY KEY,
    entidad_id TEXT NOT NULL REFERENCES entidades(id) ON DELETE CASCADE,
    clave TEXT NOT NULL,
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL, -- REQUIRENTE, CONTRATANTE, CONTROL
    responsable_nombre TEXT,
    responsable_email TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(entidad_id, clave)
);

CREATE TABLE IF NOT EXISTS proveedores (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    tipo_persona TEXT NOT NULL, -- FISICA, MORAL, CONSORCIO
    rfc TEXT UNIQUE NOT NULL,
    razon_social TEXT NOT NULL,
    nombre_comercial TEXT,
    email TEXT,
    telefono TEXT,
    direccion TEXT,
    estado TEXT DEFAULT 'ACTIVO', -- ACTIVO, INACTIVO, BLOQUEADO, SANCIONADO
    capacidad_ejecucion TEXT, -- JSON
    especialidades TEXT, -- JSON
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS representantes_legales (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    proveedor_id TEXT NOT NULL REFERENCES proveedores(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    curp TEXT,
    rfc TEXT,
    email TEXT,
    telefono TEXT,
    efirma_serial TEXT,
    efirma_vigencia_inicio TEXT,
    efirma_vigencia_fin TEXT,
    efirma_activa INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- ============================================================================
-- 1. CATÁLOGOS MAESTROS
-- ============================================================================

CREATE TABLE IF NOT EXISTS catalogo_procedimientos (
    id TEXT PRIMARY KEY,
    clave TEXT UNIQUE NOT NULL,
    nombre TEXT NOT NULL,
    descripcion TEXT,
    ley TEXT, -- LAASSP, LOPSRM, LFT
    articulos TEXT,
    requisitos TEXT, -- JSON
    documentos_obligatorios TEXT, -- JSON
    umbral_minimo REAL,
    umbral_maximo REAL,
    activo INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS catalogo_juridico (
    id TEXT PRIMARY KEY,
    clave TEXT UNIQUE NOT NULL,
    tipo TEXT NOT NULL, -- LEY, REGLAMENTO, CRITERIO, MANUAL
    nombre TEXT NOT NULL,
    descripcion TEXT,
    articulos TEXT,
    obligaciones TEXT, -- JSON
    tipo_procedimiento TEXT,
    etapa TEXT, -- PLANEACION, CONVOCATORIA, etc.
    url_documento TEXT,
    vigencia_inicio TEXT,
    vigencia_fin TEXT,
    activo INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- ============================================================================
-- 2. CATALOGO DE FUENTES (CFE, CMIC, CONAGA, etc.)
-- ============================================================================

CREATE TABLE IF NOT EXISTS catalogo_fuentes (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL, -- CFE, CMIC, CONAGA, SCT, PEMEX, CUSTOM
    tipo TEXT NOT NULL, -- CFE, CMIC, CONAGA, SCT, PEMEX, CUSTOM
    vigencia_inicio TEXT NOT NULL, -- YYYY-MM-DD
    vigencia_fin TEXT NOT NULL,
    descripcion TEXT,
    url_fuente TEXT,
    activo INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- ============================================================================
-- 3. CONCEPTOS DE CATÁLOGOS REALES (PARTES extraídas de PDFs oficiales)
-- ============================================================================

CREATE TABLE IF NOT EXISTS conceptos_catalogo (
    id TEXT PRIMARY KEY,
    fuente_id TEXT NOT NULL REFERENCES catalogo_fuentes(id) ON DELETE CASCADE,
    clave TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    descripcion_larga TEXT,
    unidad TEXT NOT NULL, -- Pza, m2, m3, km, PZ, SR, etc.
    precio_unitario REAL NOT NULL,
    zona_economica TEXT, -- Zona I, II, III; o nombre de gerencia
    estado TEXT, -- Aguascalientes, Baja California, etc.
    region TEXT,
    incluye_iva INTEGER DEFAULT 0, -- 0 = Sin IVA (como los PDFs reales)
    desglose TEXT, -- JSON: {"materiales": X, "mano_obra": Y, "maquinaria": Z}
    pagina_origen INTEGER,
    hash_linea TEXT,
    activo INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(clave, fuente_id, zona_economica)
);

CREATE INDEX IF NOT EXISTS idx_conceptos_busqueda ON conceptos_catalogo(descripcion);
CREATE INDEX IF NOT EXISTS idx_conceptos_fuente ON conceptos_catalogo(fuente_id, zona_economica, estado);
CREATE INDEX IF NOT EXISTS idx_conceptos_clave ON conceptos_catalogo(clave);

-- ============================================================================
-- 4. INSUMOS: MATERIALES, MANO DE OBRA, MAQUINARIA, SALARIOS PROFESIONALES
-- ============================================================================

CREATE TABLE IF NOT EXISTS insumos_catalogo (
    id TEXT PRIMARY KEY,
    fuente_id TEXT NOT NULL REFERENCES catalogo_fuentes(id) ON DELETE CASCADE,
    clave TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    tipo TEXT NOT NULL, -- MATERIAL, MANO_OBRA, MAQUINARIA, SALARIO_PROFESIONAL
    unidad TEXT NOT NULL,
    precio_unitario REAL NOT NULL,
    categoria TEXT, -- Hormigón, Acero, Operador, Ingeniero, etc.
    subcategoria TEXT,
    zona_economica TEXT,
    estado TEXT,
    incluye_iva INTEGER DEFAULT 0,
    activo INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(clave, fuente_id, zona_economica, tipo)
);

CREATE INDEX IF NOT EXISTS idx_insumos_tipo ON insumos_catalogo(tipo, categoria);
CREATE INDEX IF NOT EXISTS idx_insumos_fuente ON insumos_catalogo(fuente_id, zona_economica);
CREATE INDEX IF NOT EXISTS idx_insumos_clave ON insumos_catalogo(clave);

-- ============================================================================
-- 5. EXPEDIENTE / CASE MANAGEMENT
-- ============================================================================

CREATE TABLE IF NOT EXISTS expedientes_obra (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    identificador TEXT UNIQUE NOT NULL,
    titulo TEXT NOT NULL,
    descripcion TEXT,
    organo TEXT NOT NULL,
    unidad_administrativa TEXT NOT NULL,
    serie_documental TEXT NOT NULL,
    subserie_documental TEXT NOT NULL,
    estado TEXT DEFAULT 'INICIADO', -- INICIADO, EN_TRAMITE, PENDIENTE_DOCUMENTACION, EN_FIRMA, ARCHIVADO, CERRADO
    proyecto_id TEXT,
    proyecto_nombre TEXT,
    ubicacion_obra TEXT,
    monto_contrato REAL,
    plazo_dias INTEGER,
    tipo_contrato TEXT DEFAULT 'PRECIOS_UNITARIOS',
    responsable_tecnico TEXT,
    responsable_ejecutivo TEXT,
    creado_por_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    actualizado_por_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_expedientes_estado ON expedientes_obra(estado);
CREATE INDEX IF NOT EXISTS idx_expedientes_tenant ON expedientes_obra(tenant_id);

CREATE TABLE IF NOT EXISTS planeaciones_expediente (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    expediente_id TEXT UNIQUE NOT NULL REFERENCES expedientes_obra(id) ON DELETE CASCADE,
    necesidad TEXT,
    justificacion TEXT,
    objetivo TEXT,
    presupuesto_estimado REAL,
    fuente_financiamiento TEXT,
    fecha_inicio_esperada TEXT,
    fecha_fin_esperada TEXT,
    riesgos TEXT, -- JSON
    aprobado_por TEXT,
    fecha_aprobacion TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- ============================================================================
-- 6. DOCUMENTO / CDE
-- ============================================================================

CREATE TABLE IF NOT EXISTS documentos_cde (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    expediente_id TEXT NOT NULL REFERENCES expedientes_obra(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL, -- CONVOCATORIA, BASES, ANEXO_TECNICO, ACTA, FALLA, CONTRATO, ESTIMACION, FACTURA, PLANO, BIM_IFC, etc.
    estado TEXT DEFAULT 'BORRADOR', -- BORRADOR, EN_REVISION, APROBADO, PUBLICADO, ARCHIVADO, OBSOLETO
    mime_type TEXT,
    tamaño_bytes INTEGER,
    hash_sha256 TEXT,
    ruta_storage TEXT,
    ruta_supabase TEXT,
    version INTEGER DEFAULT 1,
    documento_padre_id TEXT REFERENCES documentos_cde(id) ON DELETE SET NULL,
    firmado INTEGER DEFAULT 0,
    firma_electronica_id TEXT,
    sello_tiempo TEXT,
    texto_extraido TEXT,
    ocr_completado INTEGER DEFAULT 0,
    ocr_task_id TEXT,
    metadata TEXT, -- JSON
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_documentos_expediente ON documentos_cde(expediente_id, tipo, estado);

-- ============================================================================
-- 7. LICITACIONES
-- ============================================================================

CREATE TABLE IF NOT EXISTS licitaciones (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    expediente_id TEXT NOT NULL REFERENCES expedientes_obra(id) ON DELETE CASCADE,
    folio TEXT UNIQUE NOT NULL,
    tipo_procedimiento TEXT NOT NULL, -- LICITACION_PUBLICA, INVITACION_TRES, ADJUDICACION_DIRECTA, OBRA_PUBLICA
    estado TEXT DEFAULT 'PLANEACION', -- PLANEACION, CONVOCATORIA, JUNTA_ACLARACIONES, RECEPCION_PROPUESTAS, APERTURA, EVALUACION, FALLO, ADJUDICACION, CONTRATO, DESIERTA, CANCELADA
    objeto TEXT NOT NULL,
    monto_estimado REAL,
    plazo_dias INTEGER,
    fecha_convocatoria TEXT,
    fecha_junta_aclaraciones TEXT,
    fecha_apertura TEXT,
    fecha_fallo TEXT,
    reglas_participacion TEXT, -- JSON
    bases TEXT,
    matriz_evaluacion TEXT, -- JSON
    dictamen TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS juntas_aclaracion (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    licitacion_id TEXT NOT NULL REFERENCES licitaciones(id) ON DELETE CASCADE,
    fecha TEXT NOT NULL,
    acta TEXT,
    preguntas_respuestas TEXT, -- JSON
    cambios_bases TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS proposiciones (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    licitacion_id TEXT NOT NULL REFERENCES licitaciones(id) ON DELETE CASCADE,
    proveedor_id TEXT NOT NULL REFERENCES proveedores(id) ON DELETE CASCADE,
    monto REAL NOT NULL,
    plazo_dias INTEGER NOT NULL,
    sobres_digitales TEXT, -- JSON
    evaluacion_tecnica REAL,
    evaluacion_economica REAL,
    evaluacion_legal REAL,
    resultado TEXT, -- GANADOR, RECHAZADA, etc.
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- ============================================================================
-- 8. CONTRATOS
-- ============================================================================

CREATE TABLE IF NOT EXISTS contratos (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    expediente_id TEXT NOT NULL REFERENCES expedientes_obra(id) ON DELETE CASCADE,
    licitacion_id TEXT REFERENCES licitaciones(id) ON DELETE SET NULL,
    proveedor_id TEXT NOT NULL REFERENCES proveedores(id) ON DELETE RESTRICT,
    numero_contrato TEXT UNIQUE NOT NULL,
    estado TEXT DEFAULT 'EN_FIRMA', -- EN_FIRMA, VIGENTE, EN_MODIFICACION, SUSPENDIDO, TERMINADO, RESCINDIDO, CERRADO
    objeto TEXT NOT NULL,
    monto_total REAL NOT NULL,
    plazo_dias INTEGER NOT NULL,
    fecha_firma TEXT,
    fecha_inicio TEXT,
    fecha_termino TEXT,
    clausulas TEXT, -- JSON
    obligaciones TEXT, -- JSON
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS convenios_modificatorios (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    contrato_id TEXT NOT NULL REFERENCES contratos(id) ON DELETE CASCADE,
    numero TEXT NOT NULL,
    tipo TEXT NOT NULL, -- PLAZO, MONTO, ALCANCE
    descripcion TEXT,
    monto_anterior REAL,
    monto_nuevo REAL,
    plazo_anterior INTEGER,
    plazo_nuevo INTEGER,
    justificacion TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS garantias (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    contrato_id TEXT NOT NULL REFERENCES contratos(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL, -- CUMPLIMIENTO, ANTICIPO, VICIOS_OCULTOS, ESTABILIDAD
    monto REAL NOT NULL,
    institucion TEXT,
    numero_poliza TEXT,
    vigencia_inicio TEXT,
    vigencia_fin TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS entregables (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    contrato_id TEXT NOT NULL REFERENCES contratos(id) ON DELETE CASCADE,
    numero_estimacion INTEGER NOT NULL,
    periodo_inicio TEXT,
    periodo_fin TEXT,
    monto_ejecutado REAL DEFAULT 0,
    monto_pagado REAL DEFAULT 0,
    avance_fisico REAL DEFAULT 0,
    estado TEXT DEFAULT 'PENDIENTE',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- ============================================================================
-- 9. COMPLIANCE
-- ============================================================================

CREATE TABLE IF NOT EXISTS reglas_cumplimiento (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    descripcion TEXT,
    tipo_procedimiento TEXT NOT NULL,
    etapa TEXT NOT NULL,
    requisitos TEXT, -- JSON
    obligatorio INTEGER DEFAULT 1,
    activa INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS inconformidades (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    expediente_id TEXT NOT NULL REFERENCES expedientes_obra(id) ON DELETE CASCADE,
    licitacion_id TEXT REFERENCES licitaciones(id) ON DELETE SET NULL,
    titulo TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    estado TEXT DEFAULT 'REGISTRADA', -- REGISTRADA, EN_ANALISIS, RESPONDIDA, RESUELTA, ARCHIVADA
    evidencia TEXT, -- JSON
    respuesta TEXT,
    resolucion TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sanciones (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    proveedor_id TEXT NOT NULL REFERENCES proveedores(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL, -- INHABILITACION, MULTA, AMONESTACION, DESTITUCION
    motivo TEXT NOT NULL,
    monto_multa REAL,
    vigencia_inicio TEXT,
    vigencia_fin TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- ============================================================================
-- 10. AUDIT LEDGER (Bitácora inmutable)
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit_ledger (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    user_email TEXT,
    user_role TEXT,
    entidad_tipo TEXT NOT NULL, -- EXPEDIENTE, DOCUMENTO, CONTRATO, etc.
    entidad_id TEXT NOT NULL,
    accion TEXT NOT NULL, -- CREAR, MODIFICAR, ELIMINAR, CONSULTAR, APROBAR, FIRMAR, PUBLICAR
    descripcion TEXT,
    datos_anteriores TEXT, -- JSON
    datos_nuevos TEXT, -- JSON
    hash_registro TEXT NOT NULL,
    hash_previo TEXT,
    ip_address TEXT,
    user_agent TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_entidad ON audit_ledger(entidad_tipo, entidad_id, accion);
CREATE INDEX IF NOT EXISTS idx_audit_fecha ON audit_ledger(created_at);

-- ============================================================================
-- 11. WORKFLOW / TRANSICIONES
-- ============================================================================

CREATE TABLE IF NOT EXISTS transiciones_workflow (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    tipo_procedimiento TEXT NOT NULL,
    estado_origen TEXT NOT NULL,
    estado_destino TEXT NOT NULL,
    requiere_aprobacion INTEGER DEFAULT 0,
    requiere_rol TEXT,
    condicion_regla TEXT, -- JSON
    acciones_auto TEXT, -- JSON
    sla_horas INTEGER,
    recordatorio_horas INTEGER,
    activa INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(tipo_procedimiento, estado_origen, estado_destino)
);

CREATE TABLE IF NOT EXISTS tareas_workflow (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    expediente_id TEXT NOT NULL REFERENCES expedientes_obra(id) ON DELETE CASCADE,
    asignado_a_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    titulo TEXT NOT NULL,
    descripcion TEXT,
    estado TEXT DEFAULT 'PENDIENTE', -- PENDIENTE, EN_PROGRESO, COMPLETADA, CANCELADA, ESCALADA
    fecha_vencimiento TEXT,
    fecha_completada TEXT,
    sla_horas INTEGER,
    horas_transcurridas INTEGER DEFAULT 0,
    datos TEXT, -- JSON
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- ============================================================================
-- 12. PRESUPUESTO / COSTOS
-- ============================================================================

CREATE TABLE IF NOT EXISTS presupuestos (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    expediente_id TEXT NOT NULL REFERENCES expedientes_obra(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    descripcion TEXT,
    estado TEXT DEFAULT 'BORRADOR', -- BORRADOR, EN_REVISION, APROBADO, RECHAZADO
    zona_economica TEXT DEFAULT 'CENTRO',
    monto_total REAL,
    indirectos_pct REAL DEFAULT 0,
    financiamiento_pct REAL DEFAULT 0,
    utilidad_pct REAL DEFAULT 0,
    cargo_adicional_pct REAL DEFAULT 0,
    creado_por_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    actualizado_por_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS partidas (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    presupuesto_id TEXT NOT NULL REFERENCES presupuestos(id) ON DELETE CASCADE,
    numero TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    unidad TEXT NOT NULL,
    cantidad REAL NOT NULL,
    precio_unitario REAL NOT NULL,
    importe REAL NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conceptos_presupuesto (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    partida_id TEXT REFERENCES partidas(id) ON DELETE CASCADE,
    clave TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    unidad TEXT NOT NULL,
    cantidad REAL NOT NULL,
    precio_unitario REAL NOT NULL,
    importe REAL NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS insumos_presupuesto (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    concepto_id TEXT NOT NULL REFERENCES conceptos_presupuesto(id) ON DELETE CASCADE,
    clave TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    tipo TEXT NOT NULL, -- MATERIAL, MANO_OBRA, MAQUINARIA, INDIRECTO
    unidad TEXT NOT NULL,
    cantidad REAL NOT NULL,
    precio_unitario REAL NOT NULL,
    importe REAL NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- ============================================================================
-- 13. CATALOGO APU (Análisis de Precios Unitarios interno)
-- ============================================================================

CREATE TABLE IF NOT EXISTS catalogos_apu (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    clave TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    tipo TEXT NOT NULL, -- MATERIAL, MANO_OBRA, MAQUINARIA, HERRAMIENTA, SUBCONTRATO, INDIRECTO
    unidad TEXT NOT NULL,
    precio_unitario REAL NOT NULL,
    fuente TEXT NOT NULL, -- CFE, CMIC, CONAGA, CUSTOM
    vigencia_inicio TEXT,
    vigencia_fin TEXT,
    zona_economica TEXT,
    estado TEXT,
    incluye_iva INTEGER DEFAULT 0,
    desglose TEXT, -- JSON
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS precios_unitarios_asignados (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    concepto_id TEXT NOT NULL REFERENCES catalogos_apu(id) ON DELETE CASCADE,
    expediente_id TEXT REFERENCES expedientes_obra(id) ON DELETE CASCADE,
    presupuesto_id TEXT REFERENCES presupuestos(id) ON DELETE CASCADE,
    cantidad REAL NOT NULL DEFAULT 0,
    precio_asignado REAL NOT NULL,
    importe REAL NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- ============================================================================
-- 14. BIM / IFC
-- ============================================================================

CREATE TABLE IF NOT EXISTS modelos_bim (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    expediente_id TEXT NOT NULL REFERENCES expedientes_obra(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    descripcion TEXT,
    estado TEXT DEFAULT 'PROCESANDO', -- PROCESANDO, COMPLETADO, ERROR
    elementos_count INTEGER,
    ifc_data BLOB,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS elementos_bim (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    modelo_id TEXT NOT NULL REFERENCES modelos_bim(id) ON DELETE CASCADE,
    guid TEXT NOT NULL,
    tipo_ifc TEXT NOT NULL,
    nombre TEXT,
    descripcion TEXT,
    volumen REAL,
    area REAL,
    longitud REAL,
    propiedades TEXT, -- JSON
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- ============================================================================
-- 15. PROGRAMACIÓN
-- ============================================================================

CREATE TABLE IF NOT EXISTS programas_obra (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    expediente_id TEXT NOT NULL REFERENCES expedientes_obra(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    descripcion TEXT,
    estado TEXT DEFAULT 'BORRADOR',
    fecha_inicio TEXT,
    fecha_fin TEXT,
    duracion_total INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS actividades_programa (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    programa_id TEXT NOT NULL REFERENCES programas_obra(id) ON DELETE CASCADE,
    clave TEXT NOT NULL,
    nombre TEXT NOT NULL,
    tipo TEXT DEFAULT 'NORMAL', -- NORMAL, HITO, MILESTONE
    duracion_dias INTEGER NOT NULL,
    predecesoras TEXT, -- JSON array
    fecha_inicio TEXT,
    fecha_fin TEXT,
    avance_pct REAL DEFAULT 0,
    costo REAL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- ============================================================================
-- 16. TOPOGRAFÍA
-- ============================================================================

CREATE TABLE IF NOT EXISTS levantamientos (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    expediente_id TEXT NOT NULL REFERENCES expedientes_obra(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL, -- POLIGONAL, GNSS, NIVELACION, TAQUIMETRIA, DRON
    estado TEXT DEFAULT 'EN_CAMPO',
    puntos_count INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS puntos_topograficos (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    levantamiento_id TEXT NOT NULL REFERENCES levantamientos(id) ON DELETE CASCADE,
    x REAL NOT NULL,
    y REAL NOT NULL,
    z REAL,
    codigo TEXT,
    descripcion TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- ============================================================================
-- 17. VALIDADORES
-- ============================================================================

CREATE TABLE IF NOT EXISTS validaciones (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    expediente_id TEXT NOT NULL REFERENCES expedientes_obra(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL, -- DOCUMENTAL, TECNICA, ECONOMICA, LEGAL
    estado TEXT DEFAULT 'PENDIENTE', -- PENDIENTE, EN_REVISION, APROBADO, RECHAZADO, SUBSANAR
    resultado TEXT, -- JSON
    observaciones TEXT,
    validado_por_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
