# HANDOFF.md — DagPipe Session Transition Protocol

> **When to use this:** When Herbert switches chat sessions (context too long, credits running low, or changing IDE agent). Copy the filled-out template below and paste it as the FIRST message in the new session.

## How Session Transitions Work

1. Before ending a session, the AI agent fills out the template below
2. Herbert copies the completed handoff prompt
3. Herbert pastes it as the first message in the new chat session
4. The new AI agent reads it, reads `AGENTS.md` and `PROJECT_STATUS.md`, and continues seamlessly

## Handoff Prompt Template

```
I'm continuing work on the DagPipe project. Here's the handoff from the previous session.

## Project Location
C:\Users\GASMILA\dagpipe\

## Essential Files to Read First
1. `AGENTS.md` — Project rules and structure
2. `PROJECT_STATUS.md` — Current state and what's next
3. `BLUEPRINT.md` — Detailed strategy and tech specs

## Strategy Documents (in conversation brain)
- Implementation plan: C:\Users\GASMILA\.gemini\antigravity\brain\e1b007e4-b2c4-46e7-a5b6-4d3eedd17bc0\implementation_plan.md
- Corrections report: C:\Users\GASMILA\.gemini\antigravity\brain\e1b007e4-b2c4-46e7-a5b6-4d3eedd17bc0\corrections_report.md

## Where We Left Off
[FILL: What was the last task completed?]

## What To Do Next
[FILL: Exact next step — be specific about files and functions]

## In-Progress Work
[FILL: Any half-finished files, with paths and line numbers]

## Critical Context
[FILL: Any decisions, gotchas, or things the next agent MUST know]

## Legacy Code Location
The source code to extract from is at: C:\Users\GASMILA\dagpipe\legacy\amm\

Read the AGENTS.md and PROJECT_STATUS.md files, then continue from the next step.
```

## Tips for Herbert

1. **When to switch sessions:** When the AI starts repeating itself, making errors it didn't make before, or when it stops referencing earlier context correctly
2. **Before switching:** Ask the current AI to "fill out the handoff template in HANDOFF.md"
3. **After switching:** Paste the filled template. The new agent should read the files and continue
4. **Keep sessions focused:** One phase or one major task per session works best
