# Verifying a capability tool's check_fn actually passes for a profile

Worked example: `image_gen` tool, gated by
`check_image_generation_requirements()` in `tools/image_generation_tool.py`.
The same two-part pattern (config wiring + real credential) applies to any
tool registered with a `check_fn` in the tool registry — a `check_fn`
returning False makes the tool invisible to the model that turn, with no
error surfaced anywhere a human would naturally look.

## Two independent gates — check both, not just one

1. **Config key presence.** `check_image_generation_requirements()` calls
   `_read_configured_image_provider()`, which reads `image_gen.provider`
   from that profile's `config.yaml`. If `provider:` is absent, the
   function returns False immediately — regardless of what
   `image_gen.model` / `image_gen.openai.model` (the tier selector) say.
   Setting only the tier and forgetting `provider: openai` is a natural
   mistake because the tier key looks like "the" config and lints/loads
   fine on its own.

   ```yaml
   image_gen:
     provider: openai      # <- required, easy to omit
     model: gpt-image-2-medium
     openai:
       model: gpt-image-2-medium
   ```

2. **Real credential, not a template placeholder.** `hermes profile create
   --clone-from default` copies the default `.env.example`-style file
   verbatim, including commented/placeholder lines such as
   `OPENAI_API_KEY=<sk-...>`. That string is non-empty, so a naive
   "is this env var set" check looks satisfied — but
   `provider.is_available()` (e.g. `OpenAIImageGenProvider.is_available()`
   in `plugins/image_gen/openai/__init__.py`) calls `get_secret()`, which
   returns the placeholder text itself; downstream API calls with it fail,
   or in this codebase the availability check treats it as present but the
   generation call fails. Either way the deliverable silently degrades
   (agent falls back to producing *something* — an HTML mockup, a text
   description — without flagging that the intended tool was unavailable).

## Diagnostic one-liner (safe — never prints the key value)

Run from the orchestrator, targeting the specialist profile, to check both
gates without exposing the secret:

```
hermes -p <profile> chat -q "python으로 check_image_generation_requirements() 결과와, False라면 provider.is_available() 및 (해당 키) 존재 여부(길이/시작 3글자만)를 확인해줘. 값 자체는 출력하지 마." -Q --yolo
```

Interpret the result:
- `check_image_generation_requirements() == True` → tool will be exposed;
  safe to delegate.
- `False` + provider not configured → add `provider: <id>` to that
  profile's `config.yaml` under the tool's config section.
- `False` + provider configured but `is_available()` False → the
  credential is missing or is a placeholder. Fix via `hermes auth add` (or
  the profile's own `hermes setup`) run in a **foreground session** so the
  user types the real value directly — never have an agent read, echo, or
  paste the key value itself.

## Generalizing beyond image_gen

Any tool registered via `registry.register(..., check_fn=...)` follows this
shape: a boolean gate function decides at each turn whether the tool schema
is exposed at all, with no error path for "gate failed." When a specialist
profile's task depends on such a tool, verify the check_fn passes for that
profile BEFORE trusting a "success" report — the model has no way to tell
the kanban task summary "I couldn't use the tool you expected" if it never
even saw the tool existed.
