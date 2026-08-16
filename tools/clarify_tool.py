#!/usr/bin/env python3
"""
Clarify Tool Module - Interactive Clarifying Questions

Allows the agent to present structured multiple-choice questions or open-ended
prompts to the user. In CLI mode, choices are navigable with arrow keys. On
messaging platforms, choices are rendered as a numbered list.

Supports both single-select (radio) and multi-select (checkbox) modes via the
``multi_select`` parameter.

The actual user-interaction logic lives in the platform layer (cli.py for CLI,
gateway/run.py for messaging). This module defines the schema, validation, and
a thin dispatcher that delegates to a platform-provided callback.
"""

import json
import re
from typing import List, Optional, Callable


# Maximum number of predefined choices shown on a single page/message.
# A 5th "Other (type your answer)" option is always appended by the UI.
MAX_CHOICES = 4

# --- Choice response format rules (2026-08-16, CEO-adopted) ---------------
# Adopted after the CEO reported choices being cut off / hard to read on
# Slack ("선택지에 글이 길어서 짤리는데 정확하게 확인할 수가 없다"). Four rules,
# all mandatory, apply everywhere the bot presents multiple choices:
#   1. Never ask the user to re-state their original request just because the
#      candidate choices feel ambiguous/incomplete — build the best possible
#      choices from what's already known instead (this is a prompting/schema
#      instruction, enforced via CLARIFY_SCHEMA's description below; there is
#      deliberately no "please rephrase" style fallback anywhere in this
#      module).
#   2. Each choice renders as exactly ONE line (no embedded newlines).
#   3. Each choice line is <=30 characters — short titles only; the detailed
#      explanation is a SEPARATE follow-up message sent only after the user
#      has picked by number (title first, detail after — never both at once).
#   4. At most MAX_CHOICES real choices per page, with numeric-reply support
#      (handled by tools/clarify_gateway.py's `_coerce_text_response`).
# Rule 5 (below) is the additional risk-mitigation extension for the case
# where more than MAX_CHOICES real choices are genuinely needed.
MAX_CHOICE_CHARS = 30

# Fixed label for the pagination "see more" entry (rule 5: >4 choices).
# Reserved verbatim per the adopted plan — do not localize/rename casually;
# platform adapters and the gateway's numeric-reply resolution match against
# this exact choice text to detect "the user wants the next page".
MORE_CHOICES_LABEL = "다른 선택지 보기"

# Sane upper bound on how many *raw* choices a single clarify() call may
# carry before they get paginated. Prevents a runaway/malformed tool call
# from generating an unbounded number of pages; well above any real use case.
MAX_TOTAL_CHOICES = 20


def _flatten_choice(c) -> str:
    """Coerce a single choice into its user-facing display string.

    The schema declares choices as bare strings, but LLMs sometimes emit
    dict-shaped choices like ``[{"description": "..."}]``. A naive ``str(c)``
    turns the whole dict into its Python repr — ``{'description': '...'}`` —
    which then leaks onto every surface that renders the choice (CLI panel,
    Discord buttons, Telegram numbered list) AND is returned verbatim as the
    user's answer. Normalising here, at the one platform-agnostic entry point,
    fixes the whole class in one place instead of per-adapter.

    Dict unwrap order is the canonical LLM tool-call user-facing keys:
    ``label`` → ``description`` → ``text`` → ``title``. ``name`` and ``value``
    are deliberately excluded — they're component-shaped fields that could
    carry raw enum values or short identifiers, not human-readable labels. A
    dict with none of the canonical keys is dropped (returns ""), since a
    garbage label is worse than no choice at all.
    """
    if c is None:
        return ""
    if isinstance(c, str):
        return c.strip()
    if isinstance(c, dict):
        for key in ("label", "description", "text", "title"):
            v = c.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""
    if isinstance(c, (list, tuple)):
        return " ".join(_flatten_choice(x) for x in c).strip()
    return str(c).strip()


def _format_choice_line(text: str, max_chars: int = MAX_CHOICE_CHARS) -> str:
    """Enforce the one-line + <=N-char choice format rules (#2 and #3).

    First collapses any whitespace/newlines into single spaces (a choice
    must always render as exactly one line — rule #2), then truncates to
    ``max_chars`` with a trailing ellipsis if still too long (rule #3).

    This is a defensive backstop, not the primary mechanism: CLARIFY_SCHEMA
    instructs the calling LLM to already write short one-line titles and put
    detail in a follow-up message. But a caller that ignores the instruction
    should still get a readable, single-line, bounded-width choice instead
    of the original complaint (a choice long enough to get cut off / wrap
    unreadably on a narrow chat surface like Slack).
    """
    line = re.sub(r"\s+", " ", text).strip()
    if len(line) > max_chars:
        line = line[: max_chars - 1].rstrip() + "…"
    return line


def _invoke_callback(callback, question, choices, multi_select):
    """Invoke the platform callback, passing multi_select if supported.

    Uses signature inspection (not a ``TypeError`` retry) to decide whether
    the callback accepts the ``multi_select`` keyword — a retry-on-TypeError
    approach would re-invoke a *compatible* callback that raised TypeError
    internally, potentially prompting the user twice.
    """
    import inspect

    accepts_multi = False
    try:
        sig = inspect.signature(callback)
        params = sig.parameters
        accepts_multi = "multi_select" in params or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
    except (TypeError, ValueError):
        # Builtins / C callables without introspectable signatures:
        # be conservative and use the legacy 2-arg form.
        accepts_multi = False

    if accepts_multi:
        return callback(question, choices, multi_select=multi_select)
    return callback(question, choices)


def _parse_multi_select_response(raw_response) -> List[str]:
    """Parse a multi-select response into a list of cleaned choice strings.

    Handles three forms:
      - Already a list  →  stringify + strip each element
      - JSON array      →  parse and strip
      - Comma-separated →  split, strip, drop empties
    """
    if isinstance(raw_response, list):
        return [str(r).strip() for r in raw_response if str(r).strip()]

    raw = str(raw_response).strip()

    # Try JSON array
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(p).strip() for p in parsed if str(p).strip()]
        except json.JSONDecodeError:
            pass

    # Fall back to comma-separated
    return [s.strip() for s in raw.split(",") if s.strip()]


def clarify_tool(
    question: str,
    choices: Optional[List[str]] = None,
    multi_select: bool = False,
    callback: Optional[Callable] = None,
) -> str:
    """
    Ask the user a question, optionally with multiple-choice options.

    Args:
        question:     The question text to present.
        choices:      Predefined answer choices (up to MAX_TOTAL_CHOICES).
                      Each is normalised to one line, <=30 chars (rules #2/#3).
                      When there are more than MAX_CHOICES (4) of them and
                      multi_select is False, only the first MAX_CHOICES are
                      shown on this page plus a fixed "다른 선택지 보기" entry
                      (rule #5); the remaining choices are returned in the
                      output's ``more_choices`` field so the caller can issue
                      a follow-up clarify() call for the next page. When
                      omitted the question is purely open-ended.
        multi_select: When True, the user can select multiple choices
                      (checkboxes).  The ``user_response`` in the output JSON
                      will be a list of strings instead of a single string.
                      Has no effect when ``choices`` is omitted. Pagination
                      (rule #5) is not applied in multi-select mode — choices
                      are simply capped at MAX_CHOICES as before.
        callback:     Platform-provided function that handles the actual UI
                      interaction.  Signature:
                      ``callback(question, choices, multi_select=False) -> str``.
                      The optional ``multi_select`` keyword is passed so the
                      platform can render checkboxes instead of radio buttons.
                      Injected by the agent runner (cli.py / gateway).

    Returns:
        JSON string with the user's response.
    """
    if not question or not question.strip():
        return tool_error("Question text is required.")

    question = question.strip()

    # Validate, flatten, and format choices
    more_choices: List[str] = []
    if choices is not None:
        if not isinstance(choices, list):
            return tool_error("choices must be a list of strings.")
        # LLMs sometimes emit dict-shaped choices (e.g. [{"description": "..."}])
        # instead of bare strings. _flatten_choice unwraps them to their
        # user-facing text here — the single platform-agnostic entry point —
        # so the CLI panel, Discord buttons, and Telegram list all render clean
        # text and the resolved answer is never a raw Python dict repr.
        choices = [s for s in (_flatten_choice(c) for c in choices) if s]
        # Rules #2/#3: one line, <=30 chars per choice.
        choices = [s for s in (_format_choice_line(c) for c in choices) if s]
        if len(choices) > MAX_TOTAL_CHOICES:
            choices = choices[:MAX_TOTAL_CHOICES]

        if multi_select:
            # Pagination (rule #5) is scoped to single-select flows only —
            # multi-select "want more AND already picked some" has no clean
            # resolution in tools/clarify_gateway.py's selection coercion, so
            # keep the simple pre-existing behavior: cap and show as one page.
            if len(choices) > MAX_CHOICES:
                choices = choices[:MAX_CHOICES]
        elif len(choices) > MAX_CHOICES:
            # Rule #5: show the top MAX_CHOICES, fix a "see more" entry in
            # the next slot, and hand the rest back to the caller so it can
            # issue a follow-up clarify() call in the same 1-line/30-char/
            # numbered format if the user picks it.
            more_choices = choices[MAX_CHOICES:]
            choices = choices[:MAX_CHOICES] + [MORE_CHOICES_LABEL]

        if not choices:
            choices = None  # empty list → open-ended

    if callback is None:
        return tool_error("Clarify tool is not available in this execution context.")

    try:
        raw_response = _invoke_callback(callback, question, choices, multi_select)
    except Exception as exc:
        return tool_error(f"Failed to get user input: {exc}")

    if multi_select and choices is not None:
        user_response = _parse_multi_select_response(raw_response)
    else:
        user_response = str(raw_response).strip()

    result = {
        "question": question,
        "choices_offered": choices,
        "user_response": user_response,
    }
    if more_choices:
        result["more_choices"] = more_choices
        result["more_choices_note"] = (
            f"{len(more_choices)} more choice(s) were not shown on this page. "
            f"If user_response is \"{MORE_CHOICES_LABEL}\", call clarify() again "
            "with these as `choices` to show the next page in the same "
            "1-line/<=30-char/numbered format."
        )
    return json.dumps(result, ensure_ascii=False)


def check_clarify_requirements() -> bool:
    """Clarify tool has no external requirements -- always available."""
    return True


# =============================================================================
# OpenAI Function-Calling Schema
# =============================================================================

CLARIFY_SCHEMA = {
    "name": "clarify",
    "description": (
        "Ask the user a question when you need clarification, feedback, or a "
        "decision before proceeding. Supports three modes:\n\n"
        "1. **Single-select multiple choice** — provide choices (ideally up to 4). The user picks one "
        "or types their own answer via a final 'Other' option.\n"
        "2. **Multi-select multiple choice** — set multi_select=true. The user can select "
        "multiple options via checkboxes. user_response will be a list of selected choices.\n"
        "3. **Open-ended** — omit choices entirely. The user types a free-form "
        "response.\n\n"
        "CRITICAL: when you are offering options, put each option ONLY in the "
        "`choices` array — NEVER enumerate the options inside the `question` "
        "text. The UI renders `choices` as selectable rows; options written "
        "into the question string render as dead prose the user can't pick. "
        "Right: question='Which deployment target?', choices=['staging', "
        "'prod']. Wrong: question='Which target? 1) staging 2) prod', choices=[].\n\n"
        "CHOICE FORMAT RULES (mandatory, apply to every choice you write):\n"
        "- Never ask the user to restate or re-explain their original request just "
        "because your candidate choices feel ambiguous or incomplete — build the "
        "best possible choices from what you already know and offer THOSE.\n"
        "- Each choice is a short, ONE-LINE title only (no line breaks). Keep it to "
        "roughly 30 characters or less — put any longer explanation in a separate "
        "follow-up message you send AFTER the user picks by number, never both at "
        "once. Order: short title → user picks by number → detailed explanation.\n"
        "- If you have more than 4 real options, pass them all anyway (up to 20) — "
        "the tool automatically shows the first 4 plus a 'see more' entry, and "
        "returns the rest in `more_choices` for you to offer as a follow-up "
        "clarify() call in the same format if the user asks for more.\n\n"
        "Use this tool when:\n"
        "- The task is ambiguous and you need the user to choose an approach\n"
        "- You want post-task feedback ('How did that work out?')\n"
        "- You want to offer to save a skill or update memory\n"
        "- A decision has meaningful trade-offs the user should weigh in on\n\n"
        "Do NOT use this tool for simple yes/no confirmation of dangerous "
        "commands (the terminal tool handles that). Prefer making a reasonable "
        "default choice yourself when the decision is low-stakes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": (
                    "The question itself, and ONLY the question (e.g. 'Which "
                    "deployment target?'). Do NOT embed the answer options here "
                    "— pass them as separate elements in `choices`."
                ),
            },
            "choices": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": MAX_TOTAL_CHOICES,
                "description": (
                    "REQUIRED whenever you are presenting selectable options: "
                    "each distinct option is its own array element, as a short "
                    "ONE-LINE title (<=30 chars — put detail in a follow-up "
                    "message instead). Up to 4 are shown per page; if you pass "
                    "more (up to 20), the tool paginates automatically with a "
                    "'see more' entry and returns the overflow in "
                    "`more_choices` for a follow-up call. The UI auto-appends "
                    "an 'Other (type your answer)' option. Omit this parameter "
                    "entirely ONLY for a genuinely open-ended free-text question."
                ),
            },
            "multi_select": {
                "type": "boolean",
                "description": (
                    "When true, the user can select MULTIPLE options (like checkboxes). "
                    "The user_response will be a list of selected choices. "
                    "When false (default), single selection (radio). "
                    "Has no effect when choices is omitted (open-ended question)."
                ),
            },
        },
        "required": ["question"],
    },
}


# --- Registry ---
from tools.registry import registry, tool_error

registry.register(
    name="clarify",
    toolset="clarify",
    schema=CLARIFY_SCHEMA,
    handler=lambda args, **kw: clarify_tool(
        question=args.get("question", ""),
        choices=args.get("choices"),
        multi_select=args.get("multi_select", False),
        callback=kw.get("callback")),
    check_fn=check_clarify_requirements,
    emoji="❓",
)
