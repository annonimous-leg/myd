# Megalodon · estudio de ingeniería

La pantalla BIM/CAD presenta el modelo y la revisión técnica en paralelo. La obra activa encabeza la pantalla. La tipografía de interfaz, el dorado de selección y las superficies proceden de las variables existentes en `Meg-Workspace-Documentos/frontend/app/src/index.css`.

La hoja `bim-studio.css` organiza esta pantalla con una cabecera jerárquica y un reparto 56/44 desde 1280 px. El panel derecho conserva el desplazamiento independiente existente. En móvil las superficies se apilan.

Los botones de pasos y pestañas muestran su selección con `aria-pressed`. Los controles nativos conservan su comportamiento de teclado y reciben foco visible. La carga IFC mantiene permisos, procesamiento y recuperación de errores del flujo existente.

El propietario de las llamadas y estados es `bim-calculator/index.tsx`; el cliente HTTP sigue siendo `megalodon-client.ts`. La composición de planos pertenece a `PlanosA3`. Los colores de estado siguen las variables semánticas de la aplicación. Esta entrega cubre la presentación del estudio BIM/CAD.
