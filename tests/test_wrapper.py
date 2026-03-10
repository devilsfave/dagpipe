import sys
from unittest.mock import MagicMock, patch
sys.modules['groq'] = MagicMock()

import json
import io
import os
from pathlib import Path
import importlib.util

def test_wrapper_main_outputs_dynamic_zip_filename():
    """Verify that wrapper.py correctly extracts and outputs the dynamic zip_filename."""
    # Load wrapper.py as a module dynamically since directory has a hyphen
    wrapper_path = Path("actors/pipeline-generator/src/wrapper.py").resolve()
    spec = importlib.util.spec_from_file_location("wrapper", str(wrapper_path))
    wrapper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wrapper)

    fake_input = json.dumps({
        "description": "I want a pipeline that takes a topic, researches it, writes a short summary",
        "groq_api_key": "mock_groq_key"
    })

    fake_stdin = io.StringIO(fake_input)
    fake_stdout = io.StringIO()

    with patch("sys.stdin", fake_stdin), \
         patch("sys.stdout", fake_stdout), \
         patch("sys.exit") as mock_exit:
        
        with patch.object(wrapper, "Groq", MagicMock()):
            # Mock run_generator to simulate a successful generation with a dynamic name
            with patch.object(wrapper, "run_generator") as mock_run_gen:
                mock_run_gen.return_value = {
                    "packager": {
                        "zip_path": "/tmp/out/pipeline_generated.zip",
                        "files_included": ["runner.py", "pipeline.yaml", "README.md"],
                        "zip_filename": "research_topic_pipeline.zip"
                    }
                }
                try:
                    wrapper.main()
                except SystemExit:
                    pass

    output = fake_stdout.getvalue().strip()
    parsed = json.loads(output)
    
    assert parsed.get("status") == "success"
    assert parsed.get("zip_filename") == "research_topic_pipeline.zip"
