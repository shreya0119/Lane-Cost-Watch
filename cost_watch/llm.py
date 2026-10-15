"""Talks to a local Ollama model, with a cache keyed on the exact request so reruns replay instead of re-paying."""
import hashlib
import json
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5-coder:7b"
OPTIONS = {"temperature": 0, "seed": 42}


class LLMUnavailable(RuntimeError):
    pass


class CachedLLM:
    def __init__(self, cache_path, live=False):
        self.cache_path = Path(cache_path)
        self.live = live
        self.cache = json.loads(self.cache_path.read_text()) if self.cache_path.exists() else {}
        self.stats = {"calls": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0}

    def ask_json(self, system, user):
        request = {"model": MODEL, "options": OPTIONS, "format": "json", "stream": False,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        key = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()

        if key in self.cache and not self.live:
            self.stats["cache_hits"] += 1
            entry = self.cache[key]
        else:
            entry = self._call(request)
            self.cache[key] = entry
            self.stats["calls"] += 1
            self.stats["input_tokens"] += entry["input_tokens"]
            self.stats["output_tokens"] += entry["output_tokens"]
        return json.loads(entry["content"])

    def _call(self, request):
        try:
            req = urllib.request.Request(OLLAMA_URL, data=json.dumps(request).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = json.loads(resp.read())
        except OSError as err:
            raise LLMUnavailable(
                f"Needed a fresh LLM answer but Ollama is not reachable ({err}). "
                f"Install Ollama and run `ollama pull {MODEL}`."
            ) from err
        return {"content": body["message"]["content"],
                "input_tokens": body.get("prompt_eval_count", 0),
                "output_tokens": body.get("eval_count", 0)}

    def save(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, indent=2, sort_keys=True))
