"""Frozen PostgreSQL baseline at revision 55225d1e7443.

Contains only objects predating subsequent revisions. This snapshot must not
import application models: new tables and columns belong in new migrations.
The prior dynamic create_all baseline created future objects too early and
made fresh installations fail with duplicate relations.
"""
from alembic import op

revision = "55225d1e7443"
down_revision = "06d589924524"
branch_labels = None
depends_on = None

DDL = (
    'CREATE TABLE tenants (\n\tname VARCHAR(255) NOT NULL, \n\tslug VARCHAR(100) NOT NULL, \n\trfc VARCHAR(13), \n\tis_active BOOLEAN NOT NULL, \n\tsettings JSONB, \n\tplan VARCHAR(20) NOT NULL, \n\tplan_vencimiento TIMESTAMP WITH TIME ZONE, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tPRIMARY KEY (id)\n)',
    'CREATE INDEX ix_tenants_plan ON tenants (plan)',
    'CREATE UNIQUE INDEX ix_tenants_slug ON tenants (slug)',
    'CREATE TABLE workflows (\n\texpediente_id UUID NOT NULL, \n\tnombre VARCHAR(255) NOT NULL, \n\tdescripcion TEXT, \n\ttipo VARCHAR(50) NOT NULL, \n\testado VARCHAR(20) NOT NULL, \n\tpaso_actual_id UUID, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id)\n)',
    'CREATE INDEX ix_workflows_tipo ON workflows (tipo)',
    'CREATE INDEX ix_workflows_tenant_id ON workflows (tenant_id)',
    'CREATE INDEX ix_workflows_estado ON workflows (estado)',
    'CREATE INDEX ix_workflows_creado_por_id ON workflows (creado_por_id)',
    'CREATE INDEX ix_workflows_expediente_id ON workflows (expediente_id)',
    'CREATE TABLE workflow_pasos (\n\tworkflow_id UUID NOT NULL, \n\tnombre VARCHAR(255) NOT NULL, \n\tdescripcion TEXT, \n\torden INTEGER NOT NULL, \n\tresponsable_id UUID, \n\testado VARCHAR(20) NOT NULL, \n\tfecha_limite TIMESTAMP WITH TIME ZONE, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id)\n)',
    'CREATE INDEX ix_workflow_pasos_tenant_id ON workflow_pasos (tenant_id)',
    'CREATE INDEX ix_workflow_pasos_creado_por_id ON workflow_pasos (creado_por_id)',
    'CREATE INDEX ix_workflow_pasos_estado ON workflow_pasos (estado)',
    'CREATE INDEX ix_workflow_pasos_workflow_id ON workflow_pasos (workflow_id)',
    'CREATE INDEX ix_workflow_paso_workflow_orden ON workflow_pasos (workflow_id, orden)',
    'CREATE TABLE notification_logs (\n\tdestinatario VARCHAR(255) NOT NULL, \n\ttipo VARCHAR(20) NOT NULL, \n\tasunto VARCHAR(500) NOT NULL, \n\tmensaje TEXT NOT NULL, \n\tmetadatos JSONB, \n\testado VARCHAR(20) NOT NULL, \n\tleida_at TIMESTAMP WITH TIME ZONE, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tPRIMARY KEY (id)\n)',
    'CREATE INDEX ix_notification_logs_destinatario ON notification_logs (destinatario)',
    'CREATE INDEX ix_notification_logs_estado ON notification_logs (estado)',
    'CREATE TABLE plan_limites (\n\tplan VARCHAR(20) NOT NULL, \n\tmax_proyectos_activos INTEGER, \n\tmax_corridas_costeo_mes INTEGER, \n\tmax_consultas_legl_mes INTEGER, \n\tmax_catalogos INTEGER, \n\tmax_usuarios INTEGER, \n\tpermite_api BOOLEAN NOT NULL, \n\tpermite_jobs_pesados BOOLEAN NOT NULL, \n\tpermite_multi_tenant BOOLEAN NOT NULL, \n\tprecio_mensual NUMERIC(10, 2) NOT NULL, \n\tmoneda VARCHAR(3) NOT NULL, \n\tstripe_price_id VARCHAR(255), \n\tmercadopago_plan_id VARCHAR(255), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tPRIMARY KEY (id)\n)',
    'CREATE UNIQUE INDEX ix_plan_limites_plan ON plan_limites (plan)',
    'CREATE TABLE app_modulos (\n\tapp_id VARCHAR(100) NOT NULL, \n\tnombre VARCHAR(255) NOT NULL, \n\testado VARCHAR(20) NOT NULL, \n\trequiere_plan VARCHAR(20), \n\trequiere_rol JSONB, \n\tactivo BOOLEAN NOT NULL, \n\torden INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tPRIMARY KEY (id)\n)',
    'CREATE UNIQUE INDEX ix_app_modulos_app_id ON app_modulos (app_id)',
    'CREATE TABLE users (\n\temail VARCHAR(255) NOT NULL, \n\thashed_password VARCHAR(255) NOT NULL, \n\tfull_name VARCHAR(255) NOT NULL, \n\trfc VARCHAR(13), \n\tcurp VARCHAR(18), \n\trole VARCHAR(50) NOT NULL, \n\tis_active BOOLEAN NOT NULL, \n\tis_verified BOOLEAN NOT NULL, \n\tlast_login TIMESTAMP WITH TIME ZONE, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_users_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_users_tenant_id ON users (tenant_id)',
    'CREATE INDEX ix_users_rfc ON users (rfc)',
    'CREATE UNIQUE INDEX ix_users_email ON users (email)',
    'CREATE TABLE catalogo_procedimientos (\n\tclave VARCHAR(20) NOT NULL, \n\tnombre VARCHAR(255) NOT NULL, \n\ttipo VARCHAR(50) NOT NULL, \n\tdescripcion TEXT, \n\tobjetivo TEXT, \n\tmonto_minimo NUMERIC(15, 2), \n\tmonto_maximo NUMERIC(15, 2), \n\trequisitos_participacion JSONB, \n\tdocumentos_requeridos JSONB, \n\tetapas JSONB, \n\tplazo_minimo_dias INTEGER, \n\tplazo_maximo_dias INTEGER, \n\tvigente BOOLEAN NOT NULL, \n\tfecha_vigencia TIMESTAMP WITH TIME ZONE, \n\tbase_legal TEXT, \n\tarticulos_aplicables JSONB, \n\tpalabras_clave JSONB, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_catalogo_procedimientos_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_cat_proc_vigente ON catalogo_procedimientos (vigente)',
    'CREATE INDEX ix_catalogo_procedimientos_clave ON catalogo_procedimientos (clave)',
    'CREATE INDEX ix_cat_proc_clave_tipo ON catalogo_procedimientos (clave, tipo)',
    'CREATE INDEX ix_catalogo_procedimientos_tipo ON catalogo_procedimientos (tipo)',
    'CREATE INDEX ix_catalogo_procedimientos_tenant_id ON catalogo_procedimientos (tenant_id)',
    'CREATE TABLE catalogo_juridico (\n\tclave VARCHAR(50) NOT NULL, \n\tnombre VARCHAR(255) NOT NULL, \n\ttipo VARCHAR(50) NOT NULL, \n\tdescripcion TEXT, \n\tresumen TEXT, \n\tarticulos_relevantes JSONB, \n\tambito_aplicacion VARCHAR(100), \n\tfecha_publicacion TIMESTAMP WITH TIME ZONE, \n\tfecha_vigencia TIMESTAMP WITH TIME ZONE, \n\tfecha_modificacion TIMESTAMP WITH TIME ZONE, \n\tvigente BOOLEAN NOT NULL, \n\tdocumento_url VARCHAR(500), \n\treglas JSONB, \n\tpalabras_clave JSONB, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_catalogo_juridico_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_cat_juridico_vigente ON catalogo_juridico (vigente)',
    'CREATE INDEX ix_catalogo_juridico_tipo ON catalogo_juridico (tipo)',
    'CREATE INDEX ix_cat_juridico_clave_tipo ON catalogo_juridico (clave, tipo)',
    'CREATE INDEX ix_catalogo_juridico_clave ON catalogo_juridico (clave)',
    'CREATE INDEX ix_catalogo_juridico_tenant_id ON catalogo_juridico (tenant_id)',
    'CREATE TABLE checks_validacion (\n\tcodigo VARCHAR(50) NOT NULL, \n\tnombre VARCHAR(255) NOT NULL, \n\tdescripcion TEXT, \n\tcategoria VARCHAR(50) NOT NULL, \n\tlogica JSONB NOT NULL, \n\tmensaje_exito VARCHAR(500), \n\tmensaje_error VARCHAR(500), \n\tseveridad VARCHAR(20) NOT NULL, \n\tactivo BOOLEAN NOT NULL, \n\torden INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_checks_validacion_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_checks_validacion_categoria ON checks_validacion (categoria)',
    'CREATE INDEX ix_checks_validacion_tenant_id ON checks_validacion (tenant_id)',
    'CREATE UNIQUE INDEX ix_checks_validacion_codigo ON checks_validacion (codigo)',
    'CREATE INDEX ix_checks_orden ON checks_validacion (orden)',
    'CREATE INDEX ix_checks_categoria_activo ON checks_validacion (categoria, activo)',
    'CREATE TABLE tenant_uso (\n\tperiodo VARCHAR(7) NOT NULL, \n\tcorridas_costeo INTEGER NOT NULL, \n\tconsultas_legl INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_tenant_uso_periodo UNIQUE (tenant_id, periodo), \n\tCONSTRAINT fk_baseline_tenant_uso_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_tenant_uso_tenant_id ON tenant_uso (tenant_id)',
    'CREATE INDEX ix_tenant_uso_periodo ON tenant_uso (periodo)',
    'CREATE TABLE invitations (\n\temail VARCHAR(255) NOT NULL, \n\trole VARCHAR(50) NOT NULL, \n\ttoken_hash VARCHAR(64) NOT NULL, \n\tinvited_by UUID, \n\tstatus VARCHAR(20) NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\taccepted_at TIMESTAMP WITH TIME ZONE, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_invitations_invited_by FOREIGN KEY(invited_by) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_invitations_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_invitations_status ON invitations (status)',
    'CREATE INDEX ix_invitations_tenant_id ON invitations (tenant_id)',
    'CREATE INDEX ix_invitations_tenant_email_status ON invitations (tenant_id, email, status)',
    'CREATE INDEX ix_invitations_email ON invitations (email)',
    'CREATE UNIQUE INDEX ix_invitations_token_hash ON invitations (token_hash)',
    'CREATE TABLE entidades (\n\tclave VARCHAR(50) NOT NULL, \n\tnombre VARCHAR(500) NOT NULL, \n\tnombre_corto VARCHAR(100), \n\ttipo VARCHAR(50) NOT NULL, \n\tdireccion TEXT, \n\temail VARCHAR(255), \n\ttelefono VARCHAR(50), \n\tconfig JSONB, \n\tbranding JSONB, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_entidades_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_entidades_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_entidades_tipo ON entidades (tipo)',
    'CREATE UNIQUE INDEX ix_entidades_clave ON entidades (clave)',
    'CREATE INDEX ix_entidades_creado_por_id ON entidades (creado_por_id)',
    'CREATE TABLE audit_ledger (\n\tuser_id UUID, \n\tuser_email VARCHAR(255), \n\tuser_role VARCHAR(50), \n\tentidad_tipo VARCHAR(50) NOT NULL, \n\tentidad_id VARCHAR(100) NOT NULL, \n\taccion VARCHAR(50) NOT NULL, \n\tdescripcion TEXT, \n\tdatos_anteriores JSONB, \n\tdatos_nuevos JSONB, \n\thash_registro VARCHAR(64) NOT NULL, \n\thash_previo VARCHAR(64), \n\tip_address VARCHAR(45), \n\tuser_agent VARCHAR(500), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_audit_ledger_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_audit_ledger_user_id FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_audit_ledger_hash_previo ON audit_ledger (hash_previo)',
    'CREATE INDEX ix_audit_ledger_tenant_id ON audit_ledger (tenant_id)',
    'CREATE INDEX ix_audit_ledger_accion ON audit_ledger (accion)',
    'CREATE INDEX ix_audit_ledger_user_id ON audit_ledger (user_id)',
    'CREATE INDEX ix_audit_fecha ON audit_ledger (created_at)',
    'CREATE INDEX ix_audit_ledger_entidad_id ON audit_ledger (entidad_id)',
    'CREATE INDEX ix_audit_entidad_accion ON audit_ledger (entidad_tipo, entidad_id, accion)',
    'CREATE INDEX ix_audit_ledger_hash_registro ON audit_ledger (hash_registro)',
    'CREATE INDEX ix_audit_ledger_entidad_tipo ON audit_ledger (entidad_tipo)',
    'CREATE TABLE reglas_negocio (\n\tnombre VARCHAR(255) NOT NULL, \n\tdescripcion TEXT, \n\tcodigo VARCHAR(50) NOT NULL, \n\tcategoria VARCHAR(50) NOT NULL, \n\ttipo_procedimiento VARCHAR(50), \n\tcondicion JSONB NOT NULL, \n\taccion VARCHAR(50) NOT NULL, \n\tparametros_accion JSONB, \n\tseveridad VARCHAR(20) NOT NULL, \n\tactiva BOOLEAN NOT NULL, \n\tprioridad INTEGER NOT NULL, \n\tfecha_vigencia TIMESTAMP WITH TIME ZONE, \n\tfecha_expiracion TIMESTAMP WITH TIME ZONE, \n\tversion INTEGER NOT NULL, \n\tcreado_por_id UUID, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_reglas_negocio_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_reglas_negocio_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT uq_regla_codigo_tenant UNIQUE (tenant_id, codigo)\n)',
    'CREATE INDEX ix_reglas_negocio_tenant_id ON reglas_negocio (tenant_id)',
    'CREATE INDEX ix_reglas_codigo ON reglas_negocio (codigo)',
    'CREATE INDEX ix_reglas_negocio_categoria ON reglas_negocio (categoria)',
    'CREATE INDEX ix_reglas_negocio_codigo ON reglas_negocio (codigo)',
    'CREATE INDEX ix_reglas_activa_categoria ON reglas_negocio (activa, categoria)',
    'CREATE INDEX ix_reglas_prioridad ON reglas_negocio (prioridad)',
    'CREATE TABLE transiciones_workflow (\n\ttipo_procedimiento VARCHAR(50) NOT NULL, \n\testado_origen VARCHAR(50) NOT NULL, \n\testado_destino VARCHAR(50) NOT NULL, \n\trequiere_aprobacion BOOLEAN NOT NULL, \n\trequiere_rol VARCHAR(50), \n\tcondicion_regla JSONB, \n\tacciones_auto JSONB, \n\tsla_horas INTEGER, \n\trecordatorio_horas INTEGER, \n\tactiva BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_transicionworkflow_tenant UNIQUE (tenant_id, tipo_procedimiento, estado_origen, estado_destino), \n\tCONSTRAINT fk_baseline_transiciones_workflow_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_transiciones_workflow_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_transiciones_workflow_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_transiciones_workflow_creado_por_id ON transiciones_workflow (creado_por_id)',
    'CREATE INDEX ix_transiciones_workflow_tipo_procedimiento ON transiciones_workflow (tipo_procedimiento)',
    'CREATE INDEX ix_transiciones_workflow_estado_destino ON transiciones_workflow (estado_destino)',
    'CREATE INDEX ix_transiciones_workflow_tenant_id ON transiciones_workflow (tenant_id)',
    'CREATE INDEX ix_transicion_proc ON transiciones_workflow (tipo_procedimiento, estado_origen, estado_destino)',
    'CREATE INDEX ix_transiciones_workflow_estado_origen ON transiciones_workflow (estado_origen)',
    'CREATE TABLE workflow_transiciones (\n\tworkflow_id UUID NOT NULL, \n\tpaso_origen_id UUID NOT NULL, \n\tpaso_destino_id UUID NOT NULL, \n\tnombre VARCHAR(100) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_workflow_transiciones_workflow_id FOREIGN KEY(workflow_id) REFERENCES workflows (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_workflow_transiciones_paso_destino_id FOREIGN KEY(paso_destino_id) REFERENCES workflow_pasos (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_workflow_transiciones_paso_origen_id FOREIGN KEY(paso_origen_id) REFERENCES workflow_pasos (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_workflow_transiciones_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_workflow_transiciones_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_workflow_transiciones_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_workflow_transiciones_paso_destino_id ON workflow_transiciones (paso_destino_id)',
    'CREATE INDEX ix_workflow_transicion_origen_destino ON workflow_transiciones (paso_origen_id, paso_destino_id)',
    'CREATE INDEX ix_workflow_transiciones_creado_por_id ON workflow_transiciones (creado_por_id)',
    'CREATE INDEX ix_workflow_transiciones_workflow_id ON workflow_transiciones (workflow_id)',
    'CREATE INDEX ix_workflow_transiciones_paso_origen_id ON workflow_transiciones (paso_origen_id)',
    'CREATE INDEX ix_workflow_transiciones_tenant_id ON workflow_transiciones (tenant_id)',
    'CREATE TABLE proveedores (\n\ttipo_persona VARCHAR(50) NOT NULL, \n\trfc VARCHAR(13) NOT NULL, \n\trazon_social VARCHAR(500) NOT NULL, \n\tnombre_comercial VARCHAR(500), \n\temail VARCHAR(255), \n\ttelefono VARCHAR(50), \n\tdireccion TEXT, \n\testado VARCHAR(50) NOT NULL, \n\tconstancia_fiscal VARCHAR(500), \n\tacta_constitutiva VARCHAR(500), \n\tpoder_notarial VARCHAR(500), \n\tcapacidad_ejecucion JSONB, \n\tespecialidades JSONB, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_proveedores_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_proveedores_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_proveedores_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE UNIQUE INDEX ix_proveedores_rfc ON proveedores (rfc)',
    'CREATE INDEX ix_proveedores_tenant_id ON proveedores (tenant_id)',
    'CREATE INDEX ix_proveedores_creado_por_id ON proveedores (creado_por_id)',
    'CREATE INDEX ix_proveedores_estado ON proveedores (estado)',
    'CREATE TABLE reglas_cumplimiento_catalogo (\n\tcatalogo_juridico_id UUID NOT NULL, \n\tnombre VARCHAR(255) NOT NULL, \n\tdescripcion TEXT, \n\tcondicion JSONB NOT NULL, \n\tseveridad VARCHAR(20) NOT NULL, \n\ttipo_procedimiento VARCHAR(50), \n\tactiva BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_reglas_cumplimiento_catalogo_catalogo_juridico_id FOREIGN KEY(catalogo_juridico_id) REFERENCES catalogo_juridico (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_reglas_cumplimiento_catalogo_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_reglas_cumplimiento_catalogo_tenant_id ON reglas_cumplimiento_catalogo (tenant_id)',
    'CREATE TABLE expedientes_obra (\n\tidentificador VARCHAR(100) NOT NULL, \n\ttitulo VARCHAR(500) NOT NULL, \n\tdescripcion TEXT, \n\torgano VARCHAR(255) NOT NULL, \n\tunidad_administrativa VARCHAR(255) NOT NULL, \n\tserie_documental VARCHAR(100) NOT NULL, \n\tsubserie_documental VARCHAR(100) NOT NULL, \n\tproyecto_id VARCHAR(100), \n\tproyecto_nombre VARCHAR(500), \n\tubicacion_obra TEXT, \n\tmonto_contrato NUMERIC(18, 2), \n\tplazo_dias INTEGER, \n\ttipo_contrato VARCHAR(50) NOT NULL, \n\testado VARCHAR(50) NOT NULL, \n\tclasificacion VARCHAR(50) NOT NULL, \n\tresponsable_tecnico VARCHAR(255), \n\tresponsable_ejecutivo VARCHAR(255), \n\tresponsable_id UUID, \n\tmetadatos JSONB, \n\tmerkle_root VARCHAR(64), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_expediente_tenant_identificador UNIQUE (tenant_id, identificador), \n\tCONSTRAINT uq_expediente_tenant_id UNIQUE (tenant_id, id), \n\tCONSTRAINT fk_baseline_expedientes_obra_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_expedientes_obra_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_expedientes_obra_responsable_id FOREIGN KEY(responsable_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_expedientes_obra_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_expedientes_obra_creado_por_id ON expedientes_obra (creado_por_id)',
    'CREATE INDEX ix_expedientes_obra_identificador ON expedientes_obra (identificador)',
    'CREATE INDEX idx_expediente_organo ON expedientes_obra (organo)',
    'CREATE INDEX idx_expediente_estado_tenant ON expedientes_obra (tenant_id, estado)',
    'CREATE INDEX ix_expedientes_obra_estado ON expedientes_obra (estado)',
    'CREATE INDEX ix_expedientes_obra_tenant_id ON expedientes_obra (tenant_id)',
    'CREATE TABLE reglas_cumplimiento (\n\tnombre VARCHAR(255) NOT NULL, \n\tdescripcion TEXT, \n\ttipo_procedimiento VARCHAR(50) NOT NULL, \n\tetapa VARCHAR(50) NOT NULL, \n\trequisitos JSONB, \n\tobligatorio BOOLEAN NOT NULL, \n\tactiva BOOLEAN NOT NULL, \n\tcondicion_evaluacion TEXT, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_reglas_cumplimiento_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_reglas_cumplimiento_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_reglas_cumplimiento_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_reglas_cumplimiento_tipo_procedimiento ON reglas_cumplimiento (tipo_procedimiento)',
    'CREATE INDEX ix_reglas_cumplimiento_creado_por_id ON reglas_cumplimiento (creado_por_id)',
    'CREATE INDEX ix_reglas_cumplimiento_etapa ON reglas_cumplimiento (etapa)',
    'CREATE INDEX ix_reglas_cumplimiento_tenant_id ON reglas_cumplimiento (tenant_id)',
    'CREATE TABLE catalogos_apu (\n\tclave VARCHAR(50) NOT NULL, \n\tdescripcion TEXT NOT NULL, \n\ttipo VARCHAR(50) NOT NULL, \n\tunidad VARCHAR(20) NOT NULL, \n\tprecio_unitario NUMERIC(18, 4) NOT NULL, \n\tfuente VARCHAR(100) NOT NULL, \n\tvigencia_inicio VARCHAR(10), \n\tvigencia_fin VARCHAR(10), \n\tzona_economica VARCHAR(100), \n\testado VARCHAR(100), \n\tincluye_iva BOOLEAN NOT NULL, \n\tdesglose JSONB, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_catalogo_apu_tenant_clave_fuente_zona UNIQUE (tenant_id, clave, fuente, zona_economica), \n\tCONSTRAINT fk_baseline_catalogos_apu_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_catalogos_apu_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_catalogos_apu_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_catalogos_apu_tenant_id ON catalogos_apu (tenant_id)',
    'CREATE INDEX ix_catalogos_apu_clave ON catalogos_apu (clave)',
    'CREATE INDEX ix_catalogos_apu_creado_por_id ON catalogos_apu (creado_por_id)',
    'CREATE INDEX ix_catalogo_apu_clave_fuente ON catalogos_apu (clave, fuente, zona_economica)',
    'CREATE TABLE catalogo_fuentes (\n\tnombre VARCHAR(100) NOT NULL, \n\ttipo VARCHAR(50) NOT NULL, \n\tvigencia_inicio VARCHAR(10) NOT NULL, \n\tvigencia_fin VARCHAR(10) NOT NULL, \n\tdescripcion TEXT, \n\turl_fuente VARCHAR(1000), \n\tactivo BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_catalogo_fuentes_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_catalogo_fuentes_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_catalogo_fuentes_creado_por_id ON catalogo_fuentes (creado_por_id)',
    'CREATE INDEX ix_catalogo_fuentes_tipo ON catalogo_fuentes (tipo)',
    'CREATE TABLE suscripciones (\n\tplan VARCHAR(20) NOT NULL, \n\tproveedor VARCHAR(20) NOT NULL, \n\testado VARCHAR(20) NOT NULL, \n\texternal_id VARCHAR(255), \n\tfecha_inicio TIMESTAMP WITH TIME ZONE, \n\tfecha_fin TIMESTAMP WITH TIME ZONE, \n\tmonto NUMERIC(10, 2), \n\tmoneda VARCHAR(3) NOT NULL, \n\tmetadatos JSONB, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_suscripciones_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_suscripciones_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_suscripciones_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_suscripcion_tenant_estado ON suscripciones (tenant_id, estado)',
    'CREATE INDEX ix_suscripciones_creado_por_id ON suscripciones (creado_por_id)',
    'CREATE INDEX ix_suscripciones_plan ON suscripciones (plan)',
    'CREATE INDEX ix_suscripciones_estado ON suscripciones (estado)',
    'CREATE INDEX ix_suscripciones_external_id ON suscripciones (external_id)',
    'CREATE INDEX ix_suscripciones_tenant_id ON suscripciones (tenant_id)',
    'CREATE TABLE unidades_administrativas (\n\tentidad_id UUID NOT NULL, \n\tclave VARCHAR(50) NOT NULL, \n\tnombre VARCHAR(500) NOT NULL, \n\ttipo VARCHAR(50) NOT NULL, \n\tresponsable_nombre VARCHAR(255), \n\tresponsable_email VARCHAR(255), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_unidades_administrativas_entidad_id FOREIGN KEY(entidad_id) REFERENCES entidades (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_unidades_administrativas_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_unidades_administrativas_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_unidades_administrativas_tipo ON unidades_administrativas (tipo)',
    'CREATE INDEX ix_unidades_administrativas_creado_por_id ON unidades_administrativas (creado_por_id)',
    'CREATE UNIQUE INDEX ix_unidad_entidad_clave ON unidades_administrativas (entidad_id, clave)',
    'CREATE INDEX ix_unidades_administrativas_entidad_id ON unidades_administrativas (entidad_id)',
    'CREATE TABLE ejecucion_reglas (\n\tregla_id UUID NOT NULL, \n\texpediente_id UUID NOT NULL, \n\tcontexto JSONB NOT NULL, \n\tresultado BOOLEAN NOT NULL, \n\taccion_ejecutada VARCHAR(50), \n\tmensaje TEXT, \n\testado VARCHAR(50) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_ejecucion_reglas_regla_id FOREIGN KEY(regla_id) REFERENCES reglas_negocio (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_ejecucion_reglas_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_ejecucion_reglas_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_ejecucion_regla_exp ON ejecucion_reglas (regla_id, expediente_id)',
    'CREATE INDEX ix_ejecucion_estado ON ejecucion_reglas (estado)',
    'CREATE INDEX ix_ejecucion_reglas_tenant_id ON ejecucion_reglas (tenant_id)',
    'CREATE TABLE tareas_workflow (\n\texpediente_id UUID NOT NULL, \n\tasignado_a_id UUID, \n\ttitulo VARCHAR(500) NOT NULL, \n\tdescripcion TEXT, \n\testado VARCHAR(50) NOT NULL, \n\tfecha_vencimiento VARCHAR(10), \n\tfecha_completada VARCHAR(10), \n\tsla_horas INTEGER, \n\thoras_transcurridas INTEGER NOT NULL, \n\tdatos JSONB, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_tareas_workflow_asignado_a_id FOREIGN KEY(asignado_a_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_tareas_workflow_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_tareas_workflow_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_tareas_workflow_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_tareas_workflow_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_tareas_workflow_tenant_id ON tareas_workflow (tenant_id)',
    'CREATE INDEX ix_tareas_workflow_creado_por_id ON tareas_workflow (creado_por_id)',
    'CREATE INDEX ix_tareas_workflow_estado ON tareas_workflow (estado)',
    'CREATE INDEX ix_tareas_workflow_expediente_id ON tareas_workflow (expediente_id)',
    'CREATE TABLE workflow_condiciones (\n\ttransicion_id UUID NOT NULL, \n\tcampo VARCHAR(255) NOT NULL, \n\toperador VARCHAR(20) NOT NULL, \n\tvalor_referencia JSONB, \n\tobligatoria BOOLEAN NOT NULL, \n\torden INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_workflow_condiciones_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_workflow_condiciones_transicion_id FOREIGN KEY(transicion_id) REFERENCES workflow_transiciones (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_workflow_condiciones_tenant_id ON workflow_condiciones (tenant_id)',
    'CREATE INDEX ix_workflow_condiciones_transicion_id ON workflow_condiciones (transicion_id)',
    'CREATE TABLE representantes_legales (\n\tproveedor_id UUID NOT NULL, \n\tnombre VARCHAR(255) NOT NULL, \n\tcurp VARCHAR(18), \n\trfc VARCHAR(13), \n\temail VARCHAR(255), \n\ttelefono VARCHAR(50), \n\tefirma_serial VARCHAR(255), \n\tefirma_vigencia_inicio VARCHAR(10), \n\tefirma_vigencia_fin VARCHAR(10), \n\tefirma_activa BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_representantes_legales_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_representantes_legales_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_representantes_legales_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_representantes_legales_proveedor_id FOREIGN KEY(proveedor_id) REFERENCES proveedores (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_representantes_legales_tenant_id ON representantes_legales (tenant_id)',
    'CREATE INDEX ix_representantes_legales_creado_por_id ON representantes_legales (creado_por_id)',
    'CREATE TABLE documentos (\n\tidentificador VARCHAR(100) NOT NULL, \n\tnombre VARCHAR(500) NOT NULL, \n\ttipo_documental VARCHAR(50) NOT NULL, \n\tformato VARCHAR(20) NOT NULL, \n\tstorage_path VARCHAR(1000) NOT NULL, \n\tstorage_bucket VARCHAR(255) NOT NULL, \n\tsize_bytes INTEGER NOT NULL, \n\thash_sha256 VARCHAR(64) NOT NULL, \n\tcifrado BOOLEAN NOT NULL, \n\tnonce_cifrado VARCHAR(255), \n\ttag_cifrado VARCHAR(255), \n\tencryption_key_enc VARCHAR(512), \n\tmetadatos JSONB, \n\texpediente_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_documentos_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_documentos_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_documentos_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_documentos_creado_por_id ON documentos (creado_por_id)',
    'CREATE INDEX ix_documentos_expediente_id ON documentos (expediente_id)',
    'CREATE INDEX ix_documentos_identificador ON documentos (identificador)',
    'CREATE TABLE planeacion_expediente (\n\texpediente_id UUID NOT NULL, \n\tnecesidad TEXT NOT NULL, \n\tjustificacion TEXT NOT NULL, \n\tobjetivo TEXT NOT NULL, \n\talcance TEXT, \n\tentregables JSONB, \n\tpresupuesto_estimado NUMERIC(15, 2), \n\tfuente_financiamiento VARCHAR(255), \n\tfecha_inicio_esperada TIMESTAMP WITH TIME ZONE, \n\tfecha_fin_esperada TIMESTAMP WITH TIME ZONE, \n\tduracion_estimada_dias INTEGER, \n\thitos_planeacion JSONB, \n\triesgos JSONB, \n\taprobado BOOLEAN NOT NULL, \n\tfecha_aprobacion TIMESTAMP WITH TIME ZONE, \n\taprobado_por_id UUID, \n\testado VARCHAR(50) NOT NULL, \n\tobservaciones TEXT, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_planeacion_expediente_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_planeacion_expediente_aprobado_por_id FOREIGN KEY(aprobado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_planeacion_expediente_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_planeacion_expediente_tenant_id ON planeacion_expediente (tenant_id)',
    'CREATE INDEX ix_planeacion_estado ON planeacion_expediente (estado)',
    'CREATE INDEX ix_planeacion_expediente ON planeacion_expediente (expediente_id)',
    'CREATE INDEX ix_planeacion_expediente_expediente_id ON planeacion_expediente (expediente_id)',
    'CREATE TABLE licitaciones (\n\texpediente_id UUID NOT NULL, \n\tfolio VARCHAR(100) NOT NULL, \n\ttipo_procedimiento VARCHAR(50) NOT NULL, \n\testado VARCHAR(50) NOT NULL, \n\tobjeto TEXT NOT NULL, \n\tmonto_estimado NUMERIC(18, 4), \n\tplazo_dias INTEGER, \n\tfecha_convocatoria VARCHAR(10), \n\tfecha_junta_aclaraciones VARCHAR(10), \n\tfecha_apertura VARCHAR(10), \n\tfecha_fallo VARCHAR(10), \n\tfecha_adjudicacion VARCHAR(10), \n\treglas_participacion JSONB, \n\tbases TEXT, \n\tbases_version INTEGER NOT NULL, \n\tbases_congeladas BOOLEAN NOT NULL, \n\tmatriz_evaluacion JSONB, \n\tdictamen TEXT, \n\tjustificacion_procedimiento TEXT, \n\tpresupuesto_dependencia_miles NUMERIC(18, 2), \n\tinvestigacion_mercado JSONB, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_licitaciones_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_licitaciones_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_licitaciones_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT uq_licitacion_expediente_folio UNIQUE (expediente_id, folio), \n\tCONSTRAINT fk_baseline_licitaciones_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_licitaciones_tenant_id ON licitaciones (tenant_id)',
    'CREATE INDEX ix_licitaciones_creado_por_id ON licitaciones (creado_por_id)',
    'CREATE INDEX ix_licitaciones_expediente_id ON licitaciones (expediente_id)',
    'CREATE INDEX ix_licitaciones_estado ON licitaciones (estado)',
    'CREATE INDEX ix_licitaciones_folio ON licitaciones (folio)',
    'CREATE TABLE modelos_bim (\n\texpediente_id UUID NOT NULL, \n\tidentificador VARCHAR(100) NOT NULL, \n\tnombre VARCHAR(500) NOT NULL, \n\tdescripcion VARCHAR(2000), \n\truta_archivo VARCHAR(1000) NOT NULL, \n\tversion_ifc VARCHAR(50), \n\ttamano_bytes INTEGER, \n\tnum_elementos INTEGER NOT NULL, \n\tniveles JSON, \n\testado_procesamiento VARCHAR(20) NOT NULL, \n\terror_procesamiento VARCHAR(2000), \n\tunidades_ifc VARCHAR(50), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_modelobim_expediente_identificador UNIQUE (expediente_id, identificador), \n\tCONSTRAINT fk_baseline_modelos_bim_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_modelos_bim_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_modelos_bim_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_modelos_bim_creado_por_id ON modelos_bim (creado_por_id)',
    'CREATE INDEX ix_modelos_bim_expediente_id ON modelos_bim (expediente_id)',
    'CREATE INDEX ix_modelos_bim_estado_procesamiento ON modelos_bim (estado_procesamiento)',
    'CREATE TABLE presupuestos (\n\tidentificador VARCHAR(100) NOT NULL, \n\tnombre VARCHAR(500) NOT NULL, \n\tdescripcion TEXT, \n\tmonto_directo NUMERIC(18, 2) NOT NULL, \n\tmonto_indirecto NUMERIC(18, 2) NOT NULL, \n\tmonto_utilidad NUMERIC(18, 2) NOT NULL, \n\tmonto_impuesto NUMERIC(18, 2) NOT NULL, \n\tmonto_total NUMERIC(18, 2) NOT NULL, \n\tmoneda VARCHAR(3) NOT NULL, \n\tfactor_indirecto NUMERIC(8, 4) NOT NULL, \n\tfactor_utilidad NUMERIC(8, 4) NOT NULL, \n\tfactor_impuesto NUMERIC(8, 4) NOT NULL, \n\tzona_economica VARCHAR(50) NOT NULL, \n\tplazo_dias INTEGER, \n\tmetadatos JSONB, \n\tresultado_montecarlo JSONB, \n\tresultado_determinista JSONB, \n\testado VARCHAR(20) NOT NULL, \n\texpediente_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_presupuestos_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT uq_presupuesto_expediente_identificador UNIQUE (expediente_id, identificador), \n\tCONSTRAINT fk_baseline_presupuestos_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_presupuestos_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE, \n\tCONSTRAINT ck_presupuesto_factor_utilidad CHECK (factor_utilidad BETWEEN 0 AND 1), \n\tCONSTRAINT ck_presupuesto_factor_indirecto CHECK (factor_indirecto BETWEEN 0 AND 1), \n\tCONSTRAINT ck_presupuesto_factor_impuesto CHECK (factor_impuesto BETWEEN 0 AND 1)\n)',
    'CREATE INDEX ix_presupuestos_creado_por_id ON presupuestos (creado_por_id)',
    'CREATE INDEX ix_presupuestos_expediente_id ON presupuestos (expediente_id)',
    'CREATE INDEX idx_presupuesto_expediente ON presupuestos (expediente_id)',
    'CREATE INDEX ix_presupuestos_estado ON presupuestos (estado)',
    'CREATE TABLE conceptos_catalogo (\n\tfuente_id UUID NOT NULL, \n\tclave VARCHAR(50) NOT NULL, \n\tdescripcion TEXT NOT NULL, \n\tdescripcion_larga TEXT, \n\tunidad VARCHAR(20) NOT NULL, \n\tprecio_unitario NUMERIC(18, 4) NOT NULL, \n\tzona_economica VARCHAR(100), \n\testado VARCHAR(100), \n\tregion VARCHAR(100), \n\tincluye_iva BOOLEAN NOT NULL, \n\tactivo BOOLEAN NOT NULL, \n\tdesglose JSONB, \n\tpagina_origen INTEGER, \n\thash_linea VARCHAR(64), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_conceptos_catalogo_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_conceptos_catalogo_fuente_id FOREIGN KEY(fuente_id) REFERENCES catalogo_fuentes (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_conceptos_catalogo_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_concepto_busqueda ON conceptos_catalogo (descripcion)',
    'CREATE INDEX ix_conceptos_catalogo_zona_economica ON conceptos_catalogo (zona_economica)',
    'CREATE INDEX ix_conceptos_catalogo_fuente_id ON conceptos_catalogo (fuente_id)',
    'CREATE INDEX ix_conceptos_catalogo_clave ON conceptos_catalogo (clave)',
    'CREATE UNIQUE INDEX ix_concepto_clave_fuente_zona ON conceptos_catalogo (clave, fuente_id, zona_economica)',
    'CREATE INDEX ix_conceptos_catalogo_estado ON conceptos_catalogo (estado)',
    'CREATE INDEX ix_conceptos_catalogo_creado_por_id ON conceptos_catalogo (creado_por_id)',
    'CREATE TABLE insumos_catalogo (\n\tfuente_id UUID NOT NULL, \n\tclave VARCHAR(50) NOT NULL, \n\tdescripcion TEXT NOT NULL, \n\ttipo VARCHAR(50) NOT NULL, \n\tunidad VARCHAR(20) NOT NULL, \n\tprecio_unitario NUMERIC(18, 4) NOT NULL, \n\tcategoria VARCHAR(100), \n\tsubcategoria VARCHAR(100), \n\tzona_economica VARCHAR(100), \n\testado VARCHAR(100), \n\tincluye_iva BOOLEAN NOT NULL, \n\tactivo BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_insumos_catalogo_fuente_id FOREIGN KEY(fuente_id) REFERENCES catalogo_fuentes (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_insumos_catalogo_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_insumos_catalogo_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_insumos_catalogo_clave ON insumos_catalogo (clave)',
    'CREATE INDEX ix_insumos_catalogo_zona_economica ON insumos_catalogo (zona_economica)',
    'CREATE UNIQUE INDEX ix_insumo_clave_fuente_zona ON insumos_catalogo (clave, fuente_id, zona_economica, tipo)',
    'CREATE INDEX ix_insumos_catalogo_tipo ON insumos_catalogo (tipo)',
    'CREATE INDEX ix_insumos_catalogo_creado_por_id ON insumos_catalogo (creado_por_id)',
    'CREATE INDEX ix_insumos_catalogo_estado ON insumos_catalogo (estado)',
    'CREATE INDEX ix_insumos_catalogo_fuente_id ON insumos_catalogo (fuente_id)',
    'CREATE TABLE programas_obra (\n\tidentificador VARCHAR(100) NOT NULL, \n\tnombre VARCHAR(500) NOT NULL, \n\tdescripcion TEXT, \n\tfecha_inicio_plan TIMESTAMP WITH TIME ZONE NOT NULL, \n\tfecha_fin_plan TIMESTAMP WITH TIME ZONE, \n\tfecha_inicio_real TIMESTAMP WITH TIME ZONE, \n\tfecha_fin_real TIMESTAMP WITH TIME ZONE, \n\tduracion_plan_dias INTEGER NOT NULL, \n\tduracion_real_dias INTEGER, \n\testado VARCHAR(50) NOT NULL, \n\tresultado_cpm JSONB, \n\tresultado_pert JSONB, \n\tresultado_evm JSONB, \n\texpediente_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_programas_obra_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_programas_obra_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE, \n\tCONSTRAINT uq_programa_expediente_identificador UNIQUE (expediente_id, identificador), \n\tCONSTRAINT fk_baseline_programas_obra_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX idx_programa_expediente ON programas_obra (expediente_id)',
    'CREATE INDEX ix_programas_obra_estado ON programas_obra (estado)',
    'CREATE INDEX ix_programas_obra_creado_por_id ON programas_obra (creado_por_id)',
    'CREATE TABLE levantamientos (\n\texpediente_id UUID NOT NULL, \n\tidentificador VARCHAR(100) NOT NULL, \n\tnombre VARCHAR(500) NOT NULL, \n\tdescripcion TEXT, \n\ttipo VARCHAR(20) NOT NULL, \n\testado VARCHAR(20) NOT NULL, \n\tcrs VARCHAR(50) NOT NULL, \n\tsrid INTEGER NOT NULL, \n\tmetadatos JSONB, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_levantamientos_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_levantamientos_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT uq_levantamiento_expediente_identificador UNIQUE (expediente_id, identificador), \n\tCONSTRAINT fk_baseline_levantamientos_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_levantamientos_estado ON levantamientos (estado)',
    'CREATE INDEX ix_levantamientos_expediente_id ON levantamientos (expediente_id)',
    'CREATE INDEX ix_levantamientos_creado_por_id ON levantamientos (creado_por_id)',
    'CREATE INDEX ix_levantamientos_tipo ON levantamientos (tipo)',
    'CREATE TABLE validaciones_expediente (\n\texpediente_id UUID NOT NULL, \n\ttipo VARCHAR(50) NOT NULL, \n\tnombre VARCHAR(255) NOT NULL, \n\tdescripcion TEXT, \n\testado VARCHAR(50) NOT NULL, \n\tresultados JSONB, \n\tobservaciones TEXT, \n\tejecutado_por_id UUID, \n\tfecha_ejecucion TIMESTAMP WITH TIME ZONE, \n\tscore INTEGER, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_validaciones_expediente_ejecutado_por_id FOREIGN KEY(ejecutado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_validaciones_expediente_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_validaciones_expediente_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_validaciones_expediente_tenant_id ON validaciones_expediente (tenant_id)',
    'CREATE INDEX ix_validacion_estado ON validaciones_expediente (estado)',
    'CREATE INDEX ix_validaciones_expediente_expediente_id ON validaciones_expediente (expediente_id)',
    'CREATE INDEX ix_validacion_expediente_tipo ON validaciones_expediente (expediente_id, tipo)',
    'CREATE INDEX ix_validaciones_expediente_tipo ON validaciones_expediente (tipo)',
    'CREATE TABLE juntas_aclaraciones (\n\tlicitacion_id UUID NOT NULL, \n\tfecha VARCHAR(10) NOT NULL, \n\tacta TEXT, \n\tpreguntas_respuestas JSONB, \n\tcambios_bases TEXT, \n\tnumero_junta INTEGER NOT NULL, \n\tfecha_limite_solicitudes VARCHAR(10), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_juntas_aclaraciones_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_juntas_aclaraciones_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_juntas_aclaraciones_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_juntas_aclaraciones_licitacion_id FOREIGN KEY(licitacion_id) REFERENCES licitaciones (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_juntas_aclaraciones_creado_por_id ON juntas_aclaraciones (creado_por_id)',
    'CREATE INDEX ix_juntas_aclaraciones_licitacion_id ON juntas_aclaraciones (licitacion_id)',
    'CREATE INDEX ix_juntas_aclaraciones_tenant_id ON juntas_aclaraciones (tenant_id)',
    'CREATE TABLE proposiciones (\n\tlicitacion_id UUID NOT NULL, \n\tproveedor_id UUID NOT NULL, \n\tmonto NUMERIC(18, 4) NOT NULL, \n\tplazo_dias INTEGER NOT NULL, \n\tsobres_digitales JSONB, \n\tfirma_valida BOOLEAN, \n\tintegridad_valida BOOLEAN, \n\tcumplimiento_documental BOOLEAN, \n\testado VARCHAR(50) NOT NULL, \n\tmotivo_desecho TEXT, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_proposiciones_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_proposiciones_proveedor_id FOREIGN KEY(proveedor_id) REFERENCES proveedores (id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_baseline_proposiciones_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_proposiciones_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_proposiciones_licitacion_id FOREIGN KEY(licitacion_id) REFERENCES licitaciones (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_proposiciones_licitacion_id ON proposiciones (licitacion_id)',
    'CREATE INDEX ix_proposiciones_tenant_id ON proposiciones (tenant_id)',
    'CREATE INDEX ix_proposiciones_creado_por_id ON proposiciones (creado_por_id)',
    'CREATE TABLE contratos (\n\texpediente_id UUID NOT NULL, \n\tlicitacion_id UUID, \n\tproveedor_id UUID NOT NULL, \n\tnumero_contrato VARCHAR(100) NOT NULL, \n\testado VARCHAR(50) NOT NULL, \n\tobjeto TEXT NOT NULL, \n\tmonto_total NUMERIC(18, 4) NOT NULL, \n\tmonto_original NUMERIC(18, 4), \n\tplazo_dias INTEGER NOT NULL, \n\tplazo_original INTEGER, \n\tfecha_firma VARCHAR(10), \n\tfecha_inicio VARCHAR(10), \n\tfecha_termino VARCHAR(10), \n\tfecha_termino_original VARCHAR(10), \n\tclausulas JSONB, \n\tobligaciones JSONB, \n\tanticipo_otorgado NUMERIC(18, 4) NOT NULL, \n\tavance_fisico NUMERIC(5, 2) NOT NULL, \n\tavance_financiero NUMERIC(5, 2) NOT NULL, \n\tfecha_finiquito VARCHAR(10), \n\tmonto_finiquito NUMERIC(18, 4), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_contratos_proveedor_id FOREIGN KEY(proveedor_id) REFERENCES proveedores (id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_baseline_contratos_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_contratos_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE, \n\tCONSTRAINT uq_contrato_expediente_numero UNIQUE (expediente_id, numero_contrato), \n\tCONSTRAINT fk_baseline_contratos_licitacion_id FOREIGN KEY(licitacion_id) REFERENCES licitaciones (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_contratos_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_contratos_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_contratos_numero_contrato ON contratos (numero_contrato)',
    'CREATE INDEX ix_contratos_estado ON contratos (estado)',
    'CREATE INDEX ix_contratos_tenant_id ON contratos (tenant_id)',
    'CREATE INDEX ix_contratos_expediente_id ON contratos (expediente_id)',
    'CREATE INDEX ix_contratos_creado_por_id ON contratos (creado_por_id)',
    'CREATE TABLE sanciones (\n\tproveedor_id UUID NOT NULL, \n\texpediente_id UUID, \n\tlicitacion_id UUID, \n\ttipo VARCHAR(50) NOT NULL, \n\tmotivo TEXT NOT NULL, \n\tmonto_multa NUMERIC(18, 4), \n\texpediente_sancionador VARCHAR(100), \n\thechos TEXT, \n\tpruebas JSONB, \n\taudiencia_fecha VARCHAR(10), \n\tresolucion TEXT, \n\tvigencia_inicio VARCHAR(10), \n\tvigencia_fin VARCHAR(10), \n\testado VARCHAR(50) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_sanciones_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_sanciones_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_sanciones_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_sanciones_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_sanciones_proveedor_id FOREIGN KEY(proveedor_id) REFERENCES proveedores (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_sanciones_licitacion_id FOREIGN KEY(licitacion_id) REFERENCES licitaciones (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_sanciones_tenant_id ON sanciones (tenant_id)',
    'CREATE INDEX ix_sanciones_proveedor_id ON sanciones (proveedor_id)',
    'CREATE INDEX ix_sanciones_creado_por_id ON sanciones (creado_por_id)',
    'CREATE TABLE analisis_clash (\n\tmodelo_id UUID NOT NULL, \n\ttolerancia_m NUMERIC(10, 6) NOT NULL, \n\testado VARCHAR(20) NOT NULL, \n\tnum_pares_evaluados INTEGER NOT NULL, \n\tnum_clashes_duros INTEGER NOT NULL, \n\tnum_clashes_blandos INTEGER NOT NULL, \n\ttiempo_calculo_ms INTEGER, \n\terror VARCHAR(2000), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_analisis_clash_modelo_id FOREIGN KEY(modelo_id) REFERENCES modelos_bim (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_analisis_clash_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_analisis_clash_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_analisis_clash_estado ON analisis_clash (estado)',
    'CREATE INDEX ix_analisis_clash_modelo_id ON analisis_clash (modelo_id)',
    'CREATE INDEX ix_analisis_clash_creado_por_id ON analisis_clash (creado_por_id)',
    'CREATE TABLE partidas (\n\tnumero INTEGER NOT NULL, \n\tdescripcion TEXT NOT NULL, \n\tunidad VARCHAR(20) NOT NULL, \n\tcantidad NUMERIC(18, 4) NOT NULL, \n\tprecio_unitario NUMERIC(18, 2) NOT NULL, \n\timporte NUMERIC(18, 2) NOT NULL, \n\telemento_tipo VARCHAR(100), \n\telemento_ifc_id VARCHAR(100), \n\tpresupuesto_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_partidas_presupuesto_id FOREIGN KEY(presupuesto_id) REFERENCES presupuestos (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_partidas_presupuesto_id ON partidas (presupuesto_id)',
    'CREATE TABLE precios_unitarios_asignados (\n\tconcepto_id UUID NOT NULL, \n\texpediente_id UUID, \n\tpresupuesto_id UUID, \n\tcantidad NUMERIC(18, 4) NOT NULL, \n\tprecio_asignado NUMERIC(18, 4) NOT NULL, \n\timporte NUMERIC(18, 4) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_precios_unitarios_asignados_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_precios_unitarios_asignados_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_precios_unitarios_asignados_concepto_id FOREIGN KEY(concepto_id) REFERENCES catalogos_apu (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_precios_unitarios_asignados_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_precios_unitarios_asignados_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_precios_unitarios_asignados_presupuesto_id FOREIGN KEY(presupuesto_id) REFERENCES presupuestos (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_precios_unitarios_asignados_tenant_id ON precios_unitarios_asignados (tenant_id)',
    'CREATE INDEX ix_precios_unitarios_asignados_creado_por_id ON precios_unitarios_asignados (creado_por_id)',
    'CREATE TABLE actividades_programa (\n\tidentificador VARCHAR(50) NOT NULL, \n\tnombre VARCHAR(500) NOT NULL, \n\tdescripcion TEXT, \n\twbs_codigo VARCHAR(50) NOT NULL, \n\twbs_nivel INTEGER NOT NULL, \n\tduracion NUMERIC(8, 2) NOT NULL, \n\tduracion_optimista NUMERIC(8, 2), \n\tduracion_probable NUMERIC(8, 2), \n\tduracion_pesimista NUMERIC(8, 2), \n\ttipo VARCHAR(50) NOT NULL, \n\tcosto_presupuestado NUMERIC(18, 2) NOT NULL, \n\tcosto_real NUMERIC(18, 2) NOT NULL, \n\tporcentaje_avance NUMERIC(5, 2) NOT NULL, \n\tinicio_temprano TIMESTAMP WITH TIME ZONE, \n\tfin_temprano TIMESTAMP WITH TIME ZONE, \n\tinicio_tardio TIMESTAMP WITH TIME ZONE, \n\tfin_tardio TIMESTAMP WITH TIME ZONE, \n\tholgura_total NUMERIC(8, 2) NOT NULL, \n\tholgura_libre NUMERIC(8, 2) NOT NULL, \n\ten_ruta_critica BOOLEAN NOT NULL, \n\tpredecesoras JSONB, \n\tdependencias_tipo JSONB, \n\tmetadatos JSONB, \n\tprograma_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_actividades_programa_programa_id FOREIGN KEY(programa_id) REFERENCES programas_obra (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_actividades_programa_programa_id ON actividades_programa (programa_id)',
    'CREATE TABLE puntos_topograficos (\n\tidentificador VARCHAR(50) NOT NULL, \n\tetiqueta VARCHAR(100), \n\tdescripcion TEXT, \n\tx NUMERIC(18, 6) NOT NULL, \n\ty NUMERIC(18, 6) NOT NULL, \n\tz NUMERIC(18, 6), \n\tprecision_xy NUMERIC(8, 4) NOT NULL, \n\tprecision_z NUMERIC(8, 4), \n\tgeom geometry(POINTZ,6362) NOT NULL, \n\tfuente VARCHAR(255), \n\tmetadatos JSONB, \n\tlevantamiento_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_puntos_topograficos_levantamiento_id FOREIGN KEY(levantamiento_id) REFERENCES levantamientos (id) ON DELETE CASCADE\n)',
    'CREATE INDEX idx_puntos_topograficos_geom ON puntos_topograficos USING gist (geom)',
    'CREATE INDEX idx_puntos_levantamiento ON puntos_topograficos (levantamiento_id)',
    'CREATE TABLE superficies_tin (\n\texpediente_id UUID NOT NULL, \n\tlevantamiento_id UUID NOT NULL, \n\tnombre VARCHAR(200) NOT NULL, \n\ttipo VARCHAR(20) NOT NULL, \n\tmalla_vertices JSON NOT NULL, \n\tmalla_caras JSON NOT NULL, \n\tarea_plan_m2 NUMERIC(18, 4) NOT NULL, \n\tarea_superficie_m2 NUMERIC(18, 4) NOT NULL, \n\televacion_min NUMERIC(10, 4) NOT NULL, \n\televacion_max NUMERIC(10, 4) NOT NULL, \n\televacion_media NUMERIC(10, 4) NOT NULL, \n\tpendiente_media_pct NUMERIC(8, 2) NOT NULL, \n\tnum_puntos INTEGER NOT NULL, \n\tnum_triangulos INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_superficies_tin_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_superficies_tin_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_superficies_tin_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_superficies_tin_levantamiento_id FOREIGN KEY(levantamiento_id) REFERENCES levantamientos (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_superficies_tin_creado_por_id ON superficies_tin (creado_por_id)',
    'CREATE INDEX ix_superficies_tin_levantamiento_id ON superficies_tin (levantamiento_id)',
    'CREATE INDEX ix_superficies_tin_expediente_id ON superficies_tin (expediente_id)',
    'CREATE TABLE documentos_cde (\n\texpediente_id UUID NOT NULL, \n\tnombre VARCHAR(500) NOT NULL, \n\tdescripcion TEXT, \n\tcontenido_url VARCHAR(1000), \n\tcontrato_id UUID, \n\ttipo VARCHAR(50) NOT NULL, \n\testado VARCHAR(50) NOT NULL, \n\tmime_type VARCHAR(100), \n\t"tamaño_bytes" INTEGER, \n\thash_sha256 VARCHAR(64), \n\truta_storage VARCHAR(1000), \n\truta_supabase VARCHAR(1000), \n\tversion INTEGER NOT NULL, \n\tdocumento_padre_id UUID, \n\tfirmado BOOLEAN NOT NULL, \n\tfirma_electronica_id VARCHAR(255), \n\tsello_tiempo VARCHAR(255), \n\ttexto_extraido TEXT, \n\tocr_completado BOOLEAN NOT NULL, \n\tocr_task_id VARCHAR(255), \n\tmetadatos JSONB, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_documentos_cde_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_documentos_cde_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_documentos_cde_documento_padre_id FOREIGN KEY(documento_padre_id) REFERENCES documentos_cde (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_documentos_cde_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_documentos_cde_contrato_id FOREIGN KEY(contrato_id) REFERENCES contratos (id) ON DELETE SET NULL, \n\tCONSTRAINT uq_documento_tenant_hash UNIQUE (tenant_id, hash_sha256), \n\tCONSTRAINT fk_baseline_documentos_cde_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_documentos_cde_expediente_id ON documentos_cde (expediente_id)',
    'CREATE INDEX ix_documentos_cde_estado ON documentos_cde (estado)',
    'CREATE INDEX ix_documentos_cde_tenant_id ON documentos_cde (tenant_id)',
    'CREATE INDEX ix_documentos_cde_creado_por_id ON documentos_cde (creado_por_id)',
    'CREATE INDEX ix_documentos_cde_contrato_id ON documentos_cde (contrato_id)',
    'CREATE INDEX ix_documentos_cde_hash_sha256 ON documentos_cde (hash_sha256)',
    'CREATE INDEX ix_documentos_cde_tipo ON documentos_cde (tipo)',
    'CREATE INDEX ix_documento_expediente_tipo ON documentos_cde (expediente_id, tipo, estado)',
    'CREATE TABLE evaluaciones_licitacion (\n\tlicitacion_id UUID NOT NULL, \n\tproposicion_id UUID NOT NULL, \n\ttipo VARCHAR(50) NOT NULL, \n\tresultado VARCHAR(50) NOT NULL, \n\tpuntaje NUMERIC(5, 2), \n\tdictamen TEXT, \n\tcriterios JSONB, \n\tevaluador_id UUID, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_evaluaciones_licitacion_licitacion_id FOREIGN KEY(licitacion_id) REFERENCES licitaciones (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_evaluaciones_licitacion_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_evaluaciones_licitacion_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_evaluaciones_licitacion_proposicion_id FOREIGN KEY(proposicion_id) REFERENCES proposiciones (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_evaluaciones_licitacion_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_evaluaciones_licitacion_evaluador_id FOREIGN KEY(evaluador_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_evaluaciones_licitacion_tenant_id ON evaluaciones_licitacion (tenant_id)',
    'CREATE INDEX ix_evaluaciones_licitacion_licitacion_id ON evaluaciones_licitacion (licitacion_id)',
    'CREATE INDEX ix_evaluaciones_licitacion_creado_por_id ON evaluaciones_licitacion (creado_por_id)',
    'CREATE TABLE convenios_modificatorios (\n\tcontrato_id UUID NOT NULL, \n\tnumero VARCHAR(50) NOT NULL, \n\ttipo VARCHAR(50) NOT NULL, \n\tdescripcion TEXT, \n\tmonto_anterior NUMERIC(18, 4), \n\tmonto_nuevo NUMERIC(18, 4), \n\tplazo_anterior INTEGER, \n\tplazo_nuevo INTEGER, \n\tjustificacion TEXT, \n\taprobado_por UUID, \n\tfecha_aprobacion VARCHAR(10), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_convenios_modificatorios_contrato_id FOREIGN KEY(contrato_id) REFERENCES contratos (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_convenios_modificatorios_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_convenios_modificatorios_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_convenios_modificatorios_aprobado_por FOREIGN KEY(aprobado_por) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_convenios_modificatorios_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_convenios_modificatorios_contrato_id ON convenios_modificatorios (contrato_id)',
    'CREATE INDEX ix_convenios_modificatorios_creado_por_id ON convenios_modificatorios (creado_por_id)',
    'CREATE INDEX ix_convenios_modificatorios_tenant_id ON convenios_modificatorios (tenant_id)',
    'CREATE TABLE garantias_contrato (\n\tcontrato_id UUID NOT NULL, \n\ttipo VARCHAR(50) NOT NULL, \n\tmonto NUMERIC(18, 4) NOT NULL, \n\tinstitucion VARCHAR(200), \n\tnumero_poliza VARCHAR(100), \n\tvigencia_inicio VARCHAR(10), \n\tvigencia_fin VARCHAR(10), \n\tactiva BOOLEAN NOT NULL, \n\tliberada BOOLEAN NOT NULL, \n\tejecutada BOOLEAN NOT NULL, \n\tfecha_liberacion VARCHAR(10), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_garantias_contrato_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_garantias_contrato_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_garantias_contrato_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_garantias_contrato_contrato_id FOREIGN KEY(contrato_id) REFERENCES contratos (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_garantias_contrato_creado_por_id ON garantias_contrato (creado_por_id)',
    'CREATE INDEX ix_garantias_contrato_contrato_id ON garantias_contrato (contrato_id)',
    'CREATE INDEX ix_garantias_contrato_tenant_id ON garantias_contrato (tenant_id)',
    'CREATE TABLE entregables_contrato (\n\tcontrato_id UUID NOT NULL, \n\tnumero_estimacion INTEGER NOT NULL, \n\tperiodo_inicio VARCHAR(10), \n\tperiodo_fin VARCHAR(10), \n\tmonto_ejecutado NUMERIC(18, 4) NOT NULL, \n\tavance_fisico NUMERIC(5, 2) NOT NULL, \n\tavance_financiero NUMERIC(5, 2) NOT NULL, \n\taprobado BOOLEAN NOT NULL, \n\tfecha_aprobacion VARCHAR(10), \n\taprobado_por UUID, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_entregables_contrato_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_entregables_contrato_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_entregables_contrato_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_entregables_contrato_contrato_id FOREIGN KEY(contrato_id) REFERENCES contratos (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_entregables_contrato_aprobado_por FOREIGN KEY(aprobado_por) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_entregables_contrato_creado_por_id ON entregables_contrato (creado_por_id)',
    'CREATE INDEX ix_entregables_contrato_contrato_id ON entregables_contrato (contrato_id)',
    'CREATE INDEX ix_entregables_contrato_tenant_id ON entregables_contrato (tenant_id)',
    'CREATE TABLE penalizaciones_contrato (\n\tcontrato_id UUID NOT NULL, \n\ttipo VARCHAR(50) NOT NULL, \n\tmonto NUMERIC(18, 4) NOT NULL, \n\tdias_atraso INTEGER, \n\tdescripcion TEXT NOT NULL, \n\ttope_legal NUMERIC(18, 4) NOT NULL, \n\tdentro_tope BOOLEAN NOT NULL, \n\taplicada BOOLEAN NOT NULL, \n\tfecha_aplicacion VARCHAR(10), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_penalizaciones_contrato_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_penalizaciones_contrato_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_penalizaciones_contrato_contrato_id FOREIGN KEY(contrato_id) REFERENCES contratos (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_penalizaciones_contrato_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_penalizaciones_contrato_contrato_id ON penalizaciones_contrato (contrato_id)',
    'CREATE INDEX ix_penalizaciones_contrato_tenant_id ON penalizaciones_contrato (tenant_id)',
    'CREATE INDEX ix_penalizaciones_contrato_creado_por_id ON penalizaciones_contrato (creado_por_id)',
    'CREATE TABLE inconformidades (\n\texpediente_id UUID NOT NULL, \n\tlicitacion_id UUID, \n\tcontrato_id UUID, \n\ttitulo VARCHAR(500) NOT NULL, \n\tdescripcion TEXT NOT NULL, \n\testado VARCHAR(50) NOT NULL, \n\tevidencia JSONB, \n\trespuesta TEXT, \n\tresolucion TEXT, \n\tdictamen TEXT, \n\tfecha_dictamen VARCHAR(10), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_inconformidades_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_inconformidades_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_inconformidades_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_inconformidades_licitacion_id FOREIGN KEY(licitacion_id) REFERENCES licitaciones (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_inconformidades_contrato_id FOREIGN KEY(contrato_id) REFERENCES contratos (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_inconformidades_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_inconformidades_expediente_id ON inconformidades (expediente_id)',
    'CREATE INDEX ix_inconformidades_creado_por_id ON inconformidades (creado_por_id)',
    'CREATE INDEX ix_inconformidades_estado ON inconformidades (estado)',
    'CREATE INDEX ix_inconformidades_tenant_id ON inconformidades (tenant_id)',
    'CREATE TABLE evaluaciones_compliance (\n\tlicitacion_id UUID, \n\tcontrato_id UUID, \n\tregla_id UUID NOT NULL, \n\testado VARCHAR(50) NOT NULL, \n\tobservaciones TEXT, \n\tevidencia JSONB, \n\tevaluador_id UUID, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_evaluaciones_compliance_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_evaluaciones_compliance_evaluador_id FOREIGN KEY(evaluador_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_evaluaciones_compliance_regla_id FOREIGN KEY(regla_id) REFERENCES reglas_cumplimiento (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_evaluaciones_compliance_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_evaluaciones_compliance_contrato_id FOREIGN KEY(contrato_id) REFERENCES contratos (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_evaluaciones_compliance_licitacion_id FOREIGN KEY(licitacion_id) REFERENCES licitaciones (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_evaluaciones_compliance_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_evaluaciones_compliance_tenant_id ON evaluaciones_compliance (tenant_id)',
    'CREATE INDEX ix_evaluaciones_compliance_creado_por_id ON evaluaciones_compliance (creado_por_id)',
    'CREATE TABLE elementos_bim (\n\tmodelo_id UUID NOT NULL, \n\tglobal_id VARCHAR(100) NOT NULL, \n\texpress_id INTEGER NOT NULL, \n\ttipo VARCHAR(100) NOT NULL, \n\tnombre VARCHAR(500), \n\tvolumen NUMERIC(18, 6), \n\tarea NUMERIC(18, 6), \n\tlongitud NUMERIC(18, 6), \n\tunidad VARCHAR(20) NOT NULL, \n\tfuente_volumen VARCHAR(30) NOT NULL, \n\tfuente_area VARCHAR(30) NOT NULL, \n\tsistema_constructivo VARCHAR(100), \n\tnivel VARCHAR(200), \n\tbbox JSON, \n\tpropiedades JSON, \n\tmalla_vertices JSON, \n\tmalla_caras JSON, \n\tpartida_id UUID, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_elementos_bim_modelo_id FOREIGN KEY(modelo_id) REFERENCES modelos_bim (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_elementos_bim_partida_id FOREIGN KEY(partida_id) REFERENCES partidas (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_elementos_bim_global_id ON elementos_bim (global_id)',
    'CREATE INDEX ix_elementos_bim_partida_id ON elementos_bim (partida_id)',
    'CREATE INDEX ix_elementos_bim_tipo ON elementos_bim (tipo)',
    'CREATE INDEX ix_elementos_bim_nivel ON elementos_bim (nivel)',
    'CREATE INDEX ix_elementos_bim_modelo_id ON elementos_bim (modelo_id)',
    'CREATE TABLE conceptos (\n\tclave VARCHAR(50) NOT NULL, \n\tdescripcion TEXT NOT NULL, \n\tunidad VARCHAR(20) NOT NULL, \n\tcantidad NUMERIC(18, 4) NOT NULL, \n\tcosto_directo_unitario NUMERIC(18, 2) NOT NULL, \n\tpartida_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_conceptos_partida_id FOREIGN KEY(partida_id) REFERENCES partidas (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_conceptos_partida_id ON conceptos (partida_id)',
    'CREATE TABLE calculos_volumen (\n\texpediente_id UUID NOT NULL, \n\tsuperficie_existente_id UUID NOT NULL, \n\tsuperficie_proyecto_id UUID, \n\televacion_referencia NUMERIC(10, 4), \n\tvolumen_corte_m3 NUMERIC(18, 3) NOT NULL, \n\tvolumen_terraplen_m3 NUMERIC(18, 3) NOT NULL, \n\tvolumen_neto_m3 NUMERIC(18, 3) NOT NULL, \n\tarea_analizada_m2 NUMERIC(18, 3) NOT NULL, \n\tpartida_id UUID, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_calculos_volumen_superficie_proyecto_id FOREIGN KEY(superficie_proyecto_id) REFERENCES superficies_tin (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_calculos_volumen_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_calculos_volumen_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_calculos_volumen_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_calculos_volumen_partida_id FOREIGN KEY(partida_id) REFERENCES partidas (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_calculos_volumen_superficie_existente_id FOREIGN KEY(superficie_existente_id) REFERENCES superficies_tin (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_calculos_volumen_creado_por_id ON calculos_volumen (creado_por_id)',
    'CREATE INDEX ix_calculos_volumen_expediente_id ON calculos_volumen (expediente_id)',
    'CREATE INDEX ix_calculos_volumen_partida_id ON calculos_volumen (partida_id)',
    'CREATE TABLE validaciones_propuesta (\n\texpediente_id UUID NOT NULL, \n\tproposicion_id UUID, \n\trfc_empresa VARCHAR(13), \n\testado VARCHAR(30) NOT NULL, \n\tbitacora_evaluacion JSONB NOT NULL, \n\tdatos_entrada JSONB, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreado_por_id UUID, \n\tactualizado_por_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_validaciones_propuesta_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_validaciones_propuesta_proposicion_id FOREIGN KEY(proposicion_id) REFERENCES proposiciones (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_validaciones_propuesta_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_validaciones_propuesta_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_baseline_validaciones_propuesta_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_validaciones_propuesta_expediente_id ON validaciones_propuesta (expediente_id)',
    'CREATE INDEX ix_validaciones_propuesta_tenant_id ON validaciones_propuesta (tenant_id)',
    'CREATE INDEX ix_validaciones_propuesta_estado ON validaciones_propuesta (estado)',
    'CREATE INDEX ix_validacion_propuesta_expediente ON validaciones_propuesta (expediente_id, estado)',
    'CREATE INDEX ix_validaciones_propuesta_proposicion_id ON validaciones_propuesta (proposicion_id)',
    'CREATE INDEX ix_validacion_propuesta_proposicion ON validaciones_propuesta (proposicion_id)',
    'CREATE INDEX ix_validaciones_propuesta_creado_por_id ON validaciones_propuesta (creado_por_id)',
    'CREATE INDEX ix_validaciones_propuesta_rfc_empresa ON validaciones_propuesta (rfc_empresa)',
    'CREATE TABLE clash_resultados (\n\tanalisis_id UUID NOT NULL, \n\tmodelo_id UUID NOT NULL, \n\telemento_a_id UUID NOT NULL, \n\telemento_b_id UUID NOT NULL, \n\ttipo_a VARCHAR(100) NOT NULL, \n\ttipo_b VARCHAR(100) NOT NULL, \n\tseveridad VARCHAR(10) NOT NULL, \n\tdistancia_m NUMERIC(10, 6) NOT NULL, \n\tvolumen_aproximado_m3 NUMERIC(18, 6), \n\tpunto_cercano_a JSON NOT NULL, \n\tpunto_cercano_b JSON NOT NULL, \n\ttriangulos_a JSON, \n\ttriangulos_b JSON, \n\testado VARCHAR(20) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_clash_resultados_modelo_id FOREIGN KEY(modelo_id) REFERENCES modelos_bim (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_clash_resultados_elemento_b_id FOREIGN KEY(elemento_b_id) REFERENCES elementos_bim (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_clash_resultados_elemento_a_id FOREIGN KEY(elemento_a_id) REFERENCES elementos_bim (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_baseline_clash_resultados_analisis_id FOREIGN KEY(analisis_id) REFERENCES analisis_clash (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_clash_resultados_analisis_id ON clash_resultados (analisis_id)',
    'CREATE INDEX ix_clash_resultados_modelo_id ON clash_resultados (modelo_id)',
    'CREATE INDEX ix_clash_resultados_estado ON clash_resultados (estado)',
    'CREATE INDEX ix_clash_resultados_elemento_a_id ON clash_resultados (elemento_a_id)',
    'CREATE INDEX ix_clash_resultados_severidad ON clash_resultados (severidad)',
    'CREATE INDEX ix_clash_resultados_elemento_b_id ON clash_resultados (elemento_b_id)',
    'CREATE TABLE insumos (\n\tclave VARCHAR(50) NOT NULL, \n\tdescripcion TEXT NOT NULL, \n\ttipo VARCHAR(50) NOT NULL, \n\tunidad VARCHAR(20) NOT NULL, \n\tcantidad NUMERIC(18, 4) NOT NULL, \n\tprecio_unitario NUMERIC(18, 2) NOT NULL, \n\timporte NUMERIC(18, 2) NOT NULL, \n\tfuente_catalogo VARCHAR(100), \n\trendimiento NUMERIC(8, 4) NOT NULL, \n\tconcepto_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_baseline_insumos_concepto_id FOREIGN KEY(concepto_id) REFERENCES conceptos (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_insumos_concepto_id ON insumos (concepto_id)',
    'ALTER TABLE workflow_pasos ADD CONSTRAINT fk_baseline_workflow_pasos_responsable_id FOREIGN KEY(responsable_id) REFERENCES users (id) ON DELETE SET NULL',
    'ALTER TABLE workflows ADD CONSTRAINT fk_baseline_workflows_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL',
    'ALTER TABLE workflows ADD CONSTRAINT fk_baseline_workflows_paso_actual_id FOREIGN KEY(paso_actual_id) REFERENCES workflow_pasos (id) ON DELETE SET NULL',
    'ALTER TABLE workflows ADD CONSTRAINT fk_baseline_workflows_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE',
    'ALTER TABLE workflows ADD CONSTRAINT fk_baseline_workflows_expediente_id FOREIGN KEY(expediente_id) REFERENCES expedientes_obra (id) ON DELETE CASCADE',
    'ALTER TABLE workflow_pasos ADD CONSTRAINT fk_baseline_workflow_pasos_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL',
    'ALTER TABLE workflow_pasos ADD CONSTRAINT fk_baseline_workflow_pasos_workflow_id FOREIGN KEY(workflow_id) REFERENCES workflows (id) ON DELETE CASCADE',
    'ALTER TABLE workflow_pasos ADD CONSTRAINT fk_baseline_workflow_pasos_actualizado_por_id FOREIGN KEY(actualizado_por_id) REFERENCES users (id) ON DELETE SET NULL',
    'ALTER TABLE workflows ADD CONSTRAINT fk_baseline_workflows_creado_por_id FOREIGN KEY(creado_por_id) REFERENCES users (id) ON DELETE SET NULL',
    'ALTER TABLE workflow_pasos ADD CONSTRAINT fk_baseline_workflow_pasos_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE',
)

def upgrade():
    for statement in DDL:
        op.execute(statement)

def downgrade():
    op.drop_constraint('fk_baseline_users_tenant_id', 'users', type_="foreignkey")
    op.drop_constraint('fk_baseline_invitations_invited_by', 'invitations', type_="foreignkey")
    op.drop_constraint('fk_baseline_invitations_tenant_id', 'invitations', type_="foreignkey")
    op.drop_constraint('fk_baseline_entidades_actualizado_por_id', 'entidades', type_="foreignkey")
    op.drop_constraint('fk_baseline_entidades_creado_por_id', 'entidades', type_="foreignkey")
    op.drop_constraint('fk_baseline_unidades_administrativas_actualizado_por_id', 'unidades_administrativas', type_="foreignkey")
    op.drop_constraint('fk_baseline_unidades_administrativas_creado_por_id', 'unidades_administrativas', type_="foreignkey")
    op.drop_constraint('fk_baseline_unidades_administrativas_entidad_id', 'unidades_administrativas', type_="foreignkey")
    op.drop_constraint('fk_baseline_audit_ledger_tenant_id', 'audit_ledger', type_="foreignkey")
    op.drop_constraint('fk_baseline_audit_ledger_user_id', 'audit_ledger', type_="foreignkey")
    op.drop_constraint('fk_baseline_reglas_negocio_creado_por_id', 'reglas_negocio', type_="foreignkey")
    op.drop_constraint('fk_baseline_reglas_negocio_tenant_id', 'reglas_negocio', type_="foreignkey")
    op.drop_constraint('fk_baseline_ejecucion_reglas_expediente_id', 'ejecucion_reglas', type_="foreignkey")
    op.drop_constraint('fk_baseline_ejecucion_reglas_regla_id', 'ejecucion_reglas', type_="foreignkey")
    op.drop_constraint('fk_baseline_ejecucion_reglas_tenant_id', 'ejecucion_reglas', type_="foreignkey")
    op.drop_constraint('fk_baseline_transiciones_workflow_actualizado_por_id', 'transiciones_workflow', type_="foreignkey")
    op.drop_constraint('fk_baseline_transiciones_workflow_creado_por_id', 'transiciones_workflow', type_="foreignkey")
    op.drop_constraint('fk_baseline_transiciones_workflow_tenant_id', 'transiciones_workflow', type_="foreignkey")
    op.drop_constraint('fk_baseline_tareas_workflow_actualizado_por_id', 'tareas_workflow', type_="foreignkey")
    op.drop_constraint('fk_baseline_tareas_workflow_asignado_a_id', 'tareas_workflow', type_="foreignkey")
    op.drop_constraint('fk_baseline_tareas_workflow_creado_por_id', 'tareas_workflow', type_="foreignkey")
    op.drop_constraint('fk_baseline_tareas_workflow_expediente_id', 'tareas_workflow', type_="foreignkey")
    op.drop_constraint('fk_baseline_tareas_workflow_tenant_id', 'tareas_workflow', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflows_actualizado_por_id', 'workflows', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflows_creado_por_id', 'workflows', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflows_expediente_id', 'workflows', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflows_paso_actual_id', 'workflows', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflows_tenant_id', 'workflows', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflow_pasos_actualizado_por_id', 'workflow_pasos', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflow_pasos_creado_por_id', 'workflow_pasos', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflow_pasos_responsable_id', 'workflow_pasos', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflow_pasos_tenant_id', 'workflow_pasos', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflow_pasos_workflow_id', 'workflow_pasos', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflow_transiciones_actualizado_por_id', 'workflow_transiciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflow_transiciones_creado_por_id', 'workflow_transiciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflow_transiciones_paso_destino_id', 'workflow_transiciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflow_transiciones_paso_origen_id', 'workflow_transiciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflow_transiciones_tenant_id', 'workflow_transiciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflow_transiciones_workflow_id', 'workflow_transiciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflow_condiciones_tenant_id', 'workflow_condiciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_workflow_condiciones_transicion_id', 'workflow_condiciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_proveedores_actualizado_por_id', 'proveedores', type_="foreignkey")
    op.drop_constraint('fk_baseline_proveedores_creado_por_id', 'proveedores', type_="foreignkey")
    op.drop_constraint('fk_baseline_proveedores_tenant_id', 'proveedores', type_="foreignkey")
    op.drop_constraint('fk_baseline_representantes_legales_actualizado_por_id', 'representantes_legales', type_="foreignkey")
    op.drop_constraint('fk_baseline_representantes_legales_creado_por_id', 'representantes_legales', type_="foreignkey")
    op.drop_constraint('fk_baseline_representantes_legales_proveedor_id', 'representantes_legales', type_="foreignkey")
    op.drop_constraint('fk_baseline_representantes_legales_tenant_id', 'representantes_legales', type_="foreignkey")
    op.drop_constraint('fk_baseline_catalogo_procedimientos_tenant_id', 'catalogo_procedimientos', type_="foreignkey")
    op.drop_constraint('fk_baseline_catalogo_juridico_tenant_id', 'catalogo_juridico', type_="foreignkey")
    op.drop_constraint('fk_baseline_reglas_cumplimiento_catalogo_catalogo_juridico_id', 'reglas_cumplimiento_catalogo', type_="foreignkey")
    op.drop_constraint('fk_baseline_reglas_cumplimiento_catalogo_tenant_id', 'reglas_cumplimiento_catalogo', type_="foreignkey")
    op.drop_constraint('fk_baseline_expedientes_obra_actualizado_por_id', 'expedientes_obra', type_="foreignkey")
    op.drop_constraint('fk_baseline_expedientes_obra_creado_por_id', 'expedientes_obra', type_="foreignkey")
    op.drop_constraint('fk_baseline_expedientes_obra_responsable_id', 'expedientes_obra', type_="foreignkey")
    op.drop_constraint('fk_baseline_expedientes_obra_tenant_id', 'expedientes_obra', type_="foreignkey")
    op.drop_constraint('fk_baseline_documentos_actualizado_por_id', 'documentos', type_="foreignkey")
    op.drop_constraint('fk_baseline_documentos_creado_por_id', 'documentos', type_="foreignkey")
    op.drop_constraint('fk_baseline_documentos_expediente_id', 'documentos', type_="foreignkey")
    op.drop_constraint('fk_baseline_planeacion_expediente_aprobado_por_id', 'planeacion_expediente', type_="foreignkey")
    op.drop_constraint('fk_baseline_planeacion_expediente_expediente_id', 'planeacion_expediente', type_="foreignkey")
    op.drop_constraint('fk_baseline_planeacion_expediente_tenant_id', 'planeacion_expediente', type_="foreignkey")
    op.drop_constraint('fk_baseline_documentos_cde_actualizado_por_id', 'documentos_cde', type_="foreignkey")
    op.drop_constraint('fk_baseline_documentos_cde_contrato_id', 'documentos_cde', type_="foreignkey")
    op.drop_constraint('fk_baseline_documentos_cde_creado_por_id', 'documentos_cde', type_="foreignkey")
    op.drop_constraint('fk_baseline_documentos_cde_documento_padre_id', 'documentos_cde', type_="foreignkey")
    op.drop_constraint('fk_baseline_documentos_cde_expediente_id', 'documentos_cde', type_="foreignkey")
    op.drop_constraint('fk_baseline_documentos_cde_tenant_id', 'documentos_cde', type_="foreignkey")
    op.drop_constraint('fk_baseline_licitaciones_actualizado_por_id', 'licitaciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_licitaciones_creado_por_id', 'licitaciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_licitaciones_expediente_id', 'licitaciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_licitaciones_tenant_id', 'licitaciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_juntas_aclaraciones_actualizado_por_id', 'juntas_aclaraciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_juntas_aclaraciones_creado_por_id', 'juntas_aclaraciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_juntas_aclaraciones_licitacion_id', 'juntas_aclaraciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_juntas_aclaraciones_tenant_id', 'juntas_aclaraciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_proposiciones_actualizado_por_id', 'proposiciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_proposiciones_creado_por_id', 'proposiciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_proposiciones_licitacion_id', 'proposiciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_proposiciones_proveedor_id', 'proposiciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_proposiciones_tenant_id', 'proposiciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_evaluaciones_licitacion_actualizado_por_id', 'evaluaciones_licitacion', type_="foreignkey")
    op.drop_constraint('fk_baseline_evaluaciones_licitacion_creado_por_id', 'evaluaciones_licitacion', type_="foreignkey")
    op.drop_constraint('fk_baseline_evaluaciones_licitacion_evaluador_id', 'evaluaciones_licitacion', type_="foreignkey")
    op.drop_constraint('fk_baseline_evaluaciones_licitacion_licitacion_id', 'evaluaciones_licitacion', type_="foreignkey")
    op.drop_constraint('fk_baseline_evaluaciones_licitacion_proposicion_id', 'evaluaciones_licitacion', type_="foreignkey")
    op.drop_constraint('fk_baseline_evaluaciones_licitacion_tenant_id', 'evaluaciones_licitacion', type_="foreignkey")
    op.drop_constraint('fk_baseline_contratos_actualizado_por_id', 'contratos', type_="foreignkey")
    op.drop_constraint('fk_baseline_contratos_creado_por_id', 'contratos', type_="foreignkey")
    op.drop_constraint('fk_baseline_contratos_expediente_id', 'contratos', type_="foreignkey")
    op.drop_constraint('fk_baseline_contratos_licitacion_id', 'contratos', type_="foreignkey")
    op.drop_constraint('fk_baseline_contratos_proveedor_id', 'contratos', type_="foreignkey")
    op.drop_constraint('fk_baseline_contratos_tenant_id', 'contratos', type_="foreignkey")
    op.drop_constraint('fk_baseline_convenios_modificatorios_actualizado_por_id', 'convenios_modificatorios', type_="foreignkey")
    op.drop_constraint('fk_baseline_convenios_modificatorios_aprobado_por', 'convenios_modificatorios', type_="foreignkey")
    op.drop_constraint('fk_baseline_convenios_modificatorios_contrato_id', 'convenios_modificatorios', type_="foreignkey")
    op.drop_constraint('fk_baseline_convenios_modificatorios_creado_por_id', 'convenios_modificatorios', type_="foreignkey")
    op.drop_constraint('fk_baseline_convenios_modificatorios_tenant_id', 'convenios_modificatorios', type_="foreignkey")
    op.drop_constraint('fk_baseline_garantias_contrato_actualizado_por_id', 'garantias_contrato', type_="foreignkey")
    op.drop_constraint('fk_baseline_garantias_contrato_contrato_id', 'garantias_contrato', type_="foreignkey")
    op.drop_constraint('fk_baseline_garantias_contrato_creado_por_id', 'garantias_contrato', type_="foreignkey")
    op.drop_constraint('fk_baseline_garantias_contrato_tenant_id', 'garantias_contrato', type_="foreignkey")
    op.drop_constraint('fk_baseline_entregables_contrato_actualizado_por_id', 'entregables_contrato', type_="foreignkey")
    op.drop_constraint('fk_baseline_entregables_contrato_aprobado_por', 'entregables_contrato', type_="foreignkey")
    op.drop_constraint('fk_baseline_entregables_contrato_contrato_id', 'entregables_contrato', type_="foreignkey")
    op.drop_constraint('fk_baseline_entregables_contrato_creado_por_id', 'entregables_contrato', type_="foreignkey")
    op.drop_constraint('fk_baseline_entregables_contrato_tenant_id', 'entregables_contrato', type_="foreignkey")
    op.drop_constraint('fk_baseline_penalizaciones_contrato_actualizado_por_id', 'penalizaciones_contrato', type_="foreignkey")
    op.drop_constraint('fk_baseline_penalizaciones_contrato_contrato_id', 'penalizaciones_contrato', type_="foreignkey")
    op.drop_constraint('fk_baseline_penalizaciones_contrato_creado_por_id', 'penalizaciones_contrato', type_="foreignkey")
    op.drop_constraint('fk_baseline_penalizaciones_contrato_tenant_id', 'penalizaciones_contrato', type_="foreignkey")
    op.drop_constraint('fk_baseline_reglas_cumplimiento_actualizado_por_id', 'reglas_cumplimiento', type_="foreignkey")
    op.drop_constraint('fk_baseline_reglas_cumplimiento_creado_por_id', 'reglas_cumplimiento', type_="foreignkey")
    op.drop_constraint('fk_baseline_reglas_cumplimiento_tenant_id', 'reglas_cumplimiento', type_="foreignkey")
    op.drop_constraint('fk_baseline_inconformidades_actualizado_por_id', 'inconformidades', type_="foreignkey")
    op.drop_constraint('fk_baseline_inconformidades_contrato_id', 'inconformidades', type_="foreignkey")
    op.drop_constraint('fk_baseline_inconformidades_creado_por_id', 'inconformidades', type_="foreignkey")
    op.drop_constraint('fk_baseline_inconformidades_expediente_id', 'inconformidades', type_="foreignkey")
    op.drop_constraint('fk_baseline_inconformidades_licitacion_id', 'inconformidades', type_="foreignkey")
    op.drop_constraint('fk_baseline_inconformidades_tenant_id', 'inconformidades', type_="foreignkey")
    op.drop_constraint('fk_baseline_sanciones_actualizado_por_id', 'sanciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_sanciones_creado_por_id', 'sanciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_sanciones_expediente_id', 'sanciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_sanciones_licitacion_id', 'sanciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_sanciones_proveedor_id', 'sanciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_sanciones_tenant_id', 'sanciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_evaluaciones_compliance_actualizado_por_id', 'evaluaciones_compliance', type_="foreignkey")
    op.drop_constraint('fk_baseline_evaluaciones_compliance_contrato_id', 'evaluaciones_compliance', type_="foreignkey")
    op.drop_constraint('fk_baseline_evaluaciones_compliance_creado_por_id', 'evaluaciones_compliance', type_="foreignkey")
    op.drop_constraint('fk_baseline_evaluaciones_compliance_evaluador_id', 'evaluaciones_compliance', type_="foreignkey")
    op.drop_constraint('fk_baseline_evaluaciones_compliance_licitacion_id', 'evaluaciones_compliance', type_="foreignkey")
    op.drop_constraint('fk_baseline_evaluaciones_compliance_regla_id', 'evaluaciones_compliance', type_="foreignkey")
    op.drop_constraint('fk_baseline_evaluaciones_compliance_tenant_id', 'evaluaciones_compliance', type_="foreignkey")
    op.drop_constraint('fk_baseline_modelos_bim_actualizado_por_id', 'modelos_bim', type_="foreignkey")
    op.drop_constraint('fk_baseline_modelos_bim_creado_por_id', 'modelos_bim', type_="foreignkey")
    op.drop_constraint('fk_baseline_modelos_bim_expediente_id', 'modelos_bim', type_="foreignkey")
    op.drop_constraint('fk_baseline_elementos_bim_modelo_id', 'elementos_bim', type_="foreignkey")
    op.drop_constraint('fk_baseline_elementos_bim_partida_id', 'elementos_bim', type_="foreignkey")
    op.drop_constraint('fk_baseline_analisis_clash_actualizado_por_id', 'analisis_clash', type_="foreignkey")
    op.drop_constraint('fk_baseline_analisis_clash_creado_por_id', 'analisis_clash', type_="foreignkey")
    op.drop_constraint('fk_baseline_analisis_clash_modelo_id', 'analisis_clash', type_="foreignkey")
    op.drop_constraint('fk_baseline_clash_resultados_analisis_id', 'clash_resultados', type_="foreignkey")
    op.drop_constraint('fk_baseline_clash_resultados_elemento_a_id', 'clash_resultados', type_="foreignkey")
    op.drop_constraint('fk_baseline_clash_resultados_elemento_b_id', 'clash_resultados', type_="foreignkey")
    op.drop_constraint('fk_baseline_clash_resultados_modelo_id', 'clash_resultados', type_="foreignkey")
    op.drop_constraint('fk_baseline_presupuestos_actualizado_por_id', 'presupuestos', type_="foreignkey")
    op.drop_constraint('fk_baseline_presupuestos_creado_por_id', 'presupuestos', type_="foreignkey")
    op.drop_constraint('fk_baseline_presupuestos_expediente_id', 'presupuestos', type_="foreignkey")
    op.drop_constraint('fk_baseline_partidas_presupuesto_id', 'partidas', type_="foreignkey")
    op.drop_constraint('fk_baseline_conceptos_partida_id', 'conceptos', type_="foreignkey")
    op.drop_constraint('fk_baseline_insumos_concepto_id', 'insumos', type_="foreignkey")
    op.drop_constraint('fk_baseline_catalogos_apu_actualizado_por_id', 'catalogos_apu', type_="foreignkey")
    op.drop_constraint('fk_baseline_catalogos_apu_creado_por_id', 'catalogos_apu', type_="foreignkey")
    op.drop_constraint('fk_baseline_catalogos_apu_tenant_id', 'catalogos_apu', type_="foreignkey")
    op.drop_constraint('fk_baseline_precios_unitarios_asignados_actualizado_por_id', 'precios_unitarios_asignados', type_="foreignkey")
    op.drop_constraint('fk_baseline_precios_unitarios_asignados_concepto_id', 'precios_unitarios_asignados', type_="foreignkey")
    op.drop_constraint('fk_baseline_precios_unitarios_asignados_creado_por_id', 'precios_unitarios_asignados', type_="foreignkey")
    op.drop_constraint('fk_baseline_precios_unitarios_asignados_expediente_id', 'precios_unitarios_asignados', type_="foreignkey")
    op.drop_constraint('fk_baseline_precios_unitarios_asignados_presupuesto_id', 'precios_unitarios_asignados', type_="foreignkey")
    op.drop_constraint('fk_baseline_precios_unitarios_asignados_tenant_id', 'precios_unitarios_asignados', type_="foreignkey")
    op.drop_constraint('fk_baseline_catalogo_fuentes_actualizado_por_id', 'catalogo_fuentes', type_="foreignkey")
    op.drop_constraint('fk_baseline_catalogo_fuentes_creado_por_id', 'catalogo_fuentes', type_="foreignkey")
    op.drop_constraint('fk_baseline_conceptos_catalogo_actualizado_por_id', 'conceptos_catalogo', type_="foreignkey")
    op.drop_constraint('fk_baseline_conceptos_catalogo_creado_por_id', 'conceptos_catalogo', type_="foreignkey")
    op.drop_constraint('fk_baseline_conceptos_catalogo_fuente_id', 'conceptos_catalogo', type_="foreignkey")
    op.drop_constraint('fk_baseline_insumos_catalogo_actualizado_por_id', 'insumos_catalogo', type_="foreignkey")
    op.drop_constraint('fk_baseline_insumos_catalogo_creado_por_id', 'insumos_catalogo', type_="foreignkey")
    op.drop_constraint('fk_baseline_insumos_catalogo_fuente_id', 'insumos_catalogo', type_="foreignkey")
    op.drop_constraint('fk_baseline_programas_obra_actualizado_por_id', 'programas_obra', type_="foreignkey")
    op.drop_constraint('fk_baseline_programas_obra_creado_por_id', 'programas_obra', type_="foreignkey")
    op.drop_constraint('fk_baseline_programas_obra_expediente_id', 'programas_obra', type_="foreignkey")
    op.drop_constraint('fk_baseline_actividades_programa_programa_id', 'actividades_programa', type_="foreignkey")
    op.drop_constraint('fk_baseline_levantamientos_actualizado_por_id', 'levantamientos', type_="foreignkey")
    op.drop_constraint('fk_baseline_levantamientos_creado_por_id', 'levantamientos', type_="foreignkey")
    op.drop_constraint('fk_baseline_levantamientos_expediente_id', 'levantamientos', type_="foreignkey")
    op.drop_constraint('fk_baseline_puntos_topograficos_levantamiento_id', 'puntos_topograficos', type_="foreignkey")
    op.drop_constraint('fk_baseline_superficies_tin_actualizado_por_id', 'superficies_tin', type_="foreignkey")
    op.drop_constraint('fk_baseline_superficies_tin_creado_por_id', 'superficies_tin', type_="foreignkey")
    op.drop_constraint('fk_baseline_superficies_tin_expediente_id', 'superficies_tin', type_="foreignkey")
    op.drop_constraint('fk_baseline_superficies_tin_levantamiento_id', 'superficies_tin', type_="foreignkey")
    op.drop_constraint('fk_baseline_calculos_volumen_actualizado_por_id', 'calculos_volumen', type_="foreignkey")
    op.drop_constraint('fk_baseline_calculos_volumen_creado_por_id', 'calculos_volumen', type_="foreignkey")
    op.drop_constraint('fk_baseline_calculos_volumen_expediente_id', 'calculos_volumen', type_="foreignkey")
    op.drop_constraint('fk_baseline_calculos_volumen_partida_id', 'calculos_volumen', type_="foreignkey")
    op.drop_constraint('fk_baseline_calculos_volumen_superficie_existente_id', 'calculos_volumen', type_="foreignkey")
    op.drop_constraint('fk_baseline_calculos_volumen_superficie_proyecto_id', 'calculos_volumen', type_="foreignkey")
    op.drop_constraint('fk_baseline_validaciones_expediente_ejecutado_por_id', 'validaciones_expediente', type_="foreignkey")
    op.drop_constraint('fk_baseline_validaciones_expediente_expediente_id', 'validaciones_expediente', type_="foreignkey")
    op.drop_constraint('fk_baseline_validaciones_expediente_tenant_id', 'validaciones_expediente', type_="foreignkey")
    op.drop_constraint('fk_baseline_validaciones_propuesta_actualizado_por_id', 'validaciones_propuesta', type_="foreignkey")
    op.drop_constraint('fk_baseline_validaciones_propuesta_creado_por_id', 'validaciones_propuesta', type_="foreignkey")
    op.drop_constraint('fk_baseline_validaciones_propuesta_expediente_id', 'validaciones_propuesta', type_="foreignkey")
    op.drop_constraint('fk_baseline_validaciones_propuesta_proposicion_id', 'validaciones_propuesta', type_="foreignkey")
    op.drop_constraint('fk_baseline_validaciones_propuesta_tenant_id', 'validaciones_propuesta', type_="foreignkey")
    op.drop_constraint('fk_baseline_checks_validacion_tenant_id', 'checks_validacion', type_="foreignkey")
    op.drop_constraint('fk_baseline_tenant_uso_tenant_id', 'tenant_uso', type_="foreignkey")
    op.drop_constraint('fk_baseline_suscripciones_actualizado_por_id', 'suscripciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_suscripciones_creado_por_id', 'suscripciones', type_="foreignkey")
    op.drop_constraint('fk_baseline_suscripciones_tenant_id', 'suscripciones', type_="foreignkey")
    op.drop_table('insumos')
    op.drop_table('clash_resultados')
    op.drop_table('validaciones_propuesta')
    op.drop_table('penalizaciones_contrato')
    op.drop_table('inconformidades')
    op.drop_table('garantias_contrato')
    op.drop_table('evaluaciones_licitacion')
    op.drop_table('evaluaciones_compliance')
    op.drop_table('entregables_contrato')
    op.drop_table('elementos_bim')
    op.drop_table('documentos_cde')
    op.drop_table('convenios_modificatorios')
    op.drop_table('conceptos')
    op.drop_table('calculos_volumen')
    op.drop_table('superficies_tin')
    op.drop_table('sanciones')
    op.drop_table('puntos_topograficos')
    op.drop_table('proposiciones')
    op.drop_table('precios_unitarios_asignados')
    op.drop_table('partidas')
    op.drop_table('juntas_aclaraciones')
    op.drop_table('contratos')
    op.drop_table('analisis_clash')
    op.drop_table('actividades_programa')
    op.drop_table('workflow_condiciones')
    op.drop_table('validaciones_expediente')
    op.drop_table('unidades_administrativas')
    op.drop_table('tareas_workflow')
    op.drop_table('representantes_legales')
    op.drop_table('programas_obra')
    op.drop_table('presupuestos')
    op.drop_table('planeacion_expediente')
    op.drop_table('modelos_bim')
    op.drop_table('licitaciones')
    op.drop_table('levantamientos')
    op.drop_table('insumos_catalogo')
    op.drop_table('ejecucion_reglas')
    op.drop_table('documentos')
    op.drop_table('conceptos_catalogo')
    op.drop_table('workflow_transiciones')
    op.drop_table('transiciones_workflow')
    op.drop_table('suscripciones')
    op.drop_table('reglas_negocio')
    op.drop_table('reglas_cumplimiento_catalogo')
    op.drop_table('reglas_cumplimiento')
    op.drop_table('proveedores')
    op.drop_table('invitations')
    op.drop_table('expedientes_obra')
    op.drop_table('entidades')
    op.drop_table('catalogos_apu')
    op.drop_table('catalogo_fuentes')
    op.drop_table('audit_ledger')
    op.drop_table('users')
    op.drop_table('tenant_uso')
    op.drop_table('checks_validacion')
    op.drop_table('catalogo_procedimientos')
    op.drop_table('catalogo_juridico')
    op.drop_table('workflows')
    op.drop_table('workflow_pasos')
    op.drop_table('tenants')
    op.drop_table('plan_limites')
    op.drop_table('notification_logs')
    op.drop_table('app_modulos')
