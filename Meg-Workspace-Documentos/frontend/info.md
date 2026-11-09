<!--
Copyright © 2026 Cristian Rodriguez
All rights reserved.
Unauthorized copying, modification, distribution, or use is prohibited
without prior written permission.
-->

# Research Findings: Megalodon — Web-Based Linux Replica

## User Request Summary
Build a fully web-based Linux desktop replica with 50+ fully functional applications. The OS should be called "Megalodon" (reference: Exodus 33:14). It integrates three major systems:

1. **Megalodon CostOS** — Construction cost estimation system for Mexican public works
2. **3D Citation Star-Map** — Network neuroscience visualization
3. **General SaaS Platform** — Civil engineering and architecture tools

## Key Features Required

### Megalodon CostOS (from megalodon_costos_v3_1.py)
- Full construction cost estimation per Mexican law (LOPSRM, LAASSP, LFT, CFF, RMF 2026)
- Legal constants: thresholds for adjudication, salary factor (FSR), machinery hourly costs
- Error handling system (CPLError) with severity levels
- Virtual file system (CPLVsi) for document management
- Background job queue (CPLQueue) for processing
- Progress tracking (CPLProgress)
- Hash utilities for document verification (CPLHash)
- QuadTree spatial indexing for topography
- Multiple engines:
  - **MotorFallo** — Failure cause registration and pattern analysis
  - **MotorEvidencia** — Evidence registry and validation rules
  - **MotorPreciosBIM** — BIM price catalog, cost calculation for construction elements
  - **MonteCarloRiesgo** — Risk simulation (1,000+ iterations, percentiles)
  - **MotorJuridico** — Legal framework validation (LOPSRM, LAASSP)
  - **ValidadorDeterminista** — Deterministic validation (SAT 32D, social security, e-signature, FSR arithmetic, machinery costs, overhead factors)
- CalendarioLaboral — Mexican working calendar with holidays
- CifradoReposo — AES-256-GCM encryption for documents
- FsrIndexer — Price source indexing (INEGI, Banxico, CONASAMI, SAT)
- MerkleTree — Document integrity verification
- Canonical JSON serialization (RFC 8785)

### 3D Citation Star-Map (from txt spec)
- Full-viewport 3D visualization using Three.js / React Three Fiber
- ~200 real papers with computed edges at build time
- Nodes as radial glow sprites (gold), faint citation edges
- UnrealBloomPass + starfield dust
- Even ellipsoid spread, hard min node spacing
- Camera dollies, auto-rotate, orbit/zoom/pan controls
- Wheel zoom (canvas only, not page scroll)
- Click node → highlight neighbors + right-side detail card with abstract and link
- Legend hover/click to dim other communities
- Download corpus (ZIP) button
- Error boundary, all hooks before early returns

### SaaS Platform Requirements (from txt spec)
- Modern, clean, professional design using Tailwind CSS + shadcn/ui + Radix UI
- Smooth animations (Framer Motion), excellent typography
- Configurable dark mode, perfect responsiveness
- Brand theming capability
- Low-cost infrastructure (< $20-50/month for 500-1000 users)
- Clean, scalable, documented code
- Multi-tenancy ready

## Technical Stack Specified
- Next.js 15+ (App Router) + TypeScript (adapted to React + Vite per skill)
- Tailwind CSS + shadcn/ui + Radix + Lucide icons
- Framer Motion for animations
- Three.js / React Three Fiber for 3D
- Python integration for math operations (optional WebAssembly)
- Zod for validations
- React Hook Form
- Sentry for errors

## Additional Apps to Include (50+ total)
The OS needs a full suite of desktop applications:

### System & File Management
- File Manager with folder navigation, copy/paste, rename, delete
- Terminal with real command parsing (ls, cd, mkdir, cat, echo, pwd, etc.)
- Text Editor with syntax highlighting
- System Monitor with real-time charts
- Settings panel with themes, display, sound
- Screenshot tool
- Trash/Recycle Bin

### Productivity
- Spreadsheet with formulas (SUM, AVG, etc.)
- Presentation/slides tool
- PDF Viewer
- Notes/Sticky notes
- Task Manager/Kanban
- Calculator (standard + scientific)
- Calendar with events
- Clock/World Clock/Alarm/Timer
- Password manager
- Whiteboard drawing canvas

### Development
- Code Editor with multi-file support
- JSON Viewer/Formatter
- Regex Tester
- Base64/Hash Encoder-Decoder
- API Client (HTTP requests)
- Color Picker & Converter
- Diff Tool
- Git Dashboard visualization

### Media & Graphics
- Image Viewer & Editor (filters, crop, rotate)
- Music Player with playlists
- Video Player
- Paint/Draw application
- SVG Editor
- ASCII Art Generator
- Chart/Graph Maker

### Communication & Internet
- Web Browser (mini with tabs)
- Email Client
- Chat/Messages app
- RSS Reader
- Network Scanner

### Science & Engineering
- BIM Calculator (building information modeling)
- Unit Converter (comprehensive)
- Scientific Calculator
- Periodic Table
- Graphing Calculator (function plotting)
- Monte Carlo Simulator
- Topography visualization tool

### Games
- Snake
- Tetris
- Chess
- Solitaire
- Minesweeper

## Design Direction
- Premium, professional Linux desktop aesthetic
- Dark theme default with light mode option
- Glassmorphism effects on windows
- Smooth window animations (open, close, minimize, maximize)
- Taskbar at bottom with start menu, app pins, system tray
- Desktop icons with right-click context menus
- Multiple virtual desktops (optional)
- Notification system
- Login screen
- Boot/loading sequence animation
