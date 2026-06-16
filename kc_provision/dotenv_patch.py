from __future__ import annotations

from pathlib import Path


def patch_dotenv(path: str, updates: dict[str, str]) -> None:
    """Upsert idempotente di chiavi in un file .env, preservando il resto.

    - se la chiave esiste (riga `KEY=...`) la sostituisce;
    - se non esiste la appende in fondo;
    - non riscrive ne riordina le altre righe, non tocca i commenti.
    """
    p = Path(path)
    lines = (
        p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    )
    remaining = dict(updates)

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in remaining:
            lines[i] = f"{key}={remaining.pop(key)}"

    if remaining:
        if lines and lines[-1].strip():
            lines.append("")
        for key, value in remaining.items():
            lines.append(f"{key}={value}")

    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_dotenv_keys(path: str) -> dict[str, str]:
    """Legge le coppie KEY=VALUE (ignora commenti/righe vuote)."""
    p = Path(path)
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def is_configured(values: dict[str, str], key: str) -> bool:
    """True se la chiave esiste e ha un valore non vuoto."""
    return bool(str(values.get(key, "")).strip().strip('"').strip("'"))
