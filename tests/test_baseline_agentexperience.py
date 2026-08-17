from __future__ import annotations

import tempfile
from pathlib import Path

from tools.baseline_agentexperience import benchmark

TEST_TEMP_ROOT = Path(__file__).resolve().parent / ".tmp"


def test_baseline_agentexperience_safety_and_effect_invariants() -> None:
    TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
        result = benchmark(3, Path(directory))

    assert result["passed"] is True
    assert result["abstain_behavioral_parity"] is True
    assert result["negative_transfer_count"] == 0
    assert result["arms"]["baseline"]["success_rate"] == 0.5
    assert result["arms"]["experience_assisted"]["success_rate"] == 1.0
    assert result["arms"]["experience_assisted"]["abstention_rate"] == 0.5
