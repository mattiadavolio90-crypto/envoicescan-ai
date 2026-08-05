import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    env = os.environ.copy()
    env.setdefault("WORKER_DEV_MODE", "1")
    env.setdefault("SUPABASE_URL", "http://x")
    env.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        lines = [
            line for line in result.stdout.splitlines()
            if "PydanticDeprecatedSince" not in line and "@model_validator" not in line
        ]
        tail = "\n".join(lines[-40:])
        print(json.dumps({
            "decision": "block",
            "reason": f"Test suite non verde (exit {result.returncode}). Ultime righe:\n{tail}",
        }))
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
