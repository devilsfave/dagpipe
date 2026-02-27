# DagPipe — Zero-cost, crash-proof LLM pipeline orchestrator

## Installation
```bash
pip install dagpipe
```

## Quickstart
```python
from pathlib import Path
from dagpipe.dag import PipelineOrchestrator, DAGNode
from dagpipe.checkpoints import checkpoint, restore
from dagpipe.constrained import constrained_generate

# Define your nodes
def step_one(context, model):
    return {"result": "step one complete"}

def step_two(context, model):
    return {"result": f"step two got: {context['step_one']}"}

# Build the pipeline
nodes = [
    DAGNode(id="step_one", fn_name="step_one", complexity=0.3),
    DAGNode(id="step_two", fn_name="step_two", 
            depends_on=["step_one"], complexity=0.6),
]

orchestrator = PipelineOrchestrator(
    nodes=nodes,
    node_registry={"step_one": step_one, "step_two": step_two},
    checkpoint_dir=Path(".dagpipe/checkpoints"),
)

result = orchestrator.run()
print(result)
```

## Core Features
- **Crash-proof**: JSON checkpointing — resume from last successful node after any failure
- **Zero-cost**: Route across free-tier LLMs with built-in complexity-based model selection
- **Schema-enforced**: Pydantic-validated output with automatic retry on invalid JSON

## License
MIT
