/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

export type AppCategory =
  | 'system'
  | 'productivity'
  | 'development'
  | 'media'
  | 'communication'
  | 'science'
  | 'games'
  | 'flagship';

// Estado de negocio del módulo (independiente de `category`, que es solo
// agrupación visual). Ver app/models/entitlements.py::EstadoModulo en el
// backend -- esa tabla es la fuente de verdad real; estos valores son el
// default estático que se usa mientras GET /entitlements/modulos responde
// (o si el usuario no está autenticado aún), ver useEntitlementsStore.
export type EstadoModulo =
  | 'core'        // negocio real, núcleo del producto
  | 'demo'        // existe en cualquier plan, funcionalidad limitada
  | 'internal'    // observabilidad/soporte de la plataforma (GodAdmin)
  | 'admin_only'  // alias de internal, mismo tratamiento
  | 'utility'     // herramienta de escritorio genérica, no es el producto
  | 'showcase';   // demo técnica/tech-demo sin relación con el negocio

export type PlanTipo = 'FREE' | 'INTERMEDIO' | 'PRO' | 'ENTERPRISE';

export interface AppDefinition {
  id: string;
  name: string;
  icon: string;
  category: AppCategory;
  component: string;
  defaultSize: { width: number; height: number };
  minSize: { width: number; height: number };
  estado: EstadoModulo;
  requiresPlan?: PlanTipo;
  requiresRole?: string[];
  pinned: boolean;
}

export interface WindowState {
  id: string;
  appId: string;
  title: string;
  x: number;
  y: number;
  width: number;
  height: number;
  zIndex: number;
  isMinimized: boolean;
  isMaximized: boolean;
  prevSize?: { x: number; y: number; width: number; height: number };
}

export interface Notification {
  id: string;
  type: 'success' | 'warning' | 'error' | 'info';
  title: string;
  message: string;
  appId?: string;
  timestamp: number;
  actions?: { label: string; action: () => void }[];
}

export interface FileSystemNode {
  id: string;
  name: string;
  type: 'folder' | 'file';
  parentId: string | null;
  content?: string;
  icon?: string;
  createdAt: number;
  modifiedAt: number;
  size?: number;
  isOpen?: boolean;
}

export interface DesktopIconPosition {
  appId: string;
  x: number;
  y: number;
}

export interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  items: ContextMenuItem[];
}

export interface ContextMenuItem {
  id: string;
  label: string;
  icon?: string;
  action: () => void;
  separator?: boolean;
  disabled?: boolean;
  submenu?: ContextMenuItem[];
}

export interface User {
  id: string;
  name: string;
  username: string;
  avatar?: string;
  isGuest: boolean;
  role?: string;
}
