# Content Pipeline Template — How to Use

## What This Pipeline Does

Automates the full content creation workflow: **research → outline → draft → edit → publish**. Give it a topic, and DagPipe chains five LLM calls (via Groq's free tier) to produce a polished, publication-ready article.

## Prerequisites

```bash
pip install dagpipe-core groq
```

## Set Your API Key

Get a free Groq API key at [console.groq.com](https://console.groq.com).

```bash
# Linux / Mac
export GROQ_API_KEY="gsk_your_key_here"

# Windows CMD
set GROQ_API_KEY=gsk_your_key_here

# Windows PowerShell
$env:GROQ_API_KEY = "gsk_your_key_here"
```

## Run It

```bash
python templates/content_pipeline_runner.py
```

To change the topic, edit the `topic` variable in `main()`.

## Expected Output

```
============================================================
  DagPipe Content Pipeline
  Topic: The Future of AI Agents in Software Development
============================================================

  ✓ research completed in 2.3s
  ✓ outline completed in 1.8s
  ✓ draft completed in 5.1s
  ✓ edit completed in 3.4s
  ✓ publish_ready completed in 0.0s

============================================================
  Pipeline Complete!
  Title: The Future of AI Agents in Software Development
  Word Count: 1042
  Status: ready_for_publication
============================================================
```

## How Checkpointing Works

DagPipe saves each node's output to `.dagpipe/checkpoints/content-pipeline/` as it completes. If the pipeline crashes mid-run (network error, rate limit, etc.), simply re-run the same command — it picks up **exactly where it left off**, skipping already-completed nodes.

To force a fresh run from scratch, delete the checkpoint directory:

```bash
# Linux / Mac
rm -rf .dagpipe/checkpoints/content-pipeline/

```bash
# Windows
rmdir /s /q .dagpipe\checkpoints\content-pipeline\
```

---

## Using Other Providers

DagPipe is **100% provider-agnostic**. The `content_pipeline_runner.py` script defaults to Groq, but the pipeline's `PipelineOrchestrator` accepts *any* Python callable as a model.

Here is how you can swap Groq for other popular providers. Just replace the `groq_70b` and `groq_8b` callables in your runner script with any of these 5-line wrappers:

### 1. OpenAI (GPT-4o)
```python
from openai import OpenAI
client = OpenAI(api_key="your-api-key")

def openai_gpt4o(messages):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages
    )
    return response.choices[0].message.content
```

### 2. Local Ollama (Free & Private)
```python
from openai import OpenAI
# Ollama provides an OpenAI-compatible endpoint out of the box
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

def local_llama3(messages):
    response = client.chat.completions.create(
        model="llama3",
        messages=messages
    )
    return response.choices[0].message.content
```

### 3. Google Gemini (Flash)
```python
import google.generativeai as genai
genai.configure(api_key="your-api-key")
model = genai.GenerativeModel('gemini-2.0-flash')

def gemini_flash(messages):
    # Convert standard OpenAI message format to Gemini format
    prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
    response = model.generate_content(prompt)
    return response.text
```

Change the `low_complexity_fn` and `high_complexity_fn` in your `ModelRouter` to point to whichever function you prefer.
