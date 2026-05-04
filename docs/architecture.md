# Architecture

How the pieces fit, what owns what, and where the boundaries are.

## Component map

```
                      ┌──────────────────────────────────┐
                      │      hermes-agent CLI            │
                      │  (chat loop, tool dispatch)      │
                      └────┬───────────────────┬─────────┘
                           │                   │
                  loads at start         dispatches at runtime
                           │                   │
                           ▼                   ▼
       ┌────────────────────────────────────────────────────┐
       │ ~/.hermes/plugins/hermes_comfyui_theme_maker/      │
       │  (symlinked from this repo)                        │
       │                                                    │
       │  ┌──────────────────┐   ┌──────────────────────┐  │
       │  │  SKILL.md        │   │  tools.py            │  │
       │  │  design          │   │   list_…_tokens      │  │
       │  │  knowledge       │   │   write_…_theme      │  │
       │  │  (markdown)      │   │   apply_…_theme      │  │
       │  │                  │   │   generate_mood_img  │  │
       │  │                  │   │   extract_palette    │  │
       │  └──────────────────┘   └──────┬───────────────┘  │
       │                                │                  │
       │  ┌──────────────────────────────────────────────┐ │
       │  │  token_inventory.py — canonical token list   │ │
       │  │  schemas.py         — JSON tool schemas      │ │
       │  │  workflows/anima-turbo.json (planned)        │ │
       │  └──────────────────────────────────────────────┘ │
       └─────┬────────────────────────────────────┬─────────┘
             │                                    │
             │ writes / reads files               │ HTTP
             ▼                                    ▼
   <ComfyUI_frontend checkout>/         http://127.0.0.1:8188
                                        (ComfyUI HTTP API)
     src/assets/css/                       /prompt
       style.css       (modified)          /history/<id>
       themes/<name>.css (written)         /view?...
                                           /ws (optional)

                                   on llama.cpp side:
                                   http://127.0.0.1:8080
                                   serves Hermes-4.3-36B-GGUF
                                   (used by hermes-agent itself,
                                    not by tools)
```

## Data flow

### Use case A — image-gen-grounded theme generation (target end state)

User types: *"make me a campfire theme"*

```
hermes-agent (LLM)
   │
   │ (1) loads SKILL.md from plugin into context
   │ (2) decides to do visual research
   │
   ├──── tool call: generate_mood_image(prompt="…campfire embers…")
   │         │
   │         │ POST /prompt with parameterized workflow JSON
   │         ▼
   │       ComfyUI ── runs Anima turbo (~5–15 s on M4)
   │         │
   │         │ poll /history/<prompt_id>
   │         │ download via /view?filename=…&type=output
   │         ▼
   │       returns {"path": "…/output/mood-001.png", "prompt_id": "…"}
   │
   ├──── tool call: extract_palette_from_image(path, n_colors=8)
   │         │
   │         │ Pillow opens image → numpy → k-means(8)
   │         ▼
   │       returns {"colors": ["#3a201a", "#a04020", "#e0a050", …]}
   │
   │ (3) maps anchors onto token ramps (charcoal: dark anchors,
   │     accent: warm anchors, app-mode-go/stop, etc.)
   │
   ├──── tool call: write_comfyui_theme(name="campfire-mood",
   │                                    overrides={…})
   │         │
   │         │ writes ComfyUI_frontend/src/assets/css/themes/campfire-mood.css
   │         ▼
   │       returns {"ok": true, "path": "…", "tokens_written": 17}
   │
   ├──── tool call: apply_comfyui_theme(name="campfire-mood")
   │         │
   │         │ injects @import block (between sentinels) into
   │         │ ComfyUI_frontend/src/assets/css/style.css
   │         ▼
   │       returns {"ok": true, "active_theme": "campfire-mood"}
   │
   │ (4) Vite HMR live-reloads the browser
   │ (5) Hermes summarizes: mode, palette source, accent picks
   │
   ▼
User sees the reference image and the applied theme. Iterates.
```

### Use case B — text-only fallback (current MVP behavior)

If ComfyUI is unreachable, the Anima workflow fails, or the user
explicitly says "no image needed", Hermes skips the first two tool
calls and proceeds directly to `write_comfyui_theme` →
`apply_comfyui_theme`. The skill instructs the LLM to pick palette
anchors from the description alone using the design heuristics.

### Use case C — iteration without re-generation

User says *"warmer"* after seeing the applied theme. Hermes does **not**
call `generate_mood_image` again. Instead it:

1. Reads the most recent overrides (either from memory or by re-reading
   the active theme file).
2. Adjusts hex values toward warmer hue.
3. Calls `write_comfyui_theme` with the same `name` (overwrites) and
   `apply_comfyui_theme` (idempotent — same sentinel block, same
   import).
4. Vite HMR re-loads.

## File layout

```
hermes-comfyui-theme-maker/
├── README.md                    # user-facing setup + usage
├── PLAN.md                      # vision, roadmap, decisions
├── LICENSE                      # GPL-3.0
├── plugin.yaml                  # Hermes plugin manifest
├── __init__.py                  # register(ctx) — entry point
├── schemas.py                   # JSON schemas describing tools to LLM
├── tools.py                     # tool implementations
├── token_inventory.py           # canonical CSS token inventory
├── docs/
│   ├── architecture.md          # this file
│   └── comfyui-api-notes.md     # ComfyUI HTTP API reference
├── skills/
│   └── comfyui-theme-maker/
│       └── SKILL.md             # design knowledge for the LLM
├── workflows/                   # (planned, layer 2)
│   └── anima-turbo.json         # parameterized Anima/Qwen template
├── examples/
│   └── campfire.css             # hand-designed reference theme
├── scripts/
│   └── smoke_test.py            # end-to-end verification
└── tests/                       # (currently empty)
```

## Integration points

### 1. Hermes plugin model

- Plugin discovered at `~/.hermes/plugins/hermes_comfyui_theme_maker/`
  (underscored — Hermes loads as a Python package).
- `__init__.py` exposes `register(ctx)` which Hermes calls on startup:
  - `ctx.register_skill(name, skill_md)` — skill markdown enters the
    LLM's context when invoked.
  - `ctx.register_tool(name, toolset, schema, handler)` — registers a
    callable tool with its JSON schema.
- Tool handlers: `def handler(args: dict, **kwargs) -> str`. Always
  return a JSON string (success and error). Catch exceptions
  internally — never raise.
- Toolset name (`comfyui-theme-maker`) groups all five tools so the user can
  enable/disable them together via `hermes tools`.

### 2. ComfyUI HTTP API

- Base URL: `http://127.0.0.1:8188` (default, configurable via env).
- `POST /prompt` — submits a workflow JSON in the **prompt format**
  (not the UI workflow format). Returns `{prompt_id, number, …}`.
- `GET /history/<prompt_id>` — returns workflow execution result with
  output node references when complete.
- `GET /view?filename=…&type=output[&subfolder=…]` — fetches the
  generated image.
- See `docs/comfyui-api-notes.md` for endpoint specifics, the
  prompt-vs-workflow format distinction, and a worked submission.

### 3. ComfyUI_frontend file system

- Theme files live at
  `$HERMES_COMFYUI_FRONTEND_PATH/src/assets/css/themes/<name>.css`.
- The `apply` tool injects an `@import` between sentinel comments in
  `$HERMES_COMFYUI_FRONTEND_PATH/src/assets/css/style.css`. Idempotent
  swap; one theme active at a time.
- Vite dev server (`pnpm dev`) watches both files via HMR.

## Tool inventory

### Layer 1 (current — DONE)

| Tool | Inputs | Output | Side effects |
|---|---|---|---|
| `list_comfyui_tokens` | `layer?: "all" \| "palette" \| "extended_palette" \| "app_mode" \| "layout"` | JSON of tokens | none |
| `write_comfyui_theme` | `name`, `overrides` (token: value dict) | JSON `{ok, path, tokens_written}` | writes `themes/<name>.css` |
| `apply_comfyui_theme` | `name` | JSON `{ok, active_theme}` | modifies `style.css` (sentinel block) |

### Layer 2 (next — TO BUILD)

| Tool | Inputs | Output | Side effects |
|---|---|---|---|
| `generate_mood_image` | `prompt`, `size?`, `seed?` | JSON `{ok, path, prompt_id}` | writes ComfyUI's normal output dir |
| `extract_palette_from_image` | `path`, `n_colors?` (default 8) | JSON `{colors: [hex…], counts: [int…]}` | none |

Total handlers in `tools.py` after layer 2: 5.

## Failure modes and how we handle them

| Failure | Detection | Response |
|---|---|---|
| ComfyUI not running | TCP/HTTP error from `generate_mood_image` | Tool returns `{error: "…"}`. Skill instructs LLM to fall back to text-only generation. |
| ComfyUI workflow rejected | non-200 from `POST /prompt` | Tool returns error with ComfyUI's message. Same fallback. |
| Generation timeout | poll exceeds threshold (e.g. 60 s) | Tool cancels, returns `{error: "timeout"}`. Same fallback. |
| Output file missing | `/history` shows complete but `/view` 404s | Same fallback. |
| Palette extraction fails | image unreadable | Same fallback — generate theme without palette anchors. |
| `style.css` missing or moved | tool detects on apply | Returns error; user fixes `HERMES_COMFYUI_FRONTEND_PATH`. |

The whole layer 2 stack is treated as **optional research**. Layer 1
must always work; layer 2 enriches when available.

## Out of scope for the hackathon

- Multi-modal vision (Hermes-4.3-36B is text-only — we never feed the
  generated image back to the LLM directly).
- Custom ComfyUI nodes (we only use built-in nodes via the existing
  Anima workflow template).
- Theme switching UI inside ComfyUI_frontend (out of scope; the
  user-driven theme switcher is the open theme-system redesign tracked
  in PR #11317 description).
- Cross-checkpoint mood generation (only the user's installed Anima
  stack is supported).
