#!/usr/bin/env python3
"""
Tarea C propiamente dicha: conecta rate_limit_standard/rate_limit_strict
en los endpoints que todavía no lo tienen (331 de 339 -- ya cubiertos:
auth.py x6 y geo_threats.py x2, hechos en turnos anteriores).

Política (verbo HTTP, mecánica y documentada):
- GET/HEAD -> rate_limit_standard (100/60s)
- POST/PUT/PATCH/DELETE -> rate_limit_strict (10/60s)
- Excepciones explícitas (OVERRIDES): webhooks de pago -> standard, para
  no descartar reintentos legítimos de Mercado Pago/Stripe (ya
  verifican firma HMAC propia, el rate limit es una red de seguridad
  extra, no la defensa primaria).
- websocket.py: fuera de este pase (no encaja en el patrón Depends() de
  la misma forma; ya se le agregó revocación de tokens en el turno
  anterior).

Import correcto según módulo:
- app/api/v1/*.py -> from app.core.rate_limit import ...
- tezcatlipoca/routers/*.py -> from core.rate_limit import ...
  (geo_threats.py se excluye, ya está conectado)

Corrige el bug del codemod anterior (fix_auth_gaps.py): ese insertaba
imports nuevos usando una heurística de líneas que fallaba con
docstrings multilínea. Este usa el nodo AST del docstring del módulo
(si existe) y su end_lineno real para insertar siempre DESPUÉS de que
cierre, sin importar cuántas líneas tenga.
"""
import ast
import json
from pathlib import Path
from collections import defaultdict

ROOT = Path("/home/claude/work/backend")
INVENTORY = Path("/tmp/inv_fresh.json")

SKIP_FILES = {
    "app/api/v1/websocket.py",
    "tezcatlipoca/routers/geo_threats.py",  # ya conectado en turno anterior
}

# (file, verb, path) -> tier forzado, anula la política por verbo
OVERRIDES = {
    ("app/api/v1/pagos.py", "post", "/webhook/mercadopago"): "standard",
    ("app/api/v1/pagos.py", "post", "/webhook/stripe"): "standard",
}


def module_for(relpath: str) -> str:
    return "app.core.rate_limit" if relpath.startswith("app/") else "core.rate_limit"


def tier_for(relpath: str, verb: str, path: str) -> str:
    override = OVERRIDES.get((relpath, verb, path))
    if override:
        return override
    return "standard" if verb in ("get", "head", "websocket") else "strict"


def load_targets():
    data = json.loads(INVENTORY.read_text(encoding="utf-8"))
    targets = [
        d for d in data
        if d.get("has_rate_limit") is None and d["file"] not in SKIP_FILES
    ]
    by_file = defaultdict(list)
    for d in targets:
        by_file[d["file"]].append(d)
    return by_file


def param_list_end(fn: ast.AST):
    args = fn.args
    positions = []
    for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
        positions.append((a.end_lineno, a.end_col_offset))
    for d in list(args.defaults) + [d for d in args.kw_defaults if d is not None]:
        positions.append((d.end_lineno, d.end_col_offset))
    if args.vararg:
        positions.append((args.vararg.end_lineno, args.vararg.end_col_offset))
    if args.kwarg:
        positions.append((args.kwarg.end_lineno, args.kwarg.end_col_offset))
    if not positions:
        return None
    return max(positions)


def find_open_paren_after_def(lines, fn):
    ln = fn.lineno - 1
    col = lines[ln].index("(", fn.col_offset) + 1
    return (fn.lineno, col)


def module_docstring_end_lineno(tree: ast.Module):
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        return tree.body[0].end_lineno
    return None


def ensure_fastapi_depends_import(lines):
    for i, line in enumerate(lines):
        if line.startswith("from fastapi import"):
            names_part = line.split("import", 1)[1].strip()
            names = [n.strip() for n in names_part.split(",")]
            if "Depends" not in names:
                names.append("Depends")
                lines[i] = f"from fastapi import {', '.join(names)}\n"
            return True
    return False


def insert_rate_limit_import(lines, tree: ast.Module, relpath: str):
    mod = module_for(relpath)
    import_line = f"from {mod} import rate_limit_standard, rate_limit_strict\n"
    # Ya importado (p.ej. si un turno anterior lo agregó a mano)?
    if any(import_line.strip() == l.strip() for l in lines):
        return
    doc_end = module_docstring_end_lineno(tree)
    insert_at = doc_end if doc_end is not None else 0
    # Si no hay docstring, insertar tras el último import de "cabecera"
    if doc_end is None:
        i = 0
        while i < len(lines) and (
            lines[i].startswith(("import ", "from ")) or lines[i].strip() == ""
        ):
            i += 1
        insert_at = i
    lines.insert(insert_at, import_line)


def process_file(relpath: str, items: list):
    path = ROOT / relpath
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))

    func_nodes = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_nodes[node.name] = node

    lines = src.splitlines(keepends=True)
    insertions = []
    missing = []
    for it in items:
        fn = func_nodes.get(it["function"])
        if fn is None:
            missing.append(it["function"])
            continue
        tier = tier_for(relpath, it["verb"], it.get("path"))
        param_text_body = f"_rate_limit: bool = Depends(rate_limit_{tier})"
        pos = param_list_end(fn)
        if pos is None:
            pos = find_open_paren_after_def(lines, fn)
            text = param_text_body
        else:
            text = ", " + param_text_body
        insertions.append((pos[0], pos[1], text))

    if missing:
        raise SystemExit(f"{relpath}: funciones no encontradas: {missing}")

    insertions.sort(key=lambda t: (t[0], t[1]), reverse=True)
    for line_no, col, text in insertions:
        idx = line_no - 1
        line = lines[idx]
        lines[idx] = line[:col] + text + line[col:]

    ensure_fastapi_depends_import(lines)
    insert_rate_limit_import(lines, tree, relpath)

    new_src = "".join(lines)
    ast.parse(new_src, filename=str(path))  # valida sintaxis antes de escribir
    path.write_text(new_src, encoding="utf-8")
    return len(insertions)


def main():
    by_file = load_targets()
    total = 0
    for relpath, items in sorted(by_file.items()):
        n = process_file(relpath, items)
        print(f"{relpath}: +{n} endpoints con rate limit")
        total += n
    print(f"\nTOTAL: {total} endpoints con rate limit agregado")


if __name__ == "__main__":
    main()
