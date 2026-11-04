"""Exercise the workflow's real shell checkpoint selection without API calls."""
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/daily_podcast.yml"
DATE = "2026-11-03"


class CheckpointSelectionTests(unittest.TestCase):
    def select(self, files, expected, returncode=0):
        workflow = WORKFLOW.read_text()
        start = workflow.index("          if [[ -f ${recovery_dir}/script_editorial_blocked.txt")
        end = workflow.index('          echo "directory=', start)
        shell = textwrap.dedent(workflow[start:end])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in files.items():
                (root / name).write_text(value)
            result = subprocess.run(
                ["bash", "-c", 'recovery_dir="$1"; recovery_date="$2"\n' + shell,
                 "checkpoint-test", directory, DATE],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, returncode, result.stderr)
            if expected is not None:
                self.assertEqual((root / f"script_fact_repaired_{DATE}.txt").read_text(), expected)

    def test_repaired_script_survives_older_candidate(self):
        self.select({f"script_fact_repaired_{DATE}.txt": "corrected",
                     f"script_fact_candidate_{DATE}.txt": "older"}, "corrected")

    def test_candidate_is_available_when_no_repaired_script(self):
        self.select({f"script_fact_candidate_{DATE}.txt": "candidate"}, "candidate")

    def test_latest_editorial_checkpoint_has_precedence(self):
        self.select({"script_editorial_blocked.txt": "latest",
                     f"script_fact_repaired_{DATE}.txt": "older"}, "latest")

    def test_missing_checkpoint_stops_recovery(self):
        self.select({}, None, 1)
