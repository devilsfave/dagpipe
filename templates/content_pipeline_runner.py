"""Content Pipeline Runner — DagPipe Template

A complete working example that runs the content-pipeline.yaml DAG
using Groq LLMs via DagPipe's orchestrator.

Usage:
    export GROQ_API_KEY="gsk_..."          # Linux/Mac
    set GROQ_API_KEY=gsk_...               # Windows CMD
    $env:GROQ_API_KEY = "gsk_..."          # Windows PowerShell
    python templates/content_pipeline_runner.py
"""
import os
import sys
from pathlib import Path
from typing import Any

from groq import Groq  # pip install groq

from dagpipe.dag import load_dag, PipelineOrchestrator
from dagpipe.router import ModelRouter


# ─────────────────────────────────────────────────────────────────────────────
# GROQ CLIENT SETUP
# ─────────────────────────────────────────────────────────────────────────────

# Read API key from environment — never hardcode credentials
api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    print("ERROR: Set the GROQ_API_KEY environment variable first.")
    print("  export GROQ_API_KEY='gsk_...'")
    sys.exit(1)

client = Groq(api_key=api_key)


# ─────────────────────────────────────────────────────────────────────────────
# LLM CALLABLE WRAPPERS
# ─────────────────────────────────────────────────────────────────────────────
# Each wrapper takes a list of messages and returns the response text.
# These are the callables that ModelRouter selects between.

def call_groq_8b(messages: list[dict[str, str]], **kwargs: Any) -> str:
    """Call Groq Llama 3.1 8B — fast, low-cost, good for simple tasks."""
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        temperature=0.7,
        max_tokens=2048,
    )
    return response.choices[0].message.content  # type: ignore[union-attr]


def call_groq_70b(messages: list[dict[str, str]], **kwargs: Any) -> str:
    """Call Groq Llama 3.3 70B — slower but higher quality for complex tasks."""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.7,
        max_tokens=4096,
    )
    return response.choices[0].message.content  # type: ignore[union-attr]


# ─────────────────────────────────────────────────────────────────────────────
# NODE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────
# Every node function has the same signature:
#   def node_fn(context: dict[str, Any], model: Any = None) -> dict[str, Any]
#
# - context: contains upstream node outputs (keyed by node ID) + initial_state
# - model: the LLM callable selected by ModelRouter (None for deterministic)

def research(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
    """Gather facts and sources on the topic.

    Reads the 'topic' key from context (injected via initial_state).
    Calls the LLM to produce structured research notes.
    """
    topic = context.get("topic", "artificial intelligence trends")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a research assistant. Gather key facts, statistics, "
                "recent developments, and credible sources on the given topic. "
                "Output structured research notes with numbered points."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Research the following topic thoroughly:\n\n{topic}\n\n"
                "Provide 5-8 key findings with sources where possible."
            ),
        },
    ]

    # model is the LLM callable selected by the router
    result = model(messages) if model else "No model available"
    return {"topic": topic, "findings": result}


def outline(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
    """Create a structured article outline from research findings.

    Reads the 'research' node output from context.
    """
    research_data = context.get("research", {})
    findings = research_data.get("findings", "No findings available")
    topic = research_data.get("topic", "Unknown topic")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a content strategist. Create a detailed article outline "
                "with clear sections, sub-points, and flow. The outline should be "
                "ready for a writer to expand into a full draft."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Create an article outline for: {topic}\n\n"
                f"Based on these research findings:\n{findings}\n\n"
                "Include: intro hook, 3-5 main sections, conclusion, "
                "and suggested word count per section."
            ),
        },
    ]

    result = model(messages) if model else "No model available"
    return {"topic": topic, "structure": result}


def draft(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
    """Write a complete first draft based on the outline.

    This is the most complex node — uses the high-complexity model.
    Reads the 'outline' node output from context.
    """
    outline_data = context.get("outline", {})
    structure = outline_data.get("structure", "No outline available")
    topic = outline_data.get("topic", "Unknown topic")

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert content writer. Write a complete, engaging "
                "article based on the provided outline. Use clear language, "
                "include relevant examples, and maintain a professional but "
                "approachable tone. Target 800-1200 words."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Write a full article draft on: {topic}\n\n"
                f"Follow this outline:\n{structure}\n\n"
                "Make it informative, engaging, and well-structured."
            ),
        },
    ]

    result = model(messages) if model else "No model available"
    return {"topic": topic, "content": result}


def edit(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
    """Review and polish the draft for clarity, grammar, and accuracy.

    Reads the 'draft' node output from context.
    """
    draft_data = context.get("draft", {})
    content = draft_data.get("content", "No draft available")
    topic = draft_data.get("topic", "Unknown topic")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a senior editor. Review the article for:\n"
                "1. Grammar and spelling errors\n"
                "2. Clarity and readability\n"
                "3. Logical flow between sections\n"
                "4. Factual accuracy\n"
                "5. Engaging intro and strong conclusion\n"
                "Return the fully edited, publication-ready article."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Edit and polish this article about {topic}:\n\n{content}"
            ),
        },
    ]

    result = model(messages) if model else "No model available"
    return {"topic": topic, "edited_content": result}


def publish_ready(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
    """Package the final content with metadata — no LLM call needed.

    This is a deterministic node (is_deterministic: true in the YAML).
    model will always be None.
    """
    edit_data = context.get("edit", {})
    final_content = edit_data.get("edited_content", "No content available")
    topic = edit_data.get("topic", "Unknown topic")

    # Calculate simple metadata without an LLM
    word_count = len(final_content.split())

    return {
        "title": topic,
        "content": final_content,
        "word_count": word_count,
        "status": "ready_for_publication",
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — wire everything together and run
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Load the DAG, configure routing, and execute the pipeline."""

    # Node registry maps YAML fn names → actual Python callables
    registry: dict[str, Any] = {
        "research": research,
        "outline": outline,
        "draft": draft,
        "edit": edit,
        "publish_ready": publish_ready,
    }

    # ModelRouter: decides which Groq model handles each node
    # - Low complexity (< 0.7): Llama 3.1 8B (fast, 30 RPM)
    # - High complexity (>= 0.7): Llama 3.3 70B (better quality)
    # - Fallback (rate-limited): Llama 3.1 8B again
    router = ModelRouter(
        low_complexity_fn=call_groq_8b,
        high_complexity_fn=call_groq_70b,
        fallback_fn=call_groq_8b,
        low_label="groq-8b",
        high_label="groq-70b",
        fallback_label="groq-8b-fallback",
        complexity_threshold=0.7,   # route to 70B when complexity >= 0.7
        groq_rpm_limit=30,          # Groq free tier: 30 requests per minute
    )

    # Resolve the YAML template path relative to this script
    template_path = Path(__file__).parent / "content-pipeline.yaml"

    # Checkpoint directory — enables crash-and-resume
    checkpoint_dir = Path(".dagpipe/checkpoints/content-pipeline")

    # Progress callback — prints status as each node completes
    def on_complete(node_id: str, result: Any, duration: float) -> None:
        print(f"  ✓ {node_id} completed in {duration:.1f}s")

    # Create the orchestrator — loads YAML, resolves functions, sorts DAG
    orch = PipelineOrchestrator(
        nodes=template_path,            # Pass Path to auto-load YAML
        node_registry=registry,
        router=router,
        checkpoint_dir=checkpoint_dir,
        max_retries=3,                  # Retry failed nodes up to 3 times
        on_node_complete=on_complete,
    )

    # Run the pipeline with a topic injected as initial_state
    topic = "The Future of AI Agents in Software Development"
    print(f"\n{'='*60}")
    print(f"  DagPipe Content Pipeline")
    print(f"  Topic: {topic}")
    print(f"{'='*60}\n")

    result = orch.run(initial_state={"topic": topic})

    # Print the final output
    final = result.get("publish_ready", {})
    print(f"\n{'='*60}")
    print(f"  Pipeline Complete!")
    print(f"  Title: {final.get('title', 'N/A')}")
    print(f"  Word Count: {final.get('word_count', 0)}")
    print(f"  Status: {final.get('status', 'unknown')}")
    print(f"{'='*60}\n")

    # Save to a text file for the demo
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "final_article.txt"
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"TITLE: {final.get('title', 'N/A')}\n")
        f.write(f"WORD COUNT: {final.get('word_count', 0)}\n")
        f.write("-" * 60 + "\n\n")
        f.write(final.get("content", ""))

    print(f"  Final article saved to: {output_file}")


if __name__ == "__main__":
    main()
