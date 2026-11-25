#!/usr/bin/env python3
"""Read-only retrieval acceptance check for a selected saved dialogue session."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from lab_v4_dev.memory.session_state import get_session_by_id
from lab_v4_dev.memory.dialogue_knowledge import retrieve_dialogue_evidence


SESSION_72_ID = "7ccd0498d634430080dcf5d4c27ceb96"

CASES = [
    {
        "category": "user_fact",
        "query": "ما الأدوات المنزلية البسيطة التي استخدمتها؟",
        "expected_exchange_indices": [5],
        "expected_speaker": "user",
    },
    {
        "category": "user_fact",
        "query": "ما سماكة طبقة الجبس؟",
        "expected_exchange_indices": [6],
        "expected_speaker": "user",
    },
    {
        "category": "user_fact",
        "query": "ما الإطار الذي صببت فيه الجبس؟",
        "expected_exchange_indices": [6],
        "expected_speaker": "user",
    },
    {
        "category": "user_fact",
        "query": "ما الألوان التي أضفتها إلى اللوحة؟",
        "expected_exchange_indices": [6],
        "expected_speaker": "user",
    },
    {
        "category": "user_fact",
        "query": "ما نوع الصباغة التي استخدمتها؟",
        "expected_exchange_indices": [7],
        "expected_speaker": "user",
    },
    {
        "category": "user_fact",
        "query": "ما طبقة الحماية النهائية التي وضعتها؟",
        "expected_exchange_indices": [7],
        "expected_speaker": "user",
    },
    {
        "category": "assistant_suggestion",
        "query": "ما الذي اقترحه المساعد عن صنفرة الإطار؟",
        "expected_exchange_indices": [6],
        "expected_speaker": "assistant",
    },
    {
        "category": "assistant_suggestion",
        "query": "ما الطلاء الذي اقترحه المساعد بعد جفاف الجبس؟",
        "expected_exchange_indices": [6],
        "expected_speaker": "assistant",
    },
    {
        "category": "assistant_suggestion",
        "query": "ما مواد الحماية التي اقترحها المساعد؟",
        "expected_exchange_indices": [7],
        "expected_speaker": "assistant",
    },
    {
        "category": "abstention",
        "query": "كم ساعة استغرق تجفيف الجبس بالضبط؟",
        "expected_exchange_indices": [],
        "expected_speaker": None,
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", default=SESSION_72_ID)
    args = parser.parse_args()

    session_id = str(args.session_id).strip()
    record = get_session_by_id(session_id)
    if (
        not isinstance(record, dict)
        or str(record.get("session_id") or "").strip() != session_id
        or str(record.get("session_type") or "").casefold() != "dialogue"
    ):
        print(json.dumps({
            "status": "session_not_found",
            "session_id": session_id,
            "read_only": True,
        }, ensure_ascii=False, indent=2))
        return 2

    results = []
    for case in CASES:
        started = time.perf_counter()
        evidence = retrieve_dialogue_evidence(
            record,
            case["query"],
            limit=8,
            scope="saved",
            session_id=session_id,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        actual_indices = sorted({
            int(item.get("exchange_index") or 0)
            for item in evidence
        })
        expected_indices = case["expected_exchange_indices"]
        if case["category"] == "abstention":
            passed = not evidence
        else:
            passed = bool(set(expected_indices) & set(actual_indices))
            if case["expected_speaker"] == "user":
                passed = passed and any(item.get("matched_user_terms") for item in evidence)
            elif case["expected_speaker"] == "assistant":
                passed = passed and any(item.get("matched_assistant_terms") for item in evidence)
        results.append({
            "category": case["category"],
            "query": case["query"],
            "expected_exchange_indices": expected_indices,
            "actual_exchange_indices": actual_indices,
            "evidence": [
                {
                    "exchange_id": item.get("exchange_id"),
                    "exchange_index": item.get("exchange_index"),
                    "matched_user_terms": item.get("matched_user_terms") or [],
                    "matched_assistant_terms": item.get("matched_assistant_terms") or [],
                }
                for item in evidence
            ],
            "elapsed_ms": round(elapsed_ms, 3),
            "passed": bool(passed),
        })

    total = len(results)
    passed = sum(item["passed"] for item in results)
    report = {
        "status": "passed" if passed == total else "needs_review",
        "session_id": session_id,
        "read_only": True,
        "case_count": total,
        "passed": passed,
        "failed": total - passed,
        "recall_cases": sum(item["category"] != "abstention" for item in results),
        "abstention_cases": sum(item["category"] == "abstention" for item in results),
        "average_retrieval_ms": round(
            sum(item["elapsed_ms"] for item in results) / total, 3
        ),
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
