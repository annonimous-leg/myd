from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(msg: str) -> None:
    print(f"[FAIL] {msg}")
    raise SystemExit(1)

def ok(msg: str) -> None:
    print(f"[ OK ] {msg}")


def main() -> None:
    venv_python = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not venv_python.exists():
        fail(f"Production venv missing: {venv_python}. Run backend/scripts/install_production_deps.sh in the deployment environment.")
    runner = str(venv_python)

    forbidden = [
        ROOT / "ifcopenshell", ROOT / "geoalchemy2", ROOT / "jose", ROOT / "passlib",
        ROOT / "structlog", ROOT / "aiosqlite", ROOT / "celery", ROOT / "bcrypt.py", ROOT / "jwt.py"
    ]
    shadows=[str(p.relative_to(ROOT)) for p in forbidden if p.exists()]
    if shadows: fail(f"Runtime shadow packages present: {shadows}")
    ok("No local runtime shadows")

    findings=[]
    for base in [ROOT / "app", ROOT / "tezcatlipoca"]:
        for path in base.rglob("*.py"):
            tree=ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Pass): findings.append((str(path), node.lineno, "pass"))
                if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and isinstance(node.exc.func, ast.Name) and node.exc.func.id=="NotImplementedError":
                    findings.append((str(path), node.lineno, "NotImplementedError"))
    if findings: fail(f"Product no-op/unimplemented findings: {findings[:20]}")
    ok("No pass/NotImplementedError in product code")

    compile_cmd=[runner,"-m","compileall","-q",str(ROOT/"app"),str(ROOT/"tezcatlipoca")]
    subprocess.run(compile_cmd,check=True)
    ok("Python compileall")

    subprocess.run([runner,"-m","pip","check"],check=True)
    ok("pip check")

    if not (ROOT.parent / "frontend" / "app" / "package-lock.json").exists():
        fail("frontend/app/package-lock.json missing")
    ok("Frontend lockfile present")

    heads=subprocess.check_output([runner,"-m","alembic","heads"],cwd=ROOT,text=True)
    if heads.count('(head)') != 1: fail(f"Alembic must have one head, got: {heads}")
    ok("Single Alembic head")

    manifest={
        "python": "backend/pyproject.toml",
        "frontend": "frontend/app/package.json",
        "frontend_lock": "frontend/app/package-lock.json",
        "database": "PostgreSQL/PostGIS",
        "queue": "Redis Streams + Celery",
        "object_storage": "Supabase/S3-compatible storage",
        "required_external_validation": [
            "PostgreSQL/PostGIS migration cycle", "Redis/Celery worker recovery",
            "npm ci + typecheck + build + E2E", "load/concurrency", "backup/restore",
            "security/SBOM/dependency scan",
        ],
    }
    (ROOT/"PRODUCTION_GATE_MANIFEST.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
    ok("Production gate manifest written")

if __name__=="__main__": main()
