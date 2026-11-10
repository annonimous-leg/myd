---
version: alpha
colors:
  primary: "#947020"
  surface: "#ffffff"
  elevated: "#f3f5f8"
  ink: "#172232"
  secondary: "#435268"
  border: "#d9dfe7"
typography:
  body:
    fontFamily: "Inter, system-ui, sans-serif"
  data:
    fontFamily: "JetBrains Mono, Fira Code, monospace"
  brand:
    fontFamily: "Cinzel, Georgia, serif"
rounded:
  control: "8px"
spacing:
  panel: "20px"
  section: "28px"
omitted:
  - section: components
    reason: "Las variantes viven en los componentes React existentes."
---

# Megalodon · estudio de ingeniería

## Overview

Workspace es el núcleo operativo. La referencia es una mesa profesional de revisión:
documentos legibles, visor técnico amplio y resultados trazables. La identidad se
reconoce por el dorado de selección y el modelo junto a sus cantidades, sin datos
decorativos. La decisión del usuario del 2026-11-10 establece blanco sobrio por
defecto y oscuro seleccionable. La preferencia se comparte, se conserva al recargar
y admite el valor heredado automático.

## Colors

El CSS existente conserva la autoridad de tokens (modelo B).
`Meg-Workspace-Documentos/frontend/app/src/themes.css` define el tema claro y adapta
el oscuro de `index.css`. Los valores anteriores reflejan el claro; no lo generan.
Los consumidores usan `--surface`, `--surface-elevated`, `--text-primary`,
`--text-secondary`, `--text-muted`, `--border-subtle` y `--accent-gold`.
Los estados conservan colores semánticos. BIM hereda el tema y no mantiene una
copia privada que impida cambiarlo. Los colores por tipo IFC pueden ajustarse
visualmente sin modificar el original.

## Typography

Inter para interfaz, JetBrains Mono para cantidades e identificadores y Cinzel
restringido a la marca. Los nombres de obra admiten salto de línea; no comprimir
los controles para acomodarlos. Idioma es-MX.

## Layout

La bandeja Workspace / Tezcatlipoca / Firma / Field SAT se abre desde el botón de
menú. El resto de herramientas conserva la navegación lateral. Workspace es la
entrada autenticada predeterminada.

BIM conserva 56/44 desde 1280 px y 50/50 desde 1024 px. El inspector económico
se desplaza sin mover el visor. Bajo 1024 px, el estudio completo se desplaza:
visor e inspector se apilan y son alcanzables incluso en 390 × 500. Los factores
usan columnas de al menos 115 px. Las herramientas de vista son ocultables.

## Elevation & Depth

Superficies planas y bordes discretos. Sombra para menús y capas flotantes; el
documento debe seguir pareciendo una hoja, no un mosaico de tarjetas.

## Shapes

Controles de 6–8 px y foco visible. Iconos Lucide acompañan acciones reales.
Las barras de desplazamiento permanecen visibles y siguen el tema.

## Components

`useSettingsStore` conserva la preferencia; `useResolvedTheme` resuelve el sistema;
`ThemeController` aplica atributos, clase dark y color-scheme antes de pintar.
`ThemeControl` ofrece la misma acción en cabecera y documentos.

La bandeja usa DropdownMenu de Radix; las confirmaciones, AlertDialog mediante
`useConfirmation`. `navigation.ts` permite aplazar la salida del editor cuando
hay cambios sin guardar. No sustituir esas confirmaciones por ventanas nativas.

`bim-calculator/index.tsx` conserva estados y llamadas. `bim-view.ts` transforma
ejes IFC Z-up a Y-up solo en la escena. `PlanosA3` conserva PDF/SVG/DXF. El cliente
HTTP y backend siguen controlando geometría, cantidades, versiones, precios y permisos.

## Do's and Don'ts

Mostrar datos reales y estados de carga, error y revisión. Ocultar una pared no
elimina su costo. Guardar una revisión no equivale a aprobarla ni firmarla.
No presentar NASA como Street View en tiempo real ni declarar edición CAD, salida
4K o automatización integral sin prueba. La bienvenida y el sistema solar siguen
en la especificación; no usar temporizadores que aparenten terminar el backend.
