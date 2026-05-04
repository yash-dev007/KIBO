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


# ── Phase 2: Memory Transparency API tests ──────────────────────────────────


def _make_store(tmp_path, monkeypatch, extra_config=None):
    config = {"memory_enabled": True, "memory_provider": "lexical"}
    if extra_config:
        config.update(extra_config)
    monkeypatch.setattr("src.ai.memory_store.get_user_data_dir", lambda: tmp_path)
    return MemoryStore(config)


def test_list_facts_returns_all_memories(tmp_path, monkeypatch):
    store = _make_store(tmp_path, monkeypatch)
    store.add_fact_inline({"category": "preference", "content": "User likes vim.", "keywords": ["vim"]})
    store.add_fact_inline({"category": "fact", "content": "KIBO runs on Windows.", "keywords": ["windows"]})

    facts = store.list_facts()
    assert len(facts) == 2
    contents = {f["content"] for f in facts}
    assert "User likes vim." in contents
    assert "KIBO runs on Windows." in contents


def test_list_facts_empty_when_no_memories(tmp_path, monkeypatch):
    store = _make_store(tmp_path, monkeypatch)
    assert store.list_facts() == []


def test_get_vault_path_returns_vault_dir(tmp_path, monkeypatch):
    store = _make_store(tmp_path, monkeypatch)
    vault_path = store.get_vault_path()
    assert vault_path == tmp_path / "vault"


def test_delete_fact_removes_disk_file(tmp_path, monkeypatch):
    store = _make_store(tmp_path, monkeypatch)
    store.add_fact_inline({"category": "preference", "content": "User likes Rust.", "keywords": ["rust"]})

    facts = store.list_facts()
    assert len(facts) == 1
    fact_id = facts[0]["id"]

    result = store.delete_fact(fact_id)
    assert result is True
    assert store.list_facts() == []


def test_delete_fact_removes_from_provider_index(tmp_path, monkeypatch):
    store = _make_store(tmp_path, monkeypatch)
    store.add_fact_inline({"category": "preference", "content": "User drinks coffee.", "keywords": ["coffee"]})

    facts = store.list_facts()
    fact_id = facts[0]["id"]

    store.delete_fact(fact_id)
    assert store.retrieve_relevant("coffee") == []


def test_delete_fact_returns_false_for_unknown_id(tmp_path, monkeypatch):
    store = _make_store(tmp_path, monkeypatch)
    assert store.delete_fact("nonexistent_id") is False


def test_update_fact_changes_disk_content(tmp_path, monkeypatch):
    store = _make_store(tmp_path, monkeypatch)
    store.add_fact_inline({"category": "preference", "content": "User likes Python.", "keywords": ["python"]})

    facts = store.list_facts()
    fact_id = facts[0]["id"]

    result = store.update_fact(fact_id, {"content": "User loves Python and asyncio."})
    assert result is True

    updated = store.list_facts()
    assert updated[0]["content"] == "User loves Python and asyncio."


def test_update_fact_changes_provider_retrieval(tmp_path, monkeypatch):
    store = _make_store(tmp_path, monkeypatch)
    store.add_fact_inline({"category": "preference", "content": "User likes Go.", "keywords": ["go"]})

    facts = store.list_facts()
    fact_id = facts[0]["id"]

    store.update_fact(fact_id, {"content": "User loves Go and goroutines.", "keywords": ["go", "goroutines"]})

    results = store.retrieve_relevant("goroutines")
    assert len(results) == 1
    assert results[0]["content"] == "User loves Go and goroutines."


def test_update_fact_changes_category(tmp_path, monkeypatch):
    store = _make_store(tmp_path, monkeypatch)
    store.add_fact_inline({"category": "fact", "content": "User birthday is May.", "keywords": ["birthday"]})

    facts = store.list_facts()
    fact_id = facts[0]["id"]

    store.update_fact(fact_id, {"category": "person"})

    updated = store.list_facts()
    assert updated[0]["category"] == "person"


def test_update_fact_returns_false_for_unknown_id(tmp_path, monkeypatch):
    store = _make_store(tmp_path, monkeypatch)
    assert store.update_fact("nonexistent_id", {"content": "x"}) is False


def test_rebuild_index_repopulates_from_markdown(tmp_path, monkeypatch):
    store = _make_store(tmp_path, monkeypatch)
    store.add_fact_inline({"category": "preference", "content": "User likes TypeScript.", "keywords": ["typescript"]})

    # Trigger migration so _migration_done is set, then wipe the provider
    assert len(store.retrieve_relevant("typescript")) == 1
    store._provider.clear()
    store._migration_done.set()  # keep it set so auto-migration won't re-run on next retrieve
    assert store.retrieve_relevant("typescript") == []

    store.rebuild_index()

    results = store.retrieve_relevant("typescript")
    assert len(results) == 1
    assert results[0]["content"] == "User likes TypeScript."
