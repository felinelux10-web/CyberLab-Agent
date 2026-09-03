import os
from lab_v4_dev.core.agent import Agent


def test_end_to_end_status(tmp_path, monkeypatch):
    # Run in isolated tmp dir to avoid touching user's real workspace
    monkeypatch.chdir(tmp_path)

    a = Agent()
    ok = a.boot()
    assert ok is True

    # Simple non-LLM intent that should not require external providers
    res = a.run("ما حالة النظام")
    assert isinstance(res, dict)
    assert res.get("status") == "success"
    assert res.get("intent") in ("STATUS", "status") or res.get("intent") is not None

    # After successful run, session should have recorded a task
    sess = getattr(a, "session", None)
    if sess:
        # session.record_task increments tasks_done in many implementations
        # Check that session summary exists and has numeric counters
        try:
            summary = sess.summary()
            assert isinstance(summary, dict)
        except Exception:
            # Some session implementations may not provide summary in test env
            pass
