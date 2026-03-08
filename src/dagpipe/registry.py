"""DagPipe ModelRegistry — Self-healing model availability and pricing.

Checks provider APIs for currently available models.
Warns when configured models are retired.
Pulls current pricing from LiteLLM's community-maintained JSON.
Never blocks pipeline execution — all validation is advisory.

Zero external dependencies — stdlib only (urllib.request, json, pathlib).
"""
from __future__ import annotations

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

# ─────────────────────────────────────────────────────────────────────────────
# HARDCODED FALLBACK — used when offline or before first cache refresh
# Update these when you manually notice something is wrong, but the registry
# will auto-correct from the live APIs regardless.
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_MODELS = {
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "meta-llama/llama-4-scout-17b-16e-instruct",
    ],
    "gemini": [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-5",
    ],
}

_FALLBACK_PRICING = {
    "llama-3.3-70b-versatile": {"input_per_1k": 0.00059, "output_per_1k": 0.00079},
    "llama-3.1-8b-instant": {"input_per_1k": 0.00005, "output_per_1k": 0.00008},
    "gemini-2.5-flash": {"input_per_1k": 0.0, "output_per_1k": 0.0},
    "gemini-2.5-flash-lite": {"input_per_1k": 0.0, "output_per_1k": 0.0},
    "gpt-4o": {"input_per_1k": 0.0025, "output_per_1k": 0.01},
    "gpt-4o-mini": {"input_per_1k": 0.00015, "output_per_1k": 0.0006},
}

# LiteLLM's community-maintained pricing file — updated within hours of provider changes
_LITELLM_PRICING_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)

_GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"

_DEFAULT_CACHE_TTL_HOURS = 24
_REQUEST_TIMEOUT_SECONDS = 5  # Never block pipeline for more than 5s


class ModelRegistry:
    """Self-healing model availability and pricing registry.

    Usage:
        # Attach to PipelineOrchestrator for automatic validation
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry=registry,
            model_registry=ModelRegistry(groq_api_key="sk-..."),
        )

        # Standalone validation before running
        reg = ModelRegistry(groq_api_key="sk-...")
        reg.validate_model("llama-3.1-8b-instant", provider="groq")

        # Get current pricing for cost tracking
        price = reg.get_pricing("llama-3.3-70b-versatile")
    """

    def __init__(
        self,
        groq_api_key: str | None = None,
        cache_dir: Path = Path(".dagpipe"),
        ttl_hours: int = _DEFAULT_CACHE_TTL_HOURS,
        strict: bool = False,  # If True, raise on retired model. Default: warn only.
        auto_refresh: bool = True,
    ) -> None:
        self._groq_key = groq_api_key
        self._cache_path = cache_dir / "model_registry.json"
        self._ttl_hours = ttl_hours
        self._strict = strict
        self._auto_refresh = auto_refresh
        self._cache: dict = self._load_cache()

        if auto_refresh and self._is_cache_stale():
            self._refresh_in_background()

    # ── Public API ──────────────────────────────────────────────────────────

    def validate_model(
        self,
        model_id: str,
        provider: str | None = None,
    ) -> str:
        """Check if a model is available. Returns model_id if valid.

        If the model is not found in the live list:
        - In strict=False mode (default): emits a warning, returns model_id anyway
          (lets the pipeline run — the API call will fail with a clear error)
        - In strict=True mode: raises ModelRetiredError with suggested alternatives

        Args:
            model_id: The model string to validate (e.g. "llama-3.1-8b-instant")
            provider: Optional provider name ("groq", "gemini", "openai")
                      If None, searches all providers.

        Returns:
            The model_id (same as input if valid, or best alternative if strict=False)
        """
        if provider is None:
            provider = self._detect_provider(model_id)

        available = self._get_available_models(provider)

        if model_id in available:
            return model_id

        # Model not found
        alternatives = self._find_alternatives(model_id, available, provider)
        alt_str = ", ".join(f'"{a}"' for a in alternatives[:3]) if alternatives else "none found"

        message = (
            f"DagPipe ModelRegistry: Model '{model_id}' is not in the current "
            f"list of available {provider} models. It may have been retired.\n"
            f"Available alternatives: {alt_str}\n"
            f"To update: set model_id to one of the alternatives above.\n"
            f"Registry last updated: {self._cache.get('last_updated', 'never')}"
        )

        if self._strict:
            raise ModelRetiredError(message)
        else:
            warnings.warn(message, ModelRetiredWarning, stacklevel=3)
            # Return first alternative if available, otherwise return original
            # (let the API give the real error rather than blocking silently)
            return alternatives[0] if alternatives else model_id

    def get_pricing(self, model_id: str) -> dict:
        """Get current pricing for a model.

        Returns dict with input_per_1k and output_per_1k in USD.
        Falls back to hardcoded values if model not in cache.

        Example:
            pricing = registry.get_pricing("llama-3.3-70b-versatile")
            cost = (tokens / 1000) * pricing["input_per_1k"]
        """
        pricing = self._cache.get("pricing", {})
        if model_id in pricing:
            return pricing[model_id]
        # Try fallback
        if model_id in _FALLBACK_PRICING:
            return _FALLBACK_PRICING[model_id]
        return {"input_per_1k": 0.0, "output_per_1k": 0.0}

    def get_available_models(self, provider: str) -> list[str]:
        """Return currently available models for a provider."""
        return self._get_available_models(provider)

    def force_refresh(self) -> dict:
        """Force a synchronous refresh from all provider APIs.

        Returns summary of what was updated.
        Call this manually when you know a provider just made changes.

        Example:
            from dagpipe.registry import ModelRegistry
            reg = ModelRegistry(groq_api_key="sk-...")
            summary = reg.force_refresh()
            print(summary)
        """
        return self._refresh_sync()

    # ── Cache management ────────────────────────────────────────────────────

    def _load_cache(self) -> dict:
        if not self._cache_path.exists():
            return {}
        try:
            return json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_cache(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps(self._cache, indent=2), encoding="utf-8"
        )

    def _is_cache_stale(self) -> bool:
        last = self._cache.get("last_updated")
        if not last:
            return True
        try:
            updated_at = datetime.fromisoformat(last)
            age_hours = (datetime.now(timezone.utc) - updated_at).total_seconds() / 3600
            return age_hours > self._ttl_hours
        except (ValueError, TypeError):
            return True

    # ── Refresh logic ───────────────────────────────────────────────────────

    def _refresh_in_background(self) -> None:
        """Non-blocking refresh — uses threading so pipeline never waits."""
        import threading
        t = threading.Thread(target=self._refresh_sync, daemon=True)
        t.start()

    def _refresh_sync(self) -> dict:
        """Synchronous refresh from all provider APIs. Returns summary."""
        summary = {"updated": [], "failed": [], "timestamp": datetime.now(timezone.utc).isoformat()}

        # Refresh Groq models
        if self._groq_key:
            try:
                groq_models = self._fetch_groq_models()
                if groq_models:
                    if "providers" not in self._cache:
                        self._cache["providers"] = {}
                    self._cache["providers"]["groq"] = {
                        "last_checked": summary["timestamp"],
                        "available_models": groq_models,
                    }
                    summary["updated"].append(f"groq: {len(groq_models)} models")
            except Exception as e:
                summary["failed"].append(f"groq: {e}")

        # Refresh pricing from LiteLLM
        try:
            pricing = self._fetch_litellm_pricing()
            if pricing:
                self._cache["pricing"] = pricing
                summary["updated"].append(f"pricing: {len(pricing)} models")
        except Exception as e:
            summary["failed"].append(f"pricing: {e}")

        self._cache["last_updated"] = summary["timestamp"]
        self._save_cache()
        return summary

    def _fetch_groq_models(self) -> list[str]:
        """Fetch currently available Groq models from live API."""
        req = Request(
            _GROQ_MODELS_URL,
            headers={"Authorization": f"Bearer {self._groq_key}"},
        )
        with urlopen(req, timeout=_REQUEST_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode())
        return [m["id"] for m in data.get("data", [])]

    def _fetch_litellm_pricing(self) -> dict:
        """Fetch pricing from LiteLLM's community-maintained JSON."""
        with urlopen(_LITELLM_PRICING_URL, timeout=_REQUEST_TIMEOUT_SECONDS) as resp:
            raw = json.loads(resp.read().decode())

        # Extract only the fields DagPipe needs
        simplified = {}
        for model_id, data in raw.items():
            if isinstance(data, dict):
                input_cost = data.get("input_cost_per_token", 0.0)
                output_cost = data.get("output_cost_per_token", 0.0)
                if input_cost is not None or output_cost is not None:
                    simplified[model_id] = {
                        "input_per_1k": (input_cost or 0.0) * 1000,
                        "output_per_1k": (output_cost or 0.0) * 1000,
                    }
        return simplified

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _get_available_models(self, provider: str) -> list[str]:
        """Get available models from cache, falling back to hardcoded list."""
        providers = self._cache.get("providers", {})
        if provider in providers:
            return providers[provider].get("available_models", [])
        return _FALLBACK_MODELS.get(provider, [])

    def _detect_provider(self, model_id: str) -> str:
        """Infer provider from model string."""
        if "gemini" in model_id.lower():
            return "gemini"
        if "gpt" in model_id.lower() or model_id.startswith("o1") or model_id.startswith("o3"):
            return "openai"
        if "claude" in model_id.lower():
            return "anthropic"
        if model_id.startswith("ollama") or "/" not in model_id and "llama" in model_id.lower():
            return "groq"  # Most Llama models on DagPipe are Groq
        return "groq"  # Default assumption

    def _find_alternatives(
        self,
        retired_model: str,
        available: list[str],
        provider: str,
    ) -> list[str]:
        """Find best available alternatives for a retired model.

        Heuristic: match by size class
        e.g. "llama-3.1-8b-instant" retired → prefer other 8b-class models
        e.g. "llama-3.3-70b-versatile" retired → prefer other 70b-class models
        """
        if not available:
            return []

        # Extract size hint from retired model name
        size_hint = None
        for size in ["8b", "70b", "7b", "13b", "34b", "scout", "maverick", "flash", "pro"]:
            if size in retired_model.lower():
                size_hint = size
                break

        if size_hint:
            # Prefer models matching the same size class
            matches = [m for m in available if size_hint in m.lower()]
            if matches:
                return matches

        # Fall back: return all available models sorted by name
        return sorted(available)


# ─────────────────────────────────────────────────────────────────────────────
# EXCEPTIONS
# ─────────────────────────────────────────────────────────────────────────────

class ModelRetiredError(RuntimeError):
    """Raised in strict mode when a configured model is not available."""


class ModelRetiredWarning(UserWarning):
    """Warning emitted when a configured model may have been retired."""
