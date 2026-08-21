"""
P09 — Canonical Project Knowledge ownership tests.
"""

from pathlib import Path
from lab_v4_dev.project_knowledge import ProjectKnowledgeCore
from lab_v4_dev.project_knowledge.contracts import (
    KnowledgeQuery,
    KnowledgeResult,
    ProjectFile,
    ProjectRelationship,
    ProjectSymbol,
)


def test_p09_contract_objects():
    f = ProjectFile("example.py", "python", "python")
    s = ProjectSymbol("main", "function", "example.py", 1)
    r = ProjectRelationship("example.py", "imports", "os")

    assert f.path == "example.py"
    assert s.name == "main"
    assert r.relation == "imports"


def test_p09_query_contract():
    q = KnowledgeQuery("find parser", limit=5)
    result = KnowledgeResult(
        items=("intent_parser.py",),
        query=q,
    )

    assert result.source == "project_knowledge"
    assert result.query.limit == 5


def test_p09_core_is_canonical_facade():
    core = ProjectKnowledgeCore()
    assert core.DOMAIN == "project_knowledge"
    assert core.VERSION == "P09"
    assert core.capabilities() == {
        "scanner": False,
        "analyzer_registry": False,
        "analysis_engine": False,
        "knowledge_store": False,
        "relationship_engine": False,
        "query_engine": False,
        "graph_query": False,
    }


def test_p09_core_rejects_unconfigured_operations():
    core = ProjectKnowledgeCore()

    calls = (
        (core.scan, (".",)),
        (core.analyze, ("example.py",)),
        (core.query, ("find parser",)),
        (core.relationships, (object(),)),
        (core.store, (object(),)),
    )

    for method, args in calls:
        try:
            method(*args)
        except RuntimeError:
            pass
        else:
            raise AssertionError(
                "unconfigured P09 operation did not fail"
            )


def test_p09_analysis_engine_is_persistence_free():
    import inspect
    from lab_v4_dev.project_knowledge.analysis_engine import AnalysisEngine

    source = inspect.getsource(AnalysisEngine)

    assert "knowledge_store" not in source
    assert "store_analysis" not in source
    assert "save_relationships" not in source
    assert "RelationshipEngine" not in source


def test_p09_core_pipeline_requires_canonical_boundaries():
    core = ProjectKnowledgeCore()

    try:
        core.analyze_file("example.py")
    except RuntimeError as exc:
        assert "analysis_engine" in str(exc)
    else:
        raise AssertionError(
            "P09 canonical pipeline accepted an unconfigured analyzer"
        )


def test_p09_knowledge_store_enables_foreign_keys():
    from lab_v4_dev.project_knowledge import knowledge_store

    conn = knowledge_store.get_connection()
    try:
        value = conn.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]

        assert value == 1
    finally:
        conn.close()


def test_p09_knowledge_store_has_required_indexes():
    from lab_v4_dev.project_knowledge import knowledge_store

    knowledge_store.initialize()

    conn = knowledge_store.get_connection()

    try:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='index'
            """
        ).fetchall()

        names = {row[0] for row in rows}

        assert "idx_symbols_file_id" in names
        assert "idx_symbols_name" in names
        assert "idx_dependencies_file_id" in names
        assert "idx_relationships_source" in names
        assert "idx_relationships_target" in names
    finally:
        conn.close()


def test_p09_store_analysis_replaces_file_knowledge_atomically():
    from types import SimpleNamespace
    from lab_v4_dev.project_knowledge import knowledge_store

    knowledge_store.initialize()

    result = SimpleNamespace(
        file_path="__p09_transaction_test__.py",
        language="python",
        symbols=[
            {
                "name": "first",
                "kind": "function",
                "line": 1,
            }
        ],
        dependencies=[
            {
                "name": "os",
                "kind": "import",
                "line": 1,
            }
        ],
    )

    file_id = knowledge_store.store_analysis(
        result,
        file_hash="p09-test",
        size=1,
        modified="test",
    )

    assert file_id is not None

    info = knowledge_store.get_file(
        "__p09_transaction_test__.py"
    )

    assert info is not None

    symbols = knowledge_store.get_symbols(info[0])
    dependencies = knowledge_store.get_dependencies(info[0])

    assert symbols == [
        ("first", "function", 1)
    ]

    assert dependencies == [
        ("os", "import", 1)
    ]

    # Verify replacement semantics.
    result.symbols = [
        {
            "name": "second",
            "kind": "function",
            "line": 2,
        }
    ]

    result.dependencies = []

    knowledge_store.store_analysis(
        result,
        file_hash="p09-test-2",
        size=2,
        modified="test-2",
    )

    info = knowledge_store.get_file(
        "__p09_transaction_test__.py"
    )

    symbols = knowledge_store.get_symbols(info[0])
    dependencies = knowledge_store.get_dependencies(info[0])

    assert symbols == [
        ("second", "function", 2)
    ]

    assert dependencies == []

    # Test isolation: remove the temporary knowledge created by this test.
    conn = knowledge_store.get_connection()
    try:
        conn.execute("BEGIN")
        conn.execute(
            "DELETE FROM relationships WHERE source_file=?",
            ("__p09_transaction_test__.py",),
        )
        conn.execute(
            "DELETE FROM dependencies WHERE file_id=?",
            (info[0],),
        )
        conn.execute(
            "DELETE FROM symbols WHERE file_id=?",
            (info[0],),
        )
        conn.execute(
            "DELETE FROM files WHERE id=?",
            (info[0],),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_p09_canonical_file_identity_for_relative_path():
    from lab_v4_dev.project_knowledge import knowledge_store

    assert (
        knowledge_store.canonical_file_path(
            "lab_v4_dev/core/orchestrator.py"
        )
        == "lab_v4_dev/core/orchestrator.py"
    )


def test_p09_canonical_file_identity_for_absolute_project_path():
    from lab_v4_dev.core.project_context import get_active_project_root
    from lab_v4_dev.project_knowledge import knowledge_store

    root = Path(get_active_project_root()).resolve()

    path = root / "lab_v4_dev" / "core" / "agent.py"

    assert (
        knowledge_store.canonical_file_path(str(path))
        == "lab_v4_dev/core/agent.py"
    )


def test_p09_canonical_file_identity_rejects_external_absolute_path():
    import tempfile

    from lab_v4_dev.project_knowledge import knowledge_store

    outside = tempfile.gettempdir()

    try:
        knowledge_store.canonical_file_path(
            str(Path(outside) / "p09_external.py")
        )
    except ValueError as exc:
        assert "outside active project" in str(exc)
    else:
        raise AssertionError(
            "External absolute path was accepted"
        )


def test_p09_store_analysis_normalizes_absolute_project_path():
    from pathlib import Path
    from types import SimpleNamespace

    from lab_v4_dev.core.project_context import get_active_project_root
    from lab_v4_dev.project_knowledge import knowledge_store

    root = Path(get_active_project_root()).resolve()

    absolute = (
        root
        / "__p09_canonical_absolute_test__.py"
    )

    result = SimpleNamespace(
        file_path=str(absolute),
        language="python",
        symbols=[],
        dependencies=[],
    )

    file_id = knowledge_store.store_analysis(
        result,
        file_hash="p09-canonical",
        size=1,
        modified="test",
    )

    assert file_id is not None

    info = knowledge_store.get_file(
        "__p09_canonical_absolute_test__.py"
    )

    assert info is not None
    assert info[1] == "__p09_canonical_absolute_test__.py"

    # Test isolation: remove the temporary knowledge created by this test.
    conn = knowledge_store.get_connection()
    try:
        conn.execute("BEGIN")
        conn.execute(
            "DELETE FROM relationships WHERE source_file=?",
            ("__p09_canonical_absolute_test__.py",),
        )
        conn.execute(
            "DELETE FROM dependencies WHERE file_id=?",
            (info[0],),
        )
        conn.execute(
            "DELETE FROM symbols WHERE file_id=?",
            (info[0],),
        )
        conn.execute(
            "DELETE FROM files WHERE id=?",
            (info[0],),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_p09_relationship_write_normalizes_absolute_source():
    from pathlib import Path
    from types import SimpleNamespace

    from lab_v4_dev.core.project_context import get_active_project_root
    from lab_v4_dev.project_knowledge import knowledge_store

    root = Path(get_active_project_root()).resolve()

    relationship = SimpleNamespace(
        source=str(
            root
            / "lab_v4_dev"
            / "core"
            / "agent.py"
        ),
        target="os",
        relation_type="imports",
        target_kind="import",
    )

    knowledge_store.save_relationships([relationship])

    conn = knowledge_store.get_connection()

    try:
        row = conn.execute(
            """
            SELECT source_file
            FROM relationships
            WHERE source_file=?
              AND target_name=?
              AND relation_type=?
            """,
            (
                "lab_v4_dev/core/agent.py",
                "os",
                "imports",
            ),
        ).fetchone()

        assert row == ("lab_v4_dev/core/agent.py",)

    finally:
        conn.close()
