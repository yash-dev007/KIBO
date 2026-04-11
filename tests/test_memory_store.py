import pytest
import datetime
from pathlib import Path
from memory_store import MemoryStore

def test_retrieve_relevant(tmp_path, monkeypatch):
    # Mock config
    config = {
        "memory_enabled": True,
        "memory_model": "test",
        "ollama_base_url": "http://localhost:11434"
    }

    # Patch user data dir
    def mock_get_user_data_dir():
        return tmp_path

    monkeypatch.setattr("memory_store.get_user_data_dir", mock_get_user_data_dir)

    store = MemoryStore(config)
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)

    # Write a test memory
    now = int(datetime.datetime.now().timestamp())
    test_fact = {
        "id": "123",
        "category": "preference",
        "content": "User likes dark mode.",
        "keywords": ["dark", "mode", "like"],
        "extracted_at": now,
        "source_session": "2026-04-11"
    }
    
    with open(memories_dir / "123.json", "w", encoding="utf-8") as f:
        import json
        json.dump(test_fact, f)

    results = store.retrieve_relevant("I like dark mode")
    assert len(results) == 1
    assert results[0]["content"] == "User likes dark mode."

def test_build_memory_prompt(tmp_path, monkeypatch):
    config = {"memory_enabled": True}
    monkeypatch.setattr("memory_store.get_user_data_dir", lambda: tmp_path)
    store = MemoryStore(config)
    
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)
    
    now = int(datetime.datetime.now().timestamp())
    test_fact = {
        "id": "456",
        "category": "fact",
        "content": "KIBO is awesome.",
        "keywords": ["kibo", "awesome"],
        "extracted_at": now,
        "source_session": "2026-04-11"
    }
    import json
    (memories_dir / "456.json").write_text(json.dumps(test_fact), "utf-8")

    prompt = store.build_memory_prompt("Is KIBO awesome?")
    assert "- KIBO is awesome." in prompt
