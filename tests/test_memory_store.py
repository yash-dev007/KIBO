import datetime

from src.ai.memory_store import MemoryStore


def _write_memory(path, fact: dict) -> None:
    content = (
        "---\n"
        f"id: {fact['id']}\n"
        f"category: {fact['category']}\n"
        f"keywords: [{', '.join(fact['keywords'])}]\n"
        f"extracted_at: {fact['extracted_at']}\n"
        f"source_session: {fact['source_session']}\n"
        "---\n\n"
        f"{fact['content']}\n"
    )
    path.write_text(content, "utf-8")


def test_retrieve_relevant(tmp_path, monkeypatch):
    config = {
        "memory_enabled": True,
        "memory_model": "test",
        "ollama_base_url": "http://localhost:11434",
    }

    monkeypatch.setattr("src.ai.memory_store.get_user_data_dir", lambda: tmp_path)

    store = MemoryStore(config)

    now = int(datetime.datetime.now().timestamp())
    test_fact = {
        "id": "123",
        "category": "preference",
        "content": "User likes dark mode.",
        "keywords": ["dark", "mode", "like"],
        "extracted_at": now,
        "source_session": "2026-04-11",
    }

    _write_memory(store._memory_dir / "123_preference.md", test_fact)

    results = store.retrieve_relevant("I like dark mode")
    assert len(results) == 1
    assert results[0]["content"] == "User likes dark mode."


def test_build_memory_prompt(tmp_path, monkeypatch):
    config = {"memory_enabled": True}
    monkeypatch.setattr("src.ai.memory_store.get_user_data_dir", lambda: tmp_path)
    store = MemoryStore(config)

    now = int(datetime.datetime.now().timestamp())
    test_fact = {
        "id": "456",
        "category": "fact",
        "content": "KIBO is awesome.",
        "keywords": ["kibo", "awesome"],
        "extracted_at": now,
        "source_session": "2026-04-11",
    }

    _write_memory(store._memory_dir / "456_fact.md", test_fact)

    prompt = store.build_memory_prompt("Is KIBO awesome?")
    assert "- KIBO is awesome." in prompt


def test_clear_all_facts_clears_retrieval_index(tmp_path, monkeypatch):
    config = {"memory_enabled": True, "memory_provider": "lexical"}
    monkeypatch.setattr("src.ai.memory_store.get_user_data_dir", lambda: tmp_path)
    store = MemoryStore(config)

    store.add_fact_inline({
        "category": "preference",
        "content": "User likes espresso.",
        "keywords": ["espresso"],
    })
    assert len(store.retrieve_relevant("espresso")) == 1

    store.clear_all_facts()

    assert store.retrieve_relevant("espresso") == []


def test_memory_cap_evicts_retrieval_index(tmp_path, monkeypatch):
    config = {
        "memory_enabled": True,
        "memory_provider": "lexical",
        "memory_max_facts": 1,
    }
    monkeypatch.setattr("src.ai.memory_store.get_user_data_dir", lambda: tmp_path)
    store = MemoryStore(config)

    store.add_fact_inline({
        "category": "preference",
        "content": "User likes espresso.",
        "keywords": ["espresso"],
    })
    store.add_fact_inline({
        "category": "preference",
        "content": "User likes green tea.",
        "keywords": ["tea"],
    })

    assert store.retrieve_relevant("espresso") == []
    assert len(store.retrieve_relevant("tea")) == 1
