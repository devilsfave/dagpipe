import os
from pathlib import Path
from groq import Groq
from dagpipe.dag import PipelineOrchestrator, DAGNode
from dagpipe.registry import ModelRegistry
from dagpipe.router import ModelRouter

def summarize(context: dict, model=None) -> dict:
    return {"summary": "news summary"}

def classify(context: dict, model=None) -> dict:
    return {"sentiment": "positive"}

def main():
    registry = {"summarize": summarize, "classify": classify}
    model_reg = ModelRegistry(groq_api_key=os.environ.get("GROQ_API_KEY"))
    router = ModelRouter(
        low_complexity_fn=lambda x: "low",
        high_complexity_fn=lambda x: "high",
        fallback_fn=lambda x: "fallback",
        rpm_limit=30
    )
    orch = PipelineOrchestrator(
        nodes=Path(__file__).parent / "pipeline.yaml",
        node_registry=registry,
        router=router,
        model_registry=model_reg,
    )
    state, run = orch.run(initial_state={"input": "news text"})
    print(f"Status: {run.status}")

if __name__ == "__main__":
    main()