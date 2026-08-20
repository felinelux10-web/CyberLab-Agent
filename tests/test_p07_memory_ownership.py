from lab_v4_dev.memory.store import MemoryStore
from lab_v4_dev.memory.db import Database


def test_memory_store_owns_components():
    db = Database()
    db.connect()

    memory = MemoryStore(db)

    assert memory.db is db
    assert memory.session.db is db
    assert memory.tasks.db is db
    assert memory.lessons.db is db

    db.close()


def test_agent_exposes_memory_owner():
    from lab_v4_dev.core.agent import Agent

    agent = Agent()
    assert agent.boot() is True

    assert agent.memory is not None
    assert agent.memory.db is agent.db
    assert agent.memory.session is agent.session

    agent.shutdown()
