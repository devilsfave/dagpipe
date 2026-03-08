"""Router regression tests — ensures heuristic accuracy does not degrade over time.

Run manually: pytest tests/test_router_regression.py -v
Run in CI: included in the standard test matrix via test.yml

If this test fails:
  1. Open tests/router_fixtures.json
  2. Identify which prompts are mis-classified
  3. Update the heuristics in src/dagpipe/router.py
  4. Re-run until accuracy >= threshold
"""
from __future__ import annotations

import json
from pathlib import Path
from dagpipe.router import classify_complexity


FIXTURES_PATH = Path(__file__).parent / "router_fixtures.json"


def test_router_classification_accuracy() -> None:
    """Router must correctly classify at least 85% of the fixture prompts."""
    data = json.loads(FIXTURES_PATH.read_text())
    fixtures = data["fixtures"]
    threshold = data["threshold_accuracy"]

    correct = 0
    wrong = []

    for item in fixtures:
        prompt = item["prompt"]
        expected = item["expected"]  # "low" or "high"
        score = classify_complexity(prompt)
        predicted = "high" if score >= 0.7 else "low"

        if predicted == expected:
            correct += 1
        else:
            wrong.append({
                "prompt": prompt[:60] + "...",
                "expected": expected,
                "predicted": predicted,
                "score": round(score, 2),
                "category": item["category"],
            })

    accuracy = correct / len(fixtures)

    if wrong:
        details = "\n".join(
            f"  [{w['category']}] score={w['score']} expected={w['expected']} "
            f"predicted={w['predicted']}: {w['prompt']}"
            for w in wrong
        )
        print(f"\nMis-classified ({len(wrong)}/{len(fixtures)}):\n{details}")

    assert accuracy >= threshold, (
        f"Router accuracy {accuracy:.1%} is below threshold {threshold:.0%}. "
        f"{len(wrong)} prompts mis-classified. "
        f"Update heuristics in src/dagpipe/router.py."
    )
