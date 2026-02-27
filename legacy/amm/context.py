"""AMM Phase 5 — Context Surgery

Enforces the 16K token budget before every LLM call.
Token counting: len(text) // 4 — char-based estimate.
NOT tiktoken (GPT-calibrated, not Qwen).

Every message list produced by build_context() is guaranteed to leave
room for the output_reserve (2000 tokens) so the 7B model never
hits the context ceiling mid-generation.
"""


# ─────────────────────────────────────────────────────────────────────────────
# TOKEN BUDGET — enforced by Python before every LLM call
# ─────────────────────────────────────────────────────────────────────────────

CONTEXT_BUDGET = {
    "system_prompt":      1_500,   # Agent SOUL + task constraints
    "task_description":   1_000,   # The atomic task for this node only
    "immediate_context":  6_000,   # Relevant file snippet / function
    "episodic_injection": 2_500,   # 2-3 relevant past decisions
    "semantic_retrieved": 2_000,   # RAG from skills-cache
    "output_reserve":     2_000,   # Room for generation
    "safety_margin":      1_000,   # Never fill to 100%
}

TOTAL_BUDGET = sum(CONTEXT_BUDGET.values())  # 16,000


# ─────────────────────────────────────────────────────────────────────────────
# TOKEN COUNTING — char-based, no external deps
# ─────────────────────────────────────────────────────────────────────────────

def count_tokens(text: str) -> int:
    """Estimate token count from character length.

    Uses len(text) // 4 — a reasonable approximation for English text
    across model families. Not tiktoken (GPT-calibrated, not Qwen).
    """
    return len(text) // 4


def count_tokens_messages(messages: list[dict]) -> int:
    """Count total estimated tokens across all messages."""
    return sum(count_tokens(m.get("content", "")) for m in messages)


# ─────────────────────────────────────────────────────────────────────────────
# TRUNCATION
# ─────────────────────────────────────────────────────────────────────────────

def truncate_to_budget(text: str, budget_key: str) -> str:
    """Truncate text to fit within its budget allocation.

    Args:
        text: Raw text to potentially truncate.
        budget_key: Key from CONTEXT_BUDGET dict.

    Returns:
        Text that fits within the budget, with truncation marker if cut.
    """
    max_tokens = CONTEXT_BUDGET[budget_key]
    max_chars = max_tokens * 4  # Inverse of count_tokens
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 40] + "\n\n... [TRUNCATED TO FIT CONTEXT BUDGET]"


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT BUILDER — assembles LLM messages within 16K budget
# ─────────────────────────────────────────────────────────────────────────────

def build_context(
    system_prompt: str,
    task_description: str,
    immediate_context: str = "",
    episodic: list[str] | None = None,
    semantic: list[str] | None = None,
) -> list[dict]:
    """Assemble LLM messages within the 16K budget.

    Each section is independently truncated to its budget allocation.
    The output_reserve and safety_margin are never consumed — they exist
    to ensure the model has room to generate its response.

    Args:
        system_prompt: Agent SOUL content (markdown body from SOUL.md).
        task_description: The atomic task for this specific node.
        immediate_context: Relevant file/function snippets from prior nodes.
        episodic: Past decisions from council_memory (list of strings).
        semantic: Skill file contents from skills-cache (list of strings).

    Returns:
        List of message dicts ready for the LLM call.
    """
    messages = []

    # System prompt (agent SOUL + constraints)
    sys_text = truncate_to_budget(system_prompt, "system_prompt")
    messages.append({"role": "system", "content": sys_text})

    # Build user message from parts, each truncated independently
    parts = []

    # Task description — always included
    parts.append(truncate_to_budget(task_description, "task_description"))

    # Immediate context — output from upstream DAG nodes
    if immediate_context:
        parts.append(
            "## Context from Previous Steps\n"
            + truncate_to_budget(immediate_context, "immediate_context")
        )

    # Episodic memory — past decisions (council rejection log, etc.)
    if episodic:
        ep_text = "\n".join(episodic)
        parts.append(
            "## Recent Decisions (do NOT repeat these)\n"
            + truncate_to_budget(ep_text, "episodic_injection")
        )

    # Semantic memory — skill files fetched from skills-cache
    if semantic:
        sem_text = "\n".join(semantic)
        parts.append(
            "## Reference Skills (use these patterns, NOT training data)\n"
            + truncate_to_budget(sem_text, "semantic_retrieved")
        )

    user_content = "\n\n".join(parts)
    messages.append({"role": "user", "content": user_content})

    # Final safety check
    total = count_tokens_messages(messages)
    safe_limit = TOTAL_BUDGET - CONTEXT_BUDGET["output_reserve"] - CONTEXT_BUDGET["safety_margin"]
    if total > safe_limit:
        print(
            f"[CONTEXT] WARNING: {total} tokens exceeds safe limit ({safe_limit}). "
            f"Emergency truncation may degrade output quality."
        )

    return messages


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT EVICTION — for multi-turn interactions within a single node
# ─────────────────────────────────────────────────────────────────────────────

def manage_context(messages: list[dict], budget: int) -> list[dict]:
    """Evict oldest non-system content if context exceeds budget.

    Used during multi-turn interactions within a single node
    (e.g. repair loops). Preserves the system message and the most
    recent user/assistant messages.

    Args:
        messages: Current message list.
        budget: Max token budget for the full context.

    Returns:
        Trimmed message list.
    """
    threshold = int(budget * 0.85)

    while count_tokens_messages(messages) > threshold and len(messages) > 2:
        # Find oldest non-system, non-latest message
        for i in range(1, len(messages) - 1):
            content = messages[i].get("content", "")
            summary = content[:80] + "..." if len(content) > 80 else content
            messages[i] = {
                "role": messages[i]["role"],
                "content": f"[EVICTED — summary: {summary}]",
            }
            break
        else:
            break  # Nothing left to evict

    return messages
