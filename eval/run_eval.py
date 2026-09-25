"""Measure mapping accuracy and validation coverage across messy schemas."""
import io
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.schemas import GROUND_TRUTH
from pipeline.canonical import CUSTOMER_FIELDS
from pipeline.mapper import propose_mapping
from pipeline.profiler import profile_dataframe
from pipeline.runner import run_pipeline


def evaluate(name: str, case: dict, use_llm: bool) -> dict:
    df = pd.read_csv(io.StringIO(case["csv"]), dtype=str)
    profiles = profile_dataframe(df)

    start = time.time()
    proposal = propose_mapping(profiles, use_llm=use_llm)
    elapsed = round(time.time() - start, 2)

    truth = case["mapping"]
    correct = wrong = missed = 0
    confident_correct = confident_wrong = 0
    per_field = {}

    for field in proposal["fields"]:
        name_ = field["canonical_field"]
        expected = truth.get(name_)
        actual = field["source_column"]
        is_correct = actual == expected
        per_field[name_] = {
            "expected": expected, "proposed": actual, "correct": is_correct,
            "confidence": field["confidence"], "status": field["status"],
        }
        if is_correct:
            correct += 1
            if field["status"] == "confident":
                confident_correct += 1
        elif actual is None:
            missed += 1
        else:
            wrong += 1
            if field["status"] == "confident":
                confident_wrong += 1

    total = len(CUSTOMER_FIELDS)

    # Run the pipeline using the GROUND TRUTH mapping, so validation is
    # measured independently of mapping accuracy.
    truth_fields = [
        {"canonical_field": f, "source_column": truth.get(f),
         "suggested_transforms": CUSTOMER_FIELDS[f]["default_transforms"]}
        for f in CUSTOMER_FIELDS
    ]
    result = run_pipeline(df, truth_fields)

    return {
        "schema": name,
        "mapping_accuracy": round(correct / total, 2),
        "correct": correct, "wrong": wrong, "missed": missed,
        "confident_precision": round(confident_correct / max(1, confident_correct + confident_wrong), 2),
        "proposal_seconds": elapsed,
        "valid_records": result["valid_count"],
        "expected_valid": case["expected_valid"],
        "exceptions": result["exception_count"],
        "expected_exceptions": case["expected_exceptions"],
        "validation_matches_expectation": (
            result["valid_count"] == case["expected_valid"]
            and result["exception_count"] == case["expected_exceptions"]
        ),
        "per_field": per_field,
    }


def main(use_llm: bool = True) -> None:
    label = "heuristics + LLM" if use_llm else "heuristics only"
    print(f"\n{'=' * 60}\nEvaluation: {label}\n{'=' * 60}")

    results = [evaluate(name, case, use_llm) for name, case in GROUND_TRUTH.items()]

    print(f"\n{'Schema':<22}{'Mapping':<10}{'Conf.prec':<12}{'Valid':<10}{'Exc':<8}{'Sec'}")
    for r in results:
        valid = f"{r['valid_records']}/{r['expected_valid']}"
        exc = f"{r['exceptions']}/{r['expected_exceptions']}"
        flag = "" if r["validation_matches_expectation"] else "  <-- MISMATCH"
        print(f"{r['schema']:<22}{r['mapping_accuracy']:<10.0%}{r['confident_precision']:<12.0%}"
              f"{valid:<10}{exc:<8}{r['proposal_seconds']}{flag}")

    overall = sum(r["mapping_accuracy"] for r in results) / len(results)
    coverage = sum(r["validation_matches_expectation"] for r in results) / len(results)
    print(f"\nMean mapping accuracy: {overall:.0%}")
    print(f"Validation matched expectation on: {coverage:.0%} of schemas")

    print("\nMistakes:")
    for r in results:
        for field, detail in r["per_field"].items():
            if not detail["correct"]:
                print(f"  {r['schema']}.{field}: expected '{detail['expected']}', "
                      f"got '{detail['proposed']}' ({detail['confidence']:.0%})")

    output = Path(__file__).parent / f"results_{'llm' if use_llm else 'heuristics'}.json"
    output.write_text(json.dumps(results, indent=2))
    print(f"\nWritten to {output.name}")


if __name__ == "__main__":
    main(use_llm="--no-llm" not in sys.argv)