"""Fail a public build if local/private files have entered the checkout."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
forbidden = ["data", "work", "config.local.json", ".env", "docs/auditoria-datos.md", "docs/validacion.md", "docs/estado-desarrollo.md"]
violations = [name for name in forbidden if (root/name).exists()]
for path in root.rglob("*"):
    if any(part in (".git", ".venv", "__pycache__", ".pytest_cache") for part in path.relative_to(root).parts):
        continue
    if path.is_file() and (path.suffix.lower() in (".xlsx", ".xls", ".sqlite", ".sqlite3", ".db") or path.name.startswith(".env.")):
        violations.append(str(path.relative_to(root)))
if violations:
    raise SystemExit("Public build rejected: private/local file types present. Deploy only the clean Git repository.")
print("Public bundle verified: no operational files, database or local configuration.")
