from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


class TestAuditCoverage(unittest.TestCase):
    def test_all_routes_have_audit_event(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "scripts" / "check_audit_coverage.py"

        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

        if proc.returncode != 0:
            output = (proc.stdout or "") + "\n" + (proc.stderr or "")
            self.fail(f"Cobertura de auditoria incompleta:\n{output}")


if __name__ == "__main__":
    unittest.main()
