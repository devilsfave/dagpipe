"""Tests for dagpipe.registry — ModelRegistry."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.error import URLError

import pytest

from dagpipe.registry import ModelRegistry, ModelRetiredError, ModelRetiredWarning, _FALLBACK_PRICING

@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    return tmp_path

def test_fallback_when_offline(temp_cache_dir: Path) -> None:
    """Test fallback to hardcoded list when API call fails."""
    # Mock urlopen to fail
    with patch("dagpipe.registry.urlopen", side_effect=URLError("Network unreachable")):
        reg = ModelRegistry(groq_api_key="sk-test", cache_dir=temp_cache_dir, auto_refresh=True)
        # Should not raise exception
        models = reg.get_available_models("groq")
        assert "llama-3.1-8b-instant" in models

def test_model_validation_success(temp_cache_dir: Path) -> None:
    """Validate model returns model_id when available."""
    # We don't even need to mock if it's in the fallback list, but let's mock it
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "data": [{"id": "llama-test-model"}, {"id": "llama-3.1-8b-instant"}]
    }).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    
    with patch("dagpipe.registry.urlopen", return_value=mock_response):
        reg = ModelRegistry(groq_api_key="sk-test", cache_dir=temp_cache_dir)
        reg.force_refresh()
        assert reg.validate_model("llama-test-model") == "llama-test-model"

def test_strict_mode_raises_on_retired(temp_cache_dir: Path) -> None:
    """Strict mode raises ModelRetiredError for missing model."""
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"data": [{"id": "only-one-model"}]}).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    
    with patch("dagpipe.registry.urlopen", return_value=mock_response):
        reg = ModelRegistry(groq_api_key="sk-test", cache_dir=temp_cache_dir, strict=True)
        reg.force_refresh()
        with pytest.raises(ModelRetiredError, match="not in the current list"):
            reg.validate_model("retired-model", provider="groq")

def test_warning_mode_returns_alternative(temp_cache_dir: Path) -> None:
    """Non-strict mode emits warning and returns best alternative."""
    mock_response = MagicMock()
    # Provide an alternative that matches the size hint '8b'
    mock_response.read.return_value = json.dumps({
        "data": [{"id": "llama-3.2-8b-new"}, {"id": "llama-huge-70b"}]
    }).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    
    with patch("dagpipe.registry.urlopen", return_value=mock_response):
        reg = ModelRegistry(groq_api_key="sk-test", cache_dir=temp_cache_dir, strict=False)
        reg.force_refresh()
        
        with pytest.warns(ModelRetiredWarning, match="Available alternatives: \"llama-3.2-8b-new\""):
            alt = reg.validate_model("llama-3.1-8b-old-retired")
            assert alt == "llama-3.2-8b-new" # Picked the matching 8b!

def test_pricing_litellm_mock(temp_cache_dir: Path) -> None:
    """Test parsing pricing from LiteLLM json mock."""
    mock_pricing = {
        "future-model-1": {
            "input_cost_per_token": 0.000001,
            "output_cost_per_token": 0.000002
        }
    }
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_pricing).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    
    with patch("dagpipe.registry.urlopen", return_value=mock_response):
        reg = ModelRegistry(cache_dir=temp_cache_dir, auto_refresh=False)
        reg._cache["pricing"] = reg._fetch_litellm_pricing()
        
        pricing = reg.get_pricing("future-model-1")
        assert pricing["input_per_1k"] == pytest.approx(0.001)
        assert pricing["output_per_1k"] == pytest.approx(0.002)

def test_pricing_fallback(temp_cache_dir: Path) -> None:
    """Test fallback pricing when cache empty."""
    reg = ModelRegistry(cache_dir=temp_cache_dir, auto_refresh=False)
    # Should pull from _FALLBACK_PRICING
    pricing = reg.get_pricing("gemini-2.5-flash")
    assert pricing["input_per_1k"] == _FALLBACK_PRICING["gemini-2.5-flash"]["input_per_1k"]

def test_cache_ttl_logic(temp_cache_dir: Path) -> None:
    """Test _is_cache_stale honors ttl_hours."""
    reg = ModelRegistry(cache_dir=temp_cache_dir, ttl_hours=24, auto_refresh=False)
    
    # 1. No last_updated -> stale
    assert reg._is_cache_stale() is True
    
    # 2. Updated recently -> not stale
    reg._cache["last_updated"] = datetime.now(timezone.utc).isoformat()
    assert reg._is_cache_stale() is False
    
    # 3. Updated 25 hours ago -> stale
    old_time = datetime.now(timezone.utc) - timedelta(hours=25)
    reg._cache["last_updated"] = old_time.isoformat()
    assert reg._is_cache_stale() is True
