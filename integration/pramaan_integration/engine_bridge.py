"""Load the in-tree production library unchanged; never fall back to another copy."""
from pathlib import Path
import sys

ENGINE = Path(__file__).resolve().parents[2] / "recall-engine"
sys.path.insert(0, str(ENGINE))
import pramaan_recall  # noqa: E402

if Path(pramaan_recall.__file__).resolve().parent != ENGINE / "pramaan_recall":
    raise RuntimeError("Unexpected recall-engine package")

Config = pramaan_recall.Config
evaluate = pramaan_recall.evaluate
evaluate_series = pramaan_recall.evaluate_series
replay = pramaan_recall.replay
