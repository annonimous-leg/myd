-- Copyright © 2026 Cristian Rodriguez
-- All rights reserved.
-- Unauthorized copying, modification, distribution, or use is prohibited
-- without prior written permission.

-- ============================================================================
-- MEGALODON — Seed Data Temporal para Desarrollo (SQLite)
-- ============================================================================
-- ⚠️  TEMPORAL PARA DESARROLLO — Datos de muestra de catálogos reales
-- Estos datos son PARTES extraídas de PDFs oficiales para desarrollo local.
-- En producción se cargan vía ETL completo a Supabase/PostgreSQL.
-- ============================================================================

-- ============================================================================
-- FUENTES DE CATÁLOGOS
-- ============================================================================

INSERT INTO catalogo_fuentes (id, nombre, tipo, vigencia_inicio, vigencia_fin, descripcion, url_fuente, activo) VALUES
('cfe-2026', 'CFE 2026', 'CFE', '2026-01-01', '2026-12-31', 'Catálogo de Precios Unitarios de la Comisión Federal de Electricidad 2026. Extraído de PDF oficial 1039183160-CATALOGO-DE-PRECIOS-UNITARIOS-CFE-2026.pdf. Precios SIN IVA.', 'https://www.cfe.mx/', 1),
('cmic-pozos-2026', 'CMIC Rehabilitación Pozos 2026', 'CMIC', '2026-01-01', '2026-12-31', 'Catálogo de Rehabilitación de Pozos de la Cámara Mexicana de la Construcción 2026. Extraído de PDF 1030112820-Rehabilitacion-Pozos-2026.pdf. Incluye materiales, maquinaria y mano de obra.', 'https://www.cmic.org/', 1),
('conaga-sgih-2026', 'CONAGA SGIH 2026', 'CONAGA', '2026-01-01', '2026-12-31', 'Catálogo por Gerencia de la Comisión Nacional del Agua 2026. Extraído de PDF CAT_LOGO_POR_GERENCIA_SGIH_2026.pdf. Por gerencias de distrito de riego, unidades de riego y temporal tecnificado.', 'https://www.conagua.gob.mx/', 1),
('salarios-prof-2026', 'Salarios Profesionales 2026', 'CUSTOM', '2026-01-01', '2026-12-31', 'Referencia de salarios profesionales para obra pública en México 2026. Por categoría: ingeniero residente, topógrafo, supervisor, etc.', NULL, 1),
('maquinaria-2026', 'Maquinaria y Equipo 2026', 'CUSTOM', '2026-01-01', '2026-12-31', 'Referencia de costos de maquinaria y equipo para obra pública en México 2026. Por tipo y capacidad.', NULL, 1);

-- ============================================================================
-- CONCEPTOS: CFE 2026 (PARTES extraídas del PDF)
-- Fuente: 1039183160-CATALOGO-DE-PRECIOS-UNITARIOS-CFE-2026.pdf
-- Precios SIN IVA. Unidades: PZ (pieza), SR (servicio)
-- ============================================================================

INSERT INTO conceptos_catalogo (id, fuente_id, clave, descripcion, descripcion_larga, unidad, precio_unitario, zona_economica, estado, incluye_iva, desglose) VALUES
('cfe-ct7-001', 'cfe-2026', 'CT7-001', 'REHABILITACIÓN DE POZO', 'REHABILITACIÓN DE POZO DE AGUA CON DIÁMETRO DE 6" A 10", INCLUYE: LIMPIEZA, REPARACIÓN DE TUBERÍA, COLOCACIÓN DE BOMBA Y PRUEBAS DE FUNCIONAMIENTO. MATERIALES: TUBO PVC C-10, CEMENTO, ARENA, GRAVA. MANO DE OBRA: ALBAÑIL, AYUDANTE, CAPATAZ. MAQUINARIA: CAMIÓN DE VOLTEO, BOMBA DE LODO.', 'PZ', 45000.00, 'Zona I', NULL, 0, '{"materiales": 15000.00, "mano_obra": 18000.00, "maquinaria": 12000.00}'),
('cfe-ct7-002', 'cfe-2026', 'CT7-002', 'REHABILITACIÓN DE POZO', 'REHABILITACIÓN DE POZO DE AGUA CON DIÁMETRO DE 12" A 16", INCLUYE: LIMPIEZA PROFUNDA, REPARACIÓN DE TUBERÍA DE ACERO, COLOCACIÓN DE BOMBA SUMERGIBLE Y PRUEBAS DE RENDIMIENTO. MATERIALES: TUBO ACERO INOXIDABLE, CEMENTO, ARENA, GRAVA, SELLOS. MANO DE OBRA: ALBAÑIL ESPECIALIZADO, AYUDANTE, CAPATAZ, INGENIERO RESIDENTE. MAQUINARIA: GRÚA, CAMIÓN DE VOLTEO, BOMBA DE LODO, COMPRESOR.', 'PZ', 85000.00, 'Zona I', NULL, 0, '{"materiales": 28000.00, "mano_obra": 35000.00, "maquinaria": 22000.00}'),
('cfe-ct7-003', 'cfe-2026', 'CT7-003', 'REHABILITACIÓN DE POZO', 'REHABILITACIÓN DE POZO DE AGUA CON DIÁMETRO DE 6" A 10" (URBANO). INCLUYE: LIMPIEZA, REPARACIÓN DE TUBERÍA, COLOCACIÓN DE BOMBA Y PRUEBAS. MATERIALES: TUBO PVC C-10, CEMENTO, ARENA, GRAVA. MANO DE OBRA: ALBAÑIL, AYUDANTE, CAPATAZ. MAQUINARIA: CAMIÓN DE VOLTEO, BOMBA DE LODO.', 'PZ', 52000.00, 'Zona II', NULL, 0, '{"materiales": 18000.00, "mano_obra": 22000.00, "maquinaria": 12000.00}'),
('cfe-ct7-004', 'cfe-2026', 'CT7-004', 'REHABILITACIÓN DE POZO', 'REHABILITACIÓN DE POZO DE AGUA CON DIÁMETRO DE 12" A 16" (URBANO). INCLUYE: LIMPIEZA PROFUNDA, REPARACIÓN DE TUBERÍA DE ACERO, COLOCACIÓN DE BOMBA SUMERGIBLE Y PRUEBAS DE RENDIMIENTO. MATERIALES: TUBO ACERO INOXIDABLE, CEMENTO, ARENA, GRAVA, SELLOS. MANO DE OBRA: ALBAÑIL ESPECIALIZADO, AYUDANTE, CAPATAZ, INGENIERO RESIDENTE. MAQUINARIA: GRÚA, CAMIÓN DE VOLTEO, BOMBA DE LODO, COMPRESOR.', 'PZ', 98000.00, 'Zona II', NULL, 0, '{"materiales": 32000.00, "mano_obra": 42000.00, "maquinaria": 24000.00}'),
('cfe-ct7-005', 'cfe-2026', 'CT7-005', 'REHABILITACIÓN DE POZO', 'REHABILITACIÓN DE POZO DE AGUA CON DIÁMETRO DE 6" A 10" (RURAL). INCLUYE: LIMPIEZA, REPARACIÓN DE TUBERÍA, COLOCACIÓN DE BOMBA Y PRUEBAS. MATERIALES: TUBO PVC C-10, CEMENTO, ARENA, GRAVA. MANO DE OBRA: ALBAÑIL, AYUDANTE, CAPATAZ. MAQUINARIA: CAMIÓN DE VOLTEO, BOMBA DE LODO.', 'PZ', 38000.00, 'Zona III', NULL, 0, '{"materiales": 12000.00, "mano_obra": 16000.00, "maquinaria": 10000.00}'),
('cfe-ct7-006', 'cfe-2026', 'CT7-006', 'REHABILITACIÓN DE POZO', 'REHABILITACIÓN DE POZO DE AGUA CON DIÁMETRO DE 12" A 16" (RURAL). INCLUYE: LIMPIEZA PROFUNDA, REPARACIÓN DE TUBERÍA DE ACERO, COLOCACIÓN DE BOMBA SUMERGIBLE Y PRUEBAS DE RENDIMIENTO. MATERIALES: TUBO ACERO INOXIDABLE, CEMENTO, ARENA, GRAVA, SELLOS. MANO DE OBRA: ALBAÑIL ESPECIALIZADO, AYUDANTE, CAPATAZ, INGENIERO RESIDENTE. MAQUINARIA: GRÚA, CAMIÓN DE VOLTEO, BOMBA DE LODO, COMPRESOR.', 'PZ', 72000.00, 'Zona III', NULL, 0, '{"materiales": 24000.00, "mano_obra": 30000.00, "maquinaria": 18000.00}'),
('cfe-sr-001', 'cfe-2026', 'SR-001', 'SERVICIO DE SONDAJE', 'SONDAJE DE RECONOCIMIENTO DEL SUBSUELO HASTA 30 M DE PROFUNDIDAD, INCLUYE: EQUIPO, OPERADOR, MUESTRAS CADA 1.50 M, REGISTRO FOTOGRÁFICO Y MEMORIA TÉCNICA. MATERIALES: TUBO DE SONDAJE, CEMENTO BENTONÍTICO. MANO DE OBRA: OPERADOR DE SONDAJE, AYUDANTE, GEOLOGO. MAQUINARIA: SONDA ROTATORIA.', 'SR', 18000.00, 'Zona I', NULL, 0, '{"materiales": 3000.00, "mano_obra": 10000.00, "maquinaria": 5000.00}'),
('cfe-sr-002', 'cfe-2026', 'SR-002', 'SERVICIO DE SONDAJE', 'SONDAJE DE RECONOCIMIENTO DEL SUBSUELO HASTA 30 M DE PROFUNDIDAD (URBANO), INCLUYE: EQUIPO, OPERADOR, MUESTRAS CADA 1.50 M, REGISTRO FOTOGRÁFICO Y MEMORIA TÉCNICA. MATERIALES: TUBO DE SONDAJE, CEMENTO BENTONÍTICO. MANO DE OBRA: OPERADOR DE SONDAJE, AYUDANTE, GEOLOGO. MAQUINARIA: SONDA ROTATORIA.', 'SR', 22000.00, 'Zona II', NULL, 0, '{"materiales": 3500.00, "mano_obra": 12000.00, "maquinaria": 6500.00}'),
('cfe-sr-003', 'cfe-2026', 'SR-003', 'SERVICIO DE SONDAJE', 'SONDAJE DE RECONOCIMIENTO DEL SUBSUELO HASTA 30 M DE PROFUNDIDAD (RURAL), INCLUYE: EQUIPO, OPERADOR, MUESTRAS CADA 1.50 M, REGISTRO FOTOGRÁFICO Y MEMORIA TÉCNICA. MATERIALES: TUBO DE SONDAJE, CEMENTO BENTONÍTICO. MANO DE OBRA: OPERADOR DE SONDAJE, AYUDANTE, GEOLOGO. MAQUINARIA: SONDA ROTATORIA.', 'SR', 15000.00, 'Zona III', NULL, 0, '{"materiales": 2500.00, "mano_obra": 8500.00, "maquinaria": 4000.00}');

-- ============================================================================
-- CONCEPTOS: CMIC Rehabilitación de Pozos 2026 (PARTES extraídas del PDF)
-- Fuente: 1030112820-Rehabilitacion-Pozos-2026.pdf
-- Incluye materiales, maquinaria y mano de obra específica
-- ============================================================================

INSERT INTO conceptos_catalogo (id, fuente_id, clave, descripcion, descripcion_larga, unidad, precio_unitario, zona_economica, estado, incluye_iva, desglose) VALUES
('cmic-pozo-001', 'cmic-pozos-2026', 'POZO-6-10', 'REHABILITACIÓN POZO 6"-10"', 'REHABILITACIÓN DE POZO DE AGUA POTABLE DE 6" A 10" DE DIÁMETRO. INCLUYE: DESAZOLVE, REPARACIÓN DE REVESTIMIENTO, INSTALACIÓN DE EQUIPO DE BOMBEO, PRUEBAS DE RENDIMIENTO Y PUESTA EN OPERACIÓN. MATERIALES: TUBO PVC C-10 Ø6"-10", CEMENTO PORTLAND TIPO II, ARENA, GRAVA 3/4", SELLOS HIDRÁULICOS. MANO DE OBRA: CAPATAZ, ALBAÑIL ESPECIALIZADO, AYUDANTE, MECÁNICO DE BOMBAS. MAQUINARIA: GRÚA 5 TON, CAMIÓN DE VOLTEO 7 M3, BOMBA DE LODO, COMPRESOR 185 CFM, EQUIPO DE VIDEO INSPECCIÓN.', 'PZ', 48500.00, 'Urbano', NULL, 0, '{"materiales": 16500.00, "mano_obra": 19500.00, "maquinaria": 12500.00}'),
('cmic-pozo-002', 'cmic-pozos-2026', 'POZO-12-16', 'REHABILITACIÓN POZO 12"-16"', 'REHABILITACIÓN DE POZO DE AGUA POTABLE DE 12" A 16" DE DIÁMETRO. INCLUYE: DESAZOLVE PROFUNDO, REPARACIÓN DE REVESTIMIENTO DE ACERO INOXIDABLE, INSTALACIÓN DE BOMBA SUMERGIBLE, PRUEBAS DE RENDIMIENTO Y PUESTA EN OPERACIÓN. MATERIALES: TUBO ACERO INOXIDABLE 304 Ø12"-16", CEMENTO PORTLAND TIPO II, ARENA, GRAVA 3/4", SELLOS HIDRÁULICOS, ANILLOS DE CENTRADO. MANO DE OBRA: INGENIERO RESIDENTE, CAPATAZ, ALBAÑIL ESPECIALIZADO (2), AYUDANTE (2), MECÁNICO DE BOMBAS, ELECTRICISTA. MAQUINARIA: GRÚA 10 TON, CAMIÓN DE VOLTEO 14 M3, BOMBA DE LODO, COMPRESOR 375 CFM, EQUIPO DE VIDEO INSPECCIÓN, GENERADOR 50 KVA.', 'PZ', 92000.00, 'Urbano', NULL, 0, '{"materiales": 30000.00, "mano_obra": 38000.00, "maquinaria": 24000.00}'),
('cmic-pozo-003', 'cmic-pozos-2026', 'POZO-6-10-R', 'REHABILITACIÓN POZO 6"-10" RURAL', 'REHABILITACIÓN DE POZO DE AGUA POTABLE DE 6" A 10" DE DIÁMETRO EN ZONA RURAL. INCLUYE: DESAZOLVE, REPARACIÓN DE REVESTIMIENTO, INSTALACIÓN DE EQUIPO DE BOMBEO, PRUEBAS DE RENDIMIENTO Y PUESTA EN OPERACIÓN. MATERIALES: TUBO PVC C-10 Ø6"-10", CEMENTO PORTLAND TIPO II, ARENA, GRAVA 3/4", SELLOS HIDRÁULICOS. MANO DE OBRA: CAPATAZ, ALBAÑIL, AYUDANTE, MECÁNICO DE BOMBAS. MAQUINARIA: GRÚA 3 TON, CAMIÓN DE VOLTEO 5 M3, BOMBA DE LODO, COMPRESOR 185 CFM.', 'PZ', 41000.00, 'Rural', NULL, 0, '{"materiales": 13000.00, "mano_obra": 17000.00, "maquinaria": 11000.00}'),
('cmic-pozo-004', 'cmic-pozos-2026', 'POZO-12-16-R', 'REHABILITACIÓN POZO 12"-16" RURAL', 'REHABILITACIÓN DE POZO DE AGUA POTABLE DE 12" A 16" DE DIÁMETRO EN ZONA RURAL. INCLUYE: DESAZOLVE PROFUNDO, REPARACIÓN DE REVESTIMIENTO DE ACERO INOXIDABLE, INSTALACIÓN DE BOMBA SUMERGIBLE, PRUEBAS DE RENDIMIENTO Y PUESTA EN OPERACIÓN. MATERIALES: TUBO ACERO INOXIDABLE 304 Ø12"-16", CEMENTO PORTLAND TIPO II, ARENA, GRAVA 3/4", SELLOS HIDRÁULICOS, ANILLOS DE CENTRADO. MANO DE OBRA: CAPATAZ, ALBAÑIL ESPECIALIZADO (2), AYUDANTE (2), MECÁNICO DE BOMBAS. MAQUINARIA: GRÚA 5 TON, CAMIÓN DE VOLTEO 10 M3, BOMBA DE LODO, COMPRESOR 375 CFM, GENERADOR 30 KVA.', 'PZ', 78000.00, 'Rural', NULL, 0, '{"materiales": 26000.00, "mano_obra": 32000.00, "maquinaria": 20000.00}');

-- ============================================================================
-- CONCEPTOS: CONAGA SGIH 2026 (PARTES extraídas del PDF)
-- Fuente: CAT_LOGO_POR_GERENCIA_SGIH_2026.pdf
-- Por gerencia: Distritos de Riego, Unidades de Riego, Temporal Tecnificado
-- Código: X.X.X.X, Unidades: Pza, m2, m3, km
-- ============================================================================

INSERT INTO conceptos_catalogo (id, fuente_id, clave, descripcion, descripcion_larga, unidad, precio_unitario, zona_economica, estado, incluye_iva, desglose) VALUES
('conaga-1-1-1-1', 'conaga-sgih-2026', '1.1.1.1', 'LIMPIEZA Y DESBROCE DE TERRENO', 'LIMPIEZA Y DESBROCE DE TERRENO EN ÁREA DE CONSTRUCCIÓN, INCLUYE: RETIRO DE MALEZA, ARBUSTOS, ROCAS MENORES Y NIVELACIÓN PRELIMINAR. MATERIALES: NINGUNO. MANO DE OBRA: PEÓN (3), CAPATAZ. MAQUINARIA: TRACTOR AGRÍCOLA CON RASTRA.', 'm2', 12.50, 'Distrito Riego 01', 'Aguascalientes', 0, '{"materiales": 0.00, "mano_obra": 8.50, "maquinaria": 4.00}'),
('conaga-1-1-1-2', 'conaga-sgih-2026', '1.1.1.2', 'EXCAVACIÓN A MANO EN TERRENO NORMAL', 'EXCAVACIÓN A MANO EN TERRENO NORMAL (ARCILLA LIMOSA, ARENA), INCLUYE: CARGA Y ACARREO A 20 M. MATERIALES: NINGUNO. MANO DE OBRA: PEÓN (4), CAPATAZ. MAQUINARIA: NINGUNA.', 'm3', 185.00, 'Distrito Riego 01', 'Aguascalientes', 0, '{"materiales": 0.00, "mano_obra": 185.00, "maquinaria": 0.00}'),
('conaga-1-1-1-3', 'conaga-sgih-2026', '1.1.1.3', 'EXCAVACIÓN CON MAQUINARIA EN TERRENO NORMAL', 'EXCAVACIÓN CON MAQUINARIA EN TERRENO NORMAL, INCLUYE: CARGA Y ACARREO A 50 M. MATERIALES: NINGUNO. MANO DE OBRA: OPERADOR DE EXCAVADORA, CAPATAZ. MAQUINARIA: EXCAVADORA HIDRAULICA 320 CAT.', 'm3', 95.00, 'Distrito Riego 01', 'Aguascalientes', 0, '{"materiales": 0.00, "mano_obra": 25.00, "maquinaria": 70.00}'),
('conaga-1-1-1-4', 'conaga-sgih-2026', '1.1.1.4', 'RELLENO Y COMPACTACIÓN CON MATERIAL PROPIO', 'RELLENO Y COMPACTACIÓN CON MATERIAL PROPIO, INCLUYE: ACARREO, EXTENDIDO, HUMECTACIÓN Y COMPACTACIÓN A 95% PROCTOR. MATERIALES: AGUA. MANO DE OBRA: PEÓN (3), CAPATAZ. MAQUINARIA: VIBROCOMPACTADOR 10 TON, MOTOBOMBA.', 'm3', 145.00, 'Distrito Riego 01', 'Aguascalientes', 0, '{"materiales": 5.00, "mano_obra": 65.00, "maquinaria": 75.00}'),
('conaga-1-1-1-5', 'conaga-sgih-2026', '1.1.1.5', 'CONCRETO HIDRÁULICO f''c=150 KG/CM2', 'CONCRETO HIDRÁULICO f''c=150 KG/CM2, INCLUYE: FABRICACIÓN, TRANSPORTE Y COLOCACIÓN. MATERIALES: CEMENTO PORTLAND TIPO II, ARENA, GRAVA 3/4", AGUA, ADITIVO PLASTIFICANTE. MANO DE OBRA: ALBAÑIL, AYUDANTE, CAPATAZ. MAQUINARIA: REVOLVEDORA 1 BOLSA, VIBRADOR, BOMBA DE CONCRETO (opcional).', 'm3', 2850.00, 'Distrito Riego 01', 'Aguascalientes', 0, '{"materiales": 1450.00, "mano_obra": 650.00, "maquinaria": 750.00}'),
('conaga-1-1-1-6', 'conaga-sgih-2026', '1.1.1.6', 'CONCRETO HIDRÁULICO f''c=200 KG/CM2', 'CONCRETO HIDRÁULICO f''c=200 KG/CM2, INCLUYE: FABRICACIÓN, TRANSPORTE Y COLOCACIÓN. MATERIALES: CEMENTO PORTLAND TIPO II, ARENA, GRAVA 3/4", AGUA, ADITIVO PLASTIFICANTE. MANO DE OBRA: ALBAÑIL, AYUDANTE, CAPATAZ. MAQUINARIA: REVOLVEDORA 1 BOLSA, VIBRADOR, BOMBA DE CONCRETO (opcional).', 'm3', 3200.00, 'Distrito Riego 01', 'Aguascalientes', 0, '{"materiales": 1650.00, "mano_obra": 700.00, "maquinaria": 850.00}'),
('conaga-1-1-1-7', 'conaga-sgih-2026', '1.1.1.7', 'ACERO DE REFUERZO FY=4200 KG/CM2', 'ACERO DE REFUERZO GRADO 60 FY=4200 KG/CM2, INCLUYE: CORTE, DOBLEZ, AMARRE Y COLOCACIÓN. MATERIALES: ALAMBRE RECOCIDO N°16. MANO DE OBRA: ARMADOR, AYUDANTE, CAPATAZ. MAQUINARIA: CORTADORA, DOBLADORA, SOLDADORA (opcional).', 'kg', 28.50, 'Distrito Riego 01', 'Aguascalientes', 0, '{"materiales": 18.00, "mano_obra": 7.50, "maquinaria": 3.00}'),
('conaga-1-1-1-8', 'conaga-sgih-2026', '1.1.1.8', 'TUBO PVC HIDRAULICO C-10 Ø6"', 'TUBO PVC HIDRAULICO SERIE C-10 Ø6" (160 MM), INCLUYE: SUMINISTRO, TRANSPORTE Y COLOCACIÓN. MATERIALES: TUBO PVC C-10, JUNTAS ELÁSTICAS, LUBRICANTE, ANCLAS. MANO DE OBRA: ALBAÑIL, AYUDANTE, CAPATAZ. MAQUINARIA: NINGUNA.', 'm', 485.00, 'Distrito Riego 01', 'Aguascalientes', 0, '{"materiales": 380.00, "mano_obra": 85.00, "maquinaria": 20.00}'),
('conaga-1-1-1-9', 'conaga-sgih-2026', '1.1.1.9', 'TUBO PVC HIDRAULICO C-10 Ø8"', 'TUBO PVC HIDRAULICO SERIE C-10 Ø8" (200 MM), INCLUYE: SUMINISTRO, TRANSPORTE Y COLOCACIÓN. MATERIALES: TUBO PVC C-10, JUNTAS ELÁSTICAS, LUBRICANTE, ANCLAS. MANO DE OBRA: ALBAÑIL, AYUDANTE, CAPATAZ. MAQUINARIA: NINGUNA.', 'm', 720.00, 'Distrito Riego 01', 'Aguascalientes', 0, '{"materiales": 560.00, "mano_obra": 120.00, "maquinaria": 40.00}'),
('conaga-1-1-1-10', 'conaga-sgih-2026', '1.1.1.10', 'TUBO PVC HIDRAULICO C-10 Ø10"', 'TUBO PVC HIDRAULICO SERIE C-10 Ø10" (250 MM), INCLUYE: SUMINISTRO, TRANSPORTE Y COLOCACIÓN. MATERIALES: TUBO PVC C-10, JUNTAS ELÁSTICAS, LUBRICANTE, ANCLAS. MANO DE OBRA: ALBAÑIL, AYUDANTE, CAPATAZ. MAQUINARIA: GRÚA 3 TON (opcional).', 'm', 1150.00, 'Distrito Riego 01', 'Aguascalientes', 0, '{"materiales": 900.00, "mano_obra": 180.00, "maquinaria": 70.00}'),
('conaga-1-1-2-1', 'conaga-sgih-2026', '1.1.2.1', 'LIMPIEZA Y DESBROCE DE TERRENO', 'LIMPIEZA Y DESBROCE DE TERRENO EN ÁREA DE CONSTRUCCIÓN, INCLUYE: RETIRO DE MALEZA, ARBUSTOS, ROCAS MENORES Y NIVELACIÓN PRELIMINAR. MATERIALES: NINGUNO. MANO DE OBRA: PEÓN (3), CAPATAZ. MAQUINARIA: TRACTOR AGRÍCOLA CON RASTRA.', 'm2', 14.80, 'Unidad Riego 03', 'Jalisco', 0, '{"materiales": 0.00, "mano_obra": 10.20, "maquinaria": 4.60}'),
('conaga-1-1-2-2', 'conaga-sgih-2026', '1.1.2.2', 'EXCAVACIÓN A MANO EN TERRENO NORMAL', 'EXCAVACIÓN A MANO EN TERRENO NORMAL (ARCILLA LIMOSA, ARENA), INCLUYE: CARGA Y ACARREO A 20 M. MATERIALES: NINGUNO. MANO DE OBRA: PEÓN (4), CAPATAZ. MAQUINARIA: NINGUNA.', 'm3', 210.00, 'Unidad Riego 03', 'Jalisco', 0, '{"materiales": 0.00, "mano_obra": 210.00, "maquinaria": 0.00}'),
('conaga-1-1-2-3', 'conaga-sgih-2026', '1.1.2.3', 'CONCRETO HIDRÁULICO f''c=150 KG/CM2', 'CONCRETO HIDRÁULICO f''c=150 KG/CM2, INCLUYE: FABRICACIÓN, TRANSPORTE Y COLOCACIÓN. MATERIALES: CEMENTO PORTLAND TIPO II, ARENA, GRAVA 3/4", AGUA, ADITIVO PLASTIFICANTE. MANO DE OBRA: ALBAÑIL, AYUDANTE, CAPATAZ. MAQUINARIA: REVOLVEDORA 1 BOLSA, VIBRADOR, BOMBA DE CONCRETO (opcional).', 'm3', 3100.00, 'Unidad Riego 03', 'Jalisco', 0, '{"materiales": 1580.00, "mano_obra": 720.00, "maquinaria": 800.00}'),
('conaga-1-1-3-1', 'conaga-sgih-2026', '1.1.3.1', 'LIMPIEZA Y DESBROCE DE TERRENO', 'LIMPIEZA Y DESBROCE DE TERRENO EN ÁREA DE CONSTRUCCIÓN, INCLUYE: RETIRO DE MALEZA, ARBUSTOS, ROCAS MENORES Y NIVELACIÓN PRELIMINAR. MATERIALES: NINGUNO. MANO DE OBRA: PEÓN (3), CAPATAZ. MAQUINARIA: TRACTOR AGRÍCOLA CON RASTRA.', 'm2', 11.20, 'Temporal Tecnificado 05', 'Sinaloa', 0, '{"materiales": 0.00, "mano_obra": 7.50, "maquinaria": 3.70}'),
('conaga-1-1-3-2', 'conaga-sgih-2026', '1.1.3.2', 'EXCAVACIÓN A MANO EN TERRENO NORMAL', 'EXCAVACIÓN A MANO EN TERRENO NORMAL (ARCILLA LIMOSA, ARENA), INCLUYE: CARGA Y ACARREO A 20 M. MATERIALES: NINGUNO. MANO DE OBRA: PEÓN (4), CAPATAZ. MAQUINARIA: NINGUNA.', 'm3', 165.00, 'Temporal Tecnificado 05', 'Sinaloa', 0, '{"materiales": 0.00, "mano_obra": 165.00, "maquinaria": 0.00}'),
('conaga-1-1-3-3', 'conaga-sgih-2026', '1.1.3.3', 'CONCRETO HIDRÁULICO f''c=150 KG/CM2', 'CONCRETO HIDRÁULICO f''c=150 KG/CM2, INCLUYE: FABRICACIÓN, TRANSPORTE Y COLOCACIÓN. MATERIALES: CEMENTO PORTLAND TIPO II, ARENA, GRAVA 3/4", AGUA, ADITIVO PLASTIFICANTE. MANO DE OBRA: ALBAÑIL, AYUDANTE, CAPATAZ. MAQUINARIA: REVOLVEDORA 1 BOLSA, VIBRADOR, BOMBA DE CONCRETO (opcional).', 'm3', 2650.00, 'Temporal Tecnificado 05', 'Sinaloa', 0, '{"materiales": 1350.00, "mano_obra": 600.00, "maquinaria": 700.00}');

-- ============================================================================
-- INSUMOS: MATERIALES (referencia de mercado obra pública)
-- Fuente: Inferencia de catálogos CFE, CMIC, CONAGA + mercado 2026
-- ============================================================================

INSERT INTO insumos_catalogo (id, fuente_id, clave, descripcion, tipo, unidad, precio_unitario, categoria, subcategoria, zona_economica, estado, incluye_iva) VALUES
('mat-cemento-001', 'maquinaria-2026', 'CEM-001', 'CEMENTO PORTLAND TIPO II', 'MATERIAL', 'ton', 4200.00, 'Cemento', 'Portland', 'Nacional', NULL, 0),
('mat-cemento-002', 'maquinaria-2026', 'CEM-002', 'CEMENTO PORTLAND COMPUESTO CPC 30R', 'MATERIAL', 'ton', 3850.00, 'Cemento', 'Compuesto', 'Nacional', NULL, 0),
('mat-arena-001', 'maquinaria-2026', 'ARE-001', 'ARENA LIMOSA PARA CONCRETO', 'MATERIAL', 'm3', 180.00, 'Agregado', 'Arena', 'Nacional', NULL, 0),
('mat-grava-001', 'maquinaria-2026', 'GRA-001', 'GRAVA TRITURADA 3/4"', 'MATERIAL', 'm3', 320.00, 'Agregado', 'Grava', 'Nacional', NULL, 0),
('mat-grava-002', 'maquinaria-2026', 'GRA-002', 'GRAVA TRITURADA 1/2"', 'MATERIAL', 'm3', 350.00, 'Agregado', 'Grava', 'Nacional', NULL, 0),
('mat-acero-001', 'maquinaria-2026', 'ACR-001', 'ACERO DE REFUERZO GRADO 60 #3 (3/8")', 'MATERIAL', 'kg', 18.50, 'Acero', 'Refuerzo', 'Nacional', NULL, 0),
('mat-acero-002', 'maquinaria-2026', 'ACR-002', 'ACERO DE REFUERZO GRADO 60 #4 (1/2")', 'MATERIAL', 'kg', 18.50, 'Acero', 'Refuerzo', 'Nacional', NULL, 0),
('mat-acero-003', 'maquinaria-2026', 'ACR-003', 'ACERO DE REFUERZO GRADO 60 #5 (5/8")', 'MATERIAL', 'kg', 18.50, 'Acero', 'Refuerzo', 'Nacional', NULL, 0),
('mat-acero-004', 'maquinaria-2026', 'ACR-004', 'ACERO DE REFUERZO GRADO 60 #6 (3/4")', 'MATERIAL', 'kg', 18.50, 'Acero', 'Refuerzo', 'Nacional', NULL, 0),
('mat-pvc-001', 'maquinaria-2026', 'PVC-001', 'TUBO PVC HIDRAULICO C-10 Ø4" (110 MM)', 'MATERIAL', 'm', 185.00, 'PVC', 'Hidráulico', 'Nacional', NULL, 0),
('mat-pvc-002', 'maquinaria-2026', 'PVC-002', 'TUBO PVC HIDRAULICO C-10 Ø6" (160 MM)', 'MATERIAL', 'm', 320.00, 'PVC', 'Hidráulico', 'Nacional', NULL, 0),
('mat-pvc-003', 'maquinaria-2026', 'PVC-003', 'TUBO PVC HIDRAULICO C-10 Ø8" (200 MM)', 'MATERIAL', 'm', 480.00, 'PVC', 'Hidráulico', 'Nacional', NULL, 0),
('mat-pvc-004', 'maquinaria-2026', 'PVC-004', 'TUBO PVC HIDRAULICO C-10 Ø10" (250 MM)', 'MATERIAL', 'm', 750.00, 'PVC', 'Hidráulico', 'Nacional', NULL, 0),
('mat-pvc-005', 'maquinaria-2026', 'PVC-005', 'TUBO PVC HIDRAULICO C-10 Ø12" (315 MM)', 'MATERIAL', 'm', 1150.00, 'PVC', 'Hidráulico', 'Nacional', NULL, 0),
('mat-aditivo-001', 'maquinaria-2026', 'ADI-001', 'ADITIVO PLASTIFICANTE PARA CONCRETO', 'MATERIAL', 'lt', 85.00, 'Aditivo', 'Plastificante', 'Nacional', NULL, 0),
('mat-sello-001', 'maquinaria-2026', 'SEL-001', 'SELLO HIDRÁULICO PARA JUNTAS DE TUBO PVC', 'MATERIAL', 'pza', 45.00, 'Sello', 'Hidráulico', 'Nacional', NULL, 0),
('mat-lubricante-001', 'maquinaria-2026', 'LUB-001', 'LUBRICANTE PARA JUNTAS DE PVC', 'MATERIAL', 'kg', 120.00, 'Lubricante', 'PVC', 'Nacional', NULL, 0);

-- ============================================================================
-- INSUMOS: MANO DE OBRA (referencia de mercado obra pública)
-- Fuente: Inferencia de catálogos CFE, CMIC, CONAGA + mercado 2026
-- ============================================================================

INSERT INTO insumos_catalogo (id, fuente_id, clave, descripcion, tipo, unidad, precio_unitario, categoria, subcategoria, zona_economica, estado, incluye_iva) VALUES
('mo-peon-001', 'salarios-prof-2026', 'MO-001', 'PEÓN DE CONSTRUCCIÓN', 'MANO_OBRA', 'hr', 65.00, 'Peón', 'General', 'Nacional', NULL, 0),
('mo-ayudante-001', 'salarios-prof-2026', 'MO-002', 'AYUDANTE DE ALBAÑIL', 'MANO_OBRA', 'hr', 85.00, 'Ayudante', 'Albañilería', 'Nacional', NULL, 0),
('mo-albanil-001', 'salarios-prof-2026', 'MO-003', 'ALBAÑIL ESPECIALIZADO', 'MANO_OBRA', 'hr', 120.00, 'Albañil', 'Especializado', 'Nacional', NULL, 0),
('mo-capataz-001', 'salarios-prof-2026', 'MO-004', 'CAPATAZ DE OBRA', 'MANO_OBRA', 'hr', 180.00, 'Capataz', 'Obra', 'Nacional', NULL, 0),
('mo-armador-001', 'salarios-prof-2026', 'MO-005', 'ARMADOR DE ACERO', 'MANO_OBRA', 'hr', 140.00, 'Armador', 'Acero', 'Nacional', NULL, 0),
('mo-mecanico-001', 'salarios-prof-2026', 'MO-006', 'MECÁNICO DE BOMBAS', 'MANO_OBRA', 'hr', 200.00, 'Mecánico', 'Bombas', 'Nacional', NULL, 0),
('mo-electricista-001', 'salarios-prof-2026', 'MO-007', 'ELECTRICISTA INDUSTRIAL', 'MANO_OBRA', 'hr', 190.00, 'Electricista', 'Industrial', 'Nacional', NULL, 0),
('mo-operador-001', 'salarios-prof-2026', 'MO-008', 'OPERADOR DE MAQUINARIA PESADA', 'MANO_OBRA', 'hr', 250.00, 'Operador', 'Maquinaria Pesada', 'Nacional', NULL, 0),
('mo-operador-002', 'salarios-prof-2026', 'MO-009', 'OPERADOR DE SONDAJE', 'MANO_OBRA', 'hr', 280.00, 'Operador', 'Sondaje', 'Nacional', NULL, 0),
('mo-geologo-001', 'salarios-prof-2026', 'MO-010', 'GEÓLOGO DE CAMPO', 'MANO_OBRA', 'hr', 350.00, 'Geólogo', 'Campo', 'Nacional', NULL, 0);

-- ============================================================================
-- INSUMOS: MAQUINARIA Y EQUIPO (referencia de mercado obra pública)
-- Fuente: Inferencia de catálogos CFE, CMIC, CONAGA + mercado 2026
-- ============================================================================

INSERT INTO insumos_catalogo (id, fuente_id, clave, descripcion, tipo, unidad, precio_unitario, categoria, subcategoria, zona_economica, estado, incluye_iva) VALUES
('maq-excavadora-001', 'maquinaria-2026', 'MQ-001', 'EXCAVADORA HIDRAULICA 320 CAT (1.2 M3)', 'MAQUINARIA', 'hr', 1850.00, 'Excavadora', 'Hidráulica', 'Nacional', NULL, 0),
('maq-excavadora-002', 'maquinaria-2026', 'MQ-002', 'EXCAVADORA HIDRAULICA 336 CAT (1.8 M3)', 'MAQUINARIA', 'hr', 2200.00, 'Excavadora', 'Hidráulica', 'Nacional', NULL, 0),
('maq-vibro-001', 'maquinaria-2026', 'MQ-003', 'VIBROCOMPACTADOR 10 TON', 'MAQUINARIA', 'hr', 950.00, 'Compactación', 'Vibrocompactador', 'Nacional', NULL, 0),
('maq-vibro-002', 'maquinaria-2026', 'MQ-004', 'VIBROCOMPACTADOR 15 TON', 'MAQUINARIA', 'hr', 1200.00, 'Compactación', 'Vibrocompactador', 'Nacional', NULL, 0),
('maq-grua-001', 'maquinaria-2026', 'MQ-005', 'GRÚA TELESCÓPICA 5 TON', 'MAQUINARIA', 'hr', 850.00, 'Grúa', 'Telescópica', 'Nacional', NULL, 0),
('maq-grua-002', 'maquinaria-2026', 'MQ-006', 'GRÚA TELESCÓPICA 10 TON', 'MAQUINARIA', 'hr', 1400.00, 'Grúa', 'Telescópica', 'Nacional', NULL, 0),
('maq-grua-003', 'maquinaria-2026', 'MQ-007', 'GRÚA TELESCÓPICA 25 TON', 'MAQUINARIA', 'hr', 2500.00, 'Grúa', 'Telescópica', 'Nacional', NULL, 0),
('maq-camion-001', 'maquinaria-2026', 'MQ-008', 'CAMIÓN DE VOLTEO 7 M3', 'MAQUINARIA', 'hr', 650.00, 'Camión', 'Volteo', 'Nacional', NULL, 0),
('maq-camion-002', 'maquinaria-2026', 'MQ-009', 'CAMIÓN DE VOLTEO 14 M3', 'MAQUINARIA', 'hr', 950.00, 'Camión', 'Volteo', 'Nacional', NULL, 0),
('maq-camion-003', 'maquinaria-2026', 'MQ-010', 'CAMIÓN DE VOLTEO 20 M3', 'MAQUINARIA', 'hr', 1200.00, 'Camión', 'Volteo', 'Nacional', NULL, 0),
('maq-bomba-001', 'maquinaria-2026', 'MQ-011', 'BOMBA DE LODO 6X5', 'MAQUINARIA', 'hr', 750.00, 'Bomba', 'Lodo', 'Nacional', NULL, 0),
('maq-compresor-001', 'maquinaria-2026', 'MQ-012', 'COMPRESOR 185 CFM', 'MAQUINARIA', 'hr', 550.00, 'Compresor', 'Portátil', 'Nacional', NULL, 0),
('maq-compresor-002', 'maquinaria-2026', 'MQ-013', 'COMPRESOR 375 CFM', 'MAQUINARIA', 'hr', 850.00, 'Compresor', 'Portátil', 'Nacional', NULL, 0),
('maq-generador-001', 'maquinaria-2026', 'MQ-014', 'GENERADOR 30 KVA', 'MAQUINARIA', 'hr', 450.00, 'Generador', 'Eléctrico', 'Nacional', NULL, 0),
('maq-generador-002', 'maquinaria-2026', 'MQ-015', 'GENERADOR 50 KVA', 'MAQUINARIA', 'hr', 650.00, 'Generador', 'Eléctrico', 'Nacional', NULL, 0),
('maq-tractor-001', 'maquinaria-2026', 'MQ-016', 'TRACTOR AGRÍCOLA CON RASTRA', 'MAQUINARIA', 'hr', 380.00, 'Tractor', 'Agrícola', 'Nacional', NULL, 0),
('maq-revolvedora-001', 'maquinaria-2026', 'MQ-017', 'REVOLVEDORA 1 BOLSA', 'MAQUINARIA', 'hr', 120.00, 'Revolvedora', 'Concreto', 'Nacional', NULL, 0),
('maq-vibrador-001', 'maquinaria-2026', 'MQ-018', 'VIBRADOR DE CONCRETO ELÉCTRICO', 'MAQUINARIA', 'hr', 85.00, 'Vibrador', 'Concreto', 'Nacional', NULL, 0),
('maq-sonda-001', 'maquinaria-2026', 'MQ-019', 'SONDA ROTATORIA PARA SONDAJE', 'MAQUINARIA', 'hr', 2800.00, 'Sonda', 'Rotatoria', 'Nacional', NULL, 0),
('maq-video-001', 'maquinaria-2026', 'MQ-020', 'EQUIPO DE VIDEO INSPECCIÓN DE POZOS', 'MAQUINARIA', 'hr', 1500.00, 'Video', 'Inspección', 'Nacional', NULL, 0);

-- ============================================================================
-- INSUMOS: SALARIOS PROFESIONALES (referencia mercado obra pública 2026)
-- Fuente: Referencia de mercado + catálogos de obra pública
-- ============================================================================

INSERT INTO insumos_catalogo (id, fuente_id, clave, descripcion, tipo, unidad, precio_unitario, categoria, subcategoria, zona_economica, estado, incluye_iva) VALUES
('sal-ingeniero-001', 'salarios-prof-2026', 'SP-001', 'INGENIERO RESIDENTE DE OBRA (Civil)', 'SALARIO_PROFESIONAL', 'mes', 45000.00, 'Ingeniería', 'Residente', 'Nacional', NULL, 0),
('sal-ingeniero-002', 'salarios-prof-2026', 'SP-002', 'INGENIERO RESIDENTE DE OBRA (Mecánico)', 'SALARIO_PROFESIONAL', 'mes', 45000.00, 'Ingeniería', 'Residente', 'Nacional', NULL, 0),
('sal-ingeniero-003', 'salarios-prof-2026', 'SP-003', 'INGENIERO SUPERVISOR (Civil)', 'SALARIO_PROFESIONAL', 'mes', 55000.00, 'Ingeniería', 'Supervisor', 'Nacional', NULL, 0),
('sal-topografo-001', 'salarios-prof-2026', 'SP-004', 'TOPÓGRAFO ESPECIALIZADO', 'SALARIO_PROFESIONAL', 'mes', 32000.00, 'Topografía', 'Especializado', 'Nacional', NULL, 0),
('sal-arquitecto-001', 'salarios-prof-2026', 'SP-005', 'ARQUITECTO DISEÑADOR', 'SALARIO_PROFESIONAL', 'mes', 38000.00, 'Arquitectura', 'Diseñador', 'Nacional', NULL, 0),
('sal-admin-001', 'salarios-prof-2026', 'SP-006', 'ADMINISTRADOR DE OBRA', 'SALARIO_PROFESIONAL', 'mes', 35000.00, 'Administración', 'Obra', 'Nacional', NULL, 0),
('sal-contador-001', 'salarios-prof-2026', 'SP-007', 'CONTADOR DE OBRA', 'SALARIO_PROFESIONAL', 'mes', 30000.00, 'Contabilidad', 'Obra', 'Nacional', NULL, 0),
('sal-jefe-001', 'salarios-prof-2026', 'SP-008', 'JEFE DE OBRA', 'SALARIO_PROFESIONAL', 'mes', 65000.00, 'Jefatura', 'Obra', 'Nacional', NULL, 0),
('sal-coord-001', 'salarios-prof-2026', 'SP-009', 'COORDINADOR DE SEGURIDAD', 'SALARIO_PROFESIONAL', 'mes', 42000.00, 'Seguridad', 'Coordinador', 'Nacional', NULL, 0),
('sal-ambiental-001', 'salarios-prof-2026', 'SP-010', 'ESPECIALISTA AMBIENTAL', 'SALARIO_PROFESIONAL', 'mes', 40000.00, 'Ambiental', 'Especialista', 'Nacional', NULL, 0);

-- ============================================================================
-- INSUMOS: COSTOS POR m², m³, etc. (referencia de mercado)
-- Fuente: Inferencia de catálogos + mercado 2026
-- ============================================================================

INSERT INTO insumos_catalogo (id, fuente_id, clave, descripcion, tipo, unidad, precio_unitario, categoria, subcategoria, zona_economica, estado, incluye_iva) VALUES
('costo-m2-001', 'maquinaria-2026', 'CM2-001', 'MURO DE BLOCK 15X20X40 CM (MANO DE OBRA + MATERIAL)', 'MATERIAL', 'm2', 850.00, 'Mampostería', 'Block', 'Nacional', NULL, 0),
('costo-m2-002', 'maquinaria-2026', 'CM2-002', 'MURO DE LADRILLO 7X14X28 CM (MANO DE OBRA + MATERIAL)', 'MATERIAL', 'm2', 720.00, 'Mampostería', 'Ladrillo', 'Nacional', NULL, 0),
('costo-m2-003', 'maquinaria-2026', 'CM2-003', 'CIMIENTO CORRIDO DE CONCRETO f''c=150 KG/CM2 (MANO DE OBRA + MATERIAL)', 'MATERIAL', 'm', 1850.00, 'Cimentación', 'Corrida', 'Nacional', NULL, 0),
('costo-m3-001', 'maquinaria-2026', 'CM3-001', 'CONCRETO HIDRÁULICO f''c=150 KG/CM2 (MANO DE OBRA + MATERIAL)', 'MATERIAL', 'm3', 2850.00, 'Concreto', 'Hidráulico', 'Nacional', NULL, 0),
('costo-m3-002', 'maquinaria-2026', 'CM3-002', 'CONCRETO HIDRÁULICO f''c=200 KG/CM2 (MANO DE OBRA + MATERIAL)', 'MATERIAL', 'm3', 3200.00, 'Concreto', 'Hidráulico', 'Nacional', NULL, 0),
('costo-m3-003', 'maquinaria-2026', 'CM3-003', 'CONCRETO HIDRÁULICO f''c=250 KG/CM2 (MANO DE OBRA + MATERIAL)', 'MATERIAL', 'm3', 3650.00, 'Concreto', 'Hidráulico', 'Nacional', NULL, 0),
('costo-ml-001', 'maquinaria-2026', 'CML-001', 'CIMENTACIÓN DE ZAPATA AISLADA f''c=200 KG/CM2 (MANO DE OBRA + MATERIAL)', 'MATERIAL', 'ml', 2200.00, 'Cimentación', 'Zapata', 'Nacional', NULL, 0),
('costo-ml-002', 'maquinaria-2026', 'CML-002', 'LOSA DE CONCRETO f''c=200 KG/CM2 ESPESOR 15 CM (MANO DE OBRA + MATERIAL)', 'MATERIAL', 'ml', 1850.00, 'Losa', 'Concreto', 'Nacional', NULL, 0);

-- ============================================================================
-- DATOS DE PRUEBA: TENANT + USUARIO ADMIN
-- ============================================================================

INSERT INTO tenants (id, name, slug, config, branding) VALUES
('tenant-megalodon', 'MEGALODON S.A. de C.V.', 'megalodon', '{"moneda": "MXN", "zona_horaria": "America/Mexico_City"}', '{"color_primario": "#0F172A", "logo": "/logo.svg"}');

INSERT INTO users (id, tenant_id, email, hashed_password, full_name, rfc, role, is_active, is_verified) VALUES
('admin-001', 'tenant-megalodon', 'admin@megalodon.mx', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', 'Administrador MEGALODON', 'MEGA123456ABC', 'admin', 1, 1);
