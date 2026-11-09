/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

/**
 * Instancia única del cliente Megalodon para toda la app.
 *
 * URL configurable vía VITE_API_URL (ver .env.example en la raíz del
 * frontend). Si no se define, cae a localhost:8000 para desarrollo local.
 */
import { MegalodonClient } from './megalodon-client';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const megalodonClient = new MegalodonClient(API_URL);

// Retirar credenciales persistidas por versiones anteriores.
try { localStorage.removeItem('megalodon-auth'); } catch {
  // El almacenamiento puede estar deshabilitado; no se utiliza para autenticar.
}
