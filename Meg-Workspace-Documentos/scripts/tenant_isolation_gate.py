"""Static fail-closed gate for tenant-owned domain services/workers.

This is a regression guard, not a substitute for PostgreSQL E2E. It rejects
new direct primary-key reads of tenant-owned roots in critical services and
workers unless the query visibly carries tenant context.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "backend/app/services/bim_service.py": ["ModeloBIM", "ElementoBIM"],
    "backend/app/services/clash_service.py": ["ModeloBIM", "AnalisisClash", "ClashResult"],
    "backend/app/services/programacion_service.py": ["ProgramaObra", "ActividadPrograma"],
    "backend/app/services/presupuesto_service.py": ["Presupuesto", "Partida"],
    "backend/app/services/topografia_service.py": ["Levantamiento", "SuperficieTIN", "CalculoVolumen"],
    "backend/app/services/montecarlo_service.py": ["MonteCarloRun", "Presupuesto", "ProgramaObra"],
    "backend/app/services/procurement/workspace.py": ["TenderPackage", "TenderDocument", "TenderDocumentRevision", "TenderLicitacionBridge"],
    "backend/app/workers/bim_tasks.py": ["ModeloBIM", "ElementoBIM"],
    "backend/app/workers/montecarlo_tasks.py": ["MonteCarloRun"],
    "backend/app/workers/pdf_tasks.py": ["Presupuesto"],
    "backend/app/workers/excel_tasks.py": ["Presupuesto"],
}

# Direct db.get(...) is inherently unsafe for these aggregate roots. Child
# rows without tenant_id must be read through their tenant-bearing parent.
violations = []
for rel, names in TARGETS.items():
    text = (ROOT / rel).read_text()
    if "db.get(" in text:
        for i, line in enumerate(text.splitlines(), 1):
            if "db.get(" in line and any(n in line for n in names):
                violations.append(f"{rel}:{i}: direct db.get on tenant-owned model: {line.strip()}")

# Workers that persist tenant-owned state must carry tenant_id explicitly in
# their task contract. These checks catch accidental regression to an opaque
# UUID-only worker payload.
for rel in ["backend/app/workers/bim_tasks.py", "backend/app/workers/montecarlo_tasks.py"]:
    text = (ROOT / rel).read_text()
    if "tenant_id" not in text:
        violations.append(f"{rel}: worker has no explicit tenant_id context")

if violations:
    print("TENANT ISOLATION GATE: FAIL")
    print("\n".join(violations))
    raise SystemExit(1)
print("TENANT ISOLATION GATE: PASS")
