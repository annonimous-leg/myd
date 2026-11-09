Copyright © 2026 Cristian Rodriguez
All rights reserved.
Unauthorized copying, modification, distribution, or use is prohibited
without prior written permission.

# Megalodon Client TypeScript

Cliente TypeScript para la API REST de Megalodon CostOS v4.

## Instalación

```bash
npm install megalodon-client
```

## Uso básico

```typescript
import { MegalodonClient } from "megalodon-client";

const client = new MegalodonClient("http://localhost:8000");

// Login
const token = await client.auth.login("admin@example.com", "password");

// Listar expedientes
const expedientes = await client.expedientes.list({ limit: 10 });

// WebSocket para progreso
client.websocket.connect(token.access_token);
client.websocket.onProgress("task-id-123", (progress, message) => {
  console.log(`Progreso: ${progress}% - ${message}`);
});
```

## Generar desde OpenAPI

```bash
cd scripts && ./generate-client.sh
```
