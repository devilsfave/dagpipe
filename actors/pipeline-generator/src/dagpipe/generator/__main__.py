"""DagPipe Generator — CLI Entry Point

Usage:
    python -m dagpipe.generator \
        --request "I want to scrape job listings and summarize them daily" \
        --output ./my_pipeline.zip
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Any

from groq import Groq

from .pipeline_generator import run_generator


def _make_groq_caller(client: Groq, model: str) -> Any:
    """Create a callable that sends messages to a Groq model.

    Args:
        client: Initialized Groq client.
        model: Model name (e.g. 'llama-3.1-8b-instant').

    Returns:
        Callable that takes messages and returns response text.
    """
    def call(messages: list[dict[str, str]], **kwargs: Any) -> str:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=4096,
        )
        return response.choices[0].message.content  # type: ignore[union-attr]
    return call


def main() -> None:
    """Parse CLI args and run the generator pipeline."""
    parser = argparse.ArgumentParser(
        prog="dagpipe.generator",
        description="Generate a DagPipe pipeline template from a plain English description.",
    )
    parser.add_argument(
        "--request",
        required=True,
        help="Plain English description of the pipeline you want to build.",
    )
    parser.add_argument(
        "--output",
        default="./pipeline.zip",
        help="Output path for the generated zip file (default: ./pipeline.zip).",
    )
    args = parser.parse_args()

    # Read API key from environment — never hardcoded
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("ERROR: Set the GROQ_API_KEY environment variable first.")
        print("  export GROQ_API_KEY='gsk_...'")
        sys.exit(1)

    client = Groq(api_key=api_key)

    # Use Llama 3.3 70B for generation tasks (needs high quality)
    llm_fn = _make_groq_caller(client, "llama-3.3-70b-versatile")

    print(f"\n{'='*60}")
    print(f"  DagPipe Template Generator")
    print(f"  Request: {args.request[:80]}...")
    print(f"{'='*60}\n")

    result = run_generator(
        request=args.request,
        llm_call_fn=llm_fn,
        output_path=Path(args.output),
    )

    package = result.get("packager", {})
    print(f"\n{'='*60}")
    print(f"  Generation Complete!")
    print(f"  Output: {package.get('zip_path', 'N/A')}")
    print(f"  Files: {', '.join(package.get('files_included', []))}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
