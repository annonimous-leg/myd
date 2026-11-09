"""Package the tested source tree and isolated acceptance evidence, never a deploy."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def main():
    checkout_sha = git("rev-parse", "HEAD")
    checkout_tree = git("rev-parse", "HEAD^{tree}")
    head_sha = os.environ.get("MEG_HEAD_SHA", checkout_sha)
    head_tree = git("rev-parse", head_sha + "^{tree}")
    if checkout_tree != head_tree:
        raise SystemExit("PR merge tree differs from branch head; do not label it as the same cut.")
    output = Path("review-package")
    output.mkdir(exist_ok=True)
    archive = output / "Meg-proyecto-y-evidencia.zip"
    subprocess.run(["git", "archive", "--format=zip", "--prefix=Meg/", "-o", str(archive), "HEAD"], check=True)
    evidence = Path("collected-evidence")
    with zipfile.ZipFile(archive, "a", compression=zipfile.ZIP_DEFLATED) as bundle:
        source_manifest = {
            info.filename: hashlib.sha256(bundle.read(info.filename)).hexdigest()
            for info in bundle.infolist() if not info.is_dir()
        }
        evidence_manifest = {}
        for path in sorted(evidence.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            name = "evidencia/" + path.relative_to(evidence).as_posix()
            data = path.read_bytes()
            bundle.writestr(name, data)
            evidence_manifest[name] = hashlib.sha256(data).hexdigest()
        manifest = {
            "branch_head_sha": head_sha, "checkout_sha": checkout_sha,
            "tree_sha": checkout_tree, "head_tree_matches_tested_tree": True,
            "run_id": os.getenv("GITHUB_RUN_ID"),
            "run_url": "https://github.com/" + os.environ["GITHUB_REPOSITORY"] + "/actions/runs/" + os.environ["GITHUB_RUN_ID"],
            "environment": "isolated GitHub Actions runner; no application deployment",
            "source_files": source_manifest, "evidence_files": evidence_manifest,
            "external_provider_check": os.getenv("MEG_PROVIDER_RESULT", "unknown"),
            "scope": [
                "BIM, budget, exported files, scheduling, survey/volume and tender UI acceptance",
                "PostgreSQL/PostGIS, Redis and local Supabase Storage containers",
                "Synthetic business fixtures; public provider checks reported separately",
                "HTTP telemetry privacy regression tests cover FastAPI server spans and HTTPX client spans; they do not certify SQLAlchemy, Redis or Celery attributes",
                "Not SAT/TSA acceptance, licensed Street View reconstruction or production operation",
            ],
        }
        bundle.writestr("MANIFIESTO.json", json.dumps(manifest, indent=2))
        bundle.writestr("LEEME.txt", (
            "Meg: código completo versionado y evidencia del mismo árbol probado.\n"
            "El código está en Meg/ y las capturas, trazas e informes en evidencia/.\n"
            "MANIFIESTO.json identifica SHA, árbol, ejecución y hashes por archivo.\n"
            "Las pruebas se ejecutaron en un runner aislado; no son un despliegue.\n"
            "Los expedientes y certificados de aceptación son sintéticos y están rotulados.\n"
            "Consultar Meg/docs/LOCAL_ACCEPTANCE.md para reproducir las pruebas.\n"
            "Un verde de CI no prueba SAT, Street View métrico ni operación en producción.\n"
        ))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / "SHA256SUMS.txt").write_text(f"{digest}  {archive.name}\n")
    print(json.dumps({"archive": str(archive), "sha256": digest, "bytes": archive.stat().st_size,
                      "source_files": len(source_manifest), "evidence_files": len(evidence_manifest),
                      "head_sha": head_sha, "tree_sha": checkout_tree}, indent=2))


if __name__ == "__main__":
    main()
