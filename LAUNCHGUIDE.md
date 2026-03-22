# DagPipe Pipeline Generator

## Tagline
Crash-proof LLM pipelines. Resumes from failure without a database.

## Description
DagPipe makes LLM pipelines crash-proof by saving each completed 
node's output to a plain JSON file. When a pipeline fails, re-running 
it skips finished nodes and resumes from exactly where it stopped. 
No database, no broker, just files.

Built for developers who are tired of losing pipeline progress to 
timeouts, rate limits, and bad model responses. Especially useful 
when running multi-step workflows on free tier APIs where every 
failed node costs real quota.

Ships with smart model routing by task complexity, Pydantic schema 
validation with auto-retry on malformed output, dead letter queue 
for failed nodes, context isolation so nodes only see their declared 
dependencies, and an MCP server for generating pipelines directly 
from Claude Desktop, Cursor, or Windsurf.

## Setup Requirements
- `GROQ_API_KEY` (optional): Free Groq API key for using Groq models 
as the default router. Get one at https://console.groq.com
- `GEMINI_API_KEY` (optional): Free Gemini API key for Google model 
fallback. Get one at https://aistudio.google.com

## Category
Developer Tools

## Use Cases
LLM Pipeline Orchestration, AI Agent Development, Crash Recovery, 
Multi-step Automation, Free Tier Optimization, Agentic Workflows

## Features
- Checkpoint-based crash recovery: every completed node saves output 
to a plain JSON file before the next node starts
- Smart model routing: routes tasks to free or cheap models based on 
complexity score, escalates on failure
- Constrained generation: Pydantic schema validation with auto-retry 
when the model returns malformed output
- Dead letter queue: every failed node saves full error context to 
disk for inspection and manual override
- Context isolation: nodes only receive output from their declared 
dependencies, safe for sensitive data
- Live model registry: validates model configs at startup, refreshes 
free tier availability every 24 hours
- Pluggable checkpoint backends: swap filesystem for Redis, S3, or 
any custom store
- MCP server: generate crash-proof pipelines from plain English via 
Claude Desktop, Cursor, or Windsurf

## Getting Started
- "Generate a crash-proof pipeline for summarizing research papers"
- "Create a pipeline that scrapes a URL, extracts key points, and 
saves a markdown report"
- "Build a pipeline that takes a job description and generates a 
tailored cover letter"
- Tool: generate_pipeline — Generates a complete DagPipe pipeline 
from a plain English description of what you want to automate

## Tags
python, llm, pipeline, orchestration, crash-recovery, ai-agents, 
mcp, free-tier, dag, checkpointing, pydantic, groq, gemini, 
langchain-alternative, langgraph-alternative, agentic-workflows

## Documentation URL
https://devilsfave.github.io/dagpipe/llms.txt

## Health Check URL
