import json
import logging
import uuid
import datetime
import threading
import httpx
from pathlib import Path
from typing import List, Dict

from PySide6.QtCore import QObject, Signal

from config_manager import get_user_data_dir

logger = logging.getLogger(__name__)

class MemoryStore(QObject):
    facts_updated = Signal()

    def __init__(self, config: dict) -> None:
        super().__init__()
        self._config = config
        self._memory_dir = get_user_data_dir() / "memories"
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, dict] = {}
        self._cache_time = 0.0

    def extract_facts_async(self, conversation_text: str) -> None:
        if not self._config.get("memory_enabled", True):
            return

        def worker():
            model = self._config.get("memory_model", "qwen2.5-coder:7b")
            base_url = self._config.get("ollama_base_url", "http://localhost:11434")
            
            system_prompt = (
                "Extract 0-3 factual memories from this conversation. "
                "Return JSON array: [{\"category\": \"preference | fact | person | location | task\", \"content\": \"...\", \"keywords\": [\"...\"]}]. "
                "Only extract durable facts. Return [] if nothing worth remembering."
            )
            
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": conversation_text}
                ],
                "format": "json",
                "stream": False,
                "options": {
                    "num_predict": 200
                }
            }
            
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(f"{base_url}/api/chat", json=payload)
                    resp.raise_for_status()
                    
                data = resp.json()
                content = data.get("message", {}).get("content", "[]")
                facts = json.loads(content)
                
                if not isinstance(facts, list):
                    facts = []
                    
                new_facts = 0
                for f in facts:
                    if not isinstance(f, dict): continue
                    if "content" not in f or "keywords" not in f: continue
                    
                    fact_id = str(uuid.uuid4())
                    doc = {
                        "id": fact_id,
                        "category": f.get("category", "fact"),
                        "content": f["content"],
                        "keywords": [str(k).lower() for k in f["keywords"]],
                        "extracted_at": int(datetime.datetime.now().timestamp()),
                        "source_session": datetime.datetime.now().strftime("%Y-%m-%d")
                    }
                    
                    path = self._memory_dir / f"{fact_id}.json"
                    path.write_text(json.dumps(doc, indent=2), "utf-8")
                    new_facts += 1
                
                if new_facts > 0:
                    self.invalidate_cache()
                    # Cannot emit signal directly from different thread safely without QTimer or similar,
                    # Wait, PySide6 signals are thread-safe if connected via QueuedConnection (default across threads).
                    self.facts_updated.emit()
                    
            except Exception as e:
                logger.error(f"Memory extraction failed: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def _load_all_facts(self) -> List[dict]:
        # Simple caching mechanism
        current_time = datetime.datetime.now().timestamp()
        if current_time - self._cache_time < 30 and self._cache:
            return list(self._cache.values())
            
        facts = []
        for p in self._memory_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text("utf-8"))
                facts.append(data)
                self._cache[data["id"]] = data
            except Exception:
                pass
        self._cache_time = current_time
        return facts

    def retrieve_relevant(self, query: str, max_results: int = 5) -> List[dict]:
        facts = self._load_all_facts()
        if not facts:
            return []
            
        query_tokens = set(query.lower().replace(".", "").replace("?", "").replace(",", "").split())
        if not query_tokens:
            return []
            
        scored_facts = []
        now = int(datetime.datetime.now().timestamp())
        
        for f in facts:
            keywords = set(f.get("keywords", []))
            overlap = len(query_tokens.intersection(keywords))
            
            # keyword_overlap * 0.7
            score = overlap * 0.7
            
            # recency_score * 0.2
            extracted_at = f.get("extracted_at", now)
            days_since = max(0, (now - extracted_at) / 86400)
            recency = 1.0 / (1.0 + days_since)
            score += recency * 0.2
            
            # category_boost * 0.1
            cat = f.get("category", "")
            cat_boost = 0.0
            if cat == "person": cat_boost = 0.15
            elif cat == "preference": cat_boost = 0.10
            elif cat == "task": cat_boost = 0.05
            
            score += cat_boost * 0.1
            
            if score > 0:
                scored_facts.append((score, f))
                
        scored_facts.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored_facts[:max_results]]

    def build_memory_prompt(self, query: str) -> str:
        if not self._config.get("memory_enabled", True):
            return ""
            
        relevant = self.retrieve_relevant(query)
        if not relevant:
            return ""
            
        lines = []
        for f in relevant:
            lines.append(f"- {f.get('content')}")
            
        return "\n".join(lines)

    def invalidate_cache(self) -> None:
        self._cache.clear()
        self._cache_time = 0.0
