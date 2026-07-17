from __future__ import annotations

from pathlib import Path
import re
import sys

# Pacchetti la cui versione deve restare allineata fra requirements.txt e il
# lock: un disallineamento su questi rompe la produzione o riapre una CVE.
# `streamlit` era in questa lista fino al 17/7/2026, quando il frontend Streamlit
# e' stato rimosso dal repo: il worker non lo importa (lo shim in
# services/_streamlit_shim.py lo sostituisce) e non e' piu' installato.
CRITICAL_PACKAGES = {
    "supabase",
    "openai",
    "cryptography",
    "pyjwt",
    "python-multipart",
}


SPEC_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*([<>=!~]{1,2})\s*([^\s;#]+)")


def parse_requirements(path: Path) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = SPEC_RE.match(line)
        if not m:
            continue
        name = m.group(1).lower()
        op = m.group(2)
        ver = m.group(3)
        out[name] = (op, ver)
    return out


def main() -> int:
    req = parse_requirements(Path("requirements.txt"))
    lock = parse_requirements(Path("requirements-lock.txt"))

    errors: list[str] = []

    for pkg in sorted(CRITICAL_PACKAGES):
        if pkg not in req:
            errors.append(f"{pkg}: missing in requirements.txt")
            continue
        if pkg not in lock:
            errors.append(f"{pkg}: missing in requirements-lock.txt")
            continue

        req_op, req_ver = req[pkg]
        lock_op, lock_ver = lock[pkg]

        if lock_op != "==":
            errors.append(f"{pkg}: lockfile must pin exact version (found {lock_op}{lock_ver})")

        if req_op == "==":
            if req_ver != lock_ver:
                errors.append(
                    f"{pkg}: requirements.txt pins {req_ver}, lockfile pins {lock_ver}"
                )
        elif req_op in {">=", ">"}:
            # For lower-bound specs we only require lockfile exact pinning;
            # version comparison is intentionally skipped to keep this check dependency-free.
            pass

    if errors:
        print("Requirements consistency check failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    print("Requirements consistency check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
