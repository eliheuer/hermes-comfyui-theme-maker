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
       │  │  knowledge       │   │   generate_mood_img  │  │
       │  │                  │   │   extract_palette    │  │
       │  │                  │   │   write_…_theme      │  │
       │  │                  │   │   apply_…_theme      │  │
       │  │                  │   │   render_…_swatch    │  │
       │  │                  │   │   render_…_image     │  │
       │  └──────────────────┘   └──────┬───────────────┘  │
       │                                │                  │
       │  token_inventory.py · schemas.py                  │
       └─────┬────────────────────────────────────┬─────────┘
             │                                    │
             │ writes / reads files               │ HTTP
             ▼                                    ▼
   <ComfyUI_frontend checkout>/         http://127.0.0.1:8188
                                        (ComfyUI HTTP API)
```

The LLM endpoint runs separately (cloud, or local `llama-server`) and
isn't part of the plugin's process.

## Data flow

User types: *"make me a campfire theme"*

```
hermes-agent (LLM)
   │
   │ (1) loads SKILL.md into context
   │ (2) checks memory for comfyui_frontend_path; asks user if missing
   │ (3) plans visual research
   │
   ├── generate_mood_image(prompt="…campfire embers…")
   │      → POST /prompt (Anima/Qwen workflow)
   │      → poll /history → fetch /view
   │      → returns {"path": "<cache>/<prompt_id>.png", …}
   │
   ├── extract_palette_from_image(path, n_colors=8)
   │      → Pillow median-cut quantization
   │      → returns {"colors": [{"hex": "#3a201a", "percent": 22.5}, …]}
   │
   │ (4) maps anchors onto token ramps (dark → charcoal-*,
   │     warm accent → coral-* or gold-*, app-mode-go/stop)
   │
   ├── write_comfyui_theme(name, overrides, frontend_path)
   │      → writes <frontend>/src/assets/css/themes/<name>.css
   │
   ├── apply_comfyui_theme(name, frontend_path)
   │      → injects @import between sentinels in
   │        <frontend>/src/assets/css/style.css
   │
   │ (5) Vite HMR live-reloads the browser
   │ (6) Hermes summarizes
   ▼
User iterates ("warmer", "less saturated") — Hermes adjusts and
re-applies without regenerating the reference image.
```

If ComfyUI is unreachable or generation fails, the agent skips visual
research and picks palette anchors from the description alone.

## Integration points

**Hermes plugin model.** Plugin discovered at
`~/.hermes/plugins/hermes_comfyui_theme_maker/` (underscored — loaded
as a Python package). `register(ctx)` calls `ctx.register_skill(name,
path)` and `ctx.register_tool(name, toolset, schema, handler)`. Tool
handlers have signature `def handler(args: dict, **kwargs) -> str`,
always return JSON, catch exceptions internally.

**ComfyUI HTTP API.** `POST /prompt` submits a prompt-format workflow
(returns `prompt_id` or `node_errors`); `GET /history/<id>` polls for
completion; `GET /view?filename=…` fetches the generated image. The
workflow we send is a flattened (subgraph-resolved) version of the
user's saved Anima turbo workflow, parameterized by prompt, size, seed.

**ComfyUI_frontend file system.** Themes land in
`<frontend>/src/assets/css/themes/<name>.css`. Apply injects an
`@import` block in `<frontend>/src/assets/css/style.css` between
sentinel comments — idempotent, single source of truth, one theme
active at a time. Vite dev server picks up both files via HMR.

## Failure modes

| Failure | Detection | Response |
|---|---|---|
| ComfyUI unreachable | TCP/HTTP error | Error; agent falls back to text-only generation. |
| Workflow rejected | non-200 from `/prompt` | Echo `node_errors`; same fallback. |
| Generation timeout | poll exceeds 90 s | Error; same fallback. |
| `frontend_path` missing or wrong | no `src/assets/css/style.css` | Error naming the offending path. |
| Pillow / drawbot-skia missing | lazy `ImportError` | Error pointing at `requirements.txt` install command. |

The image-gen path is **optional research**: text-only generation must
always work; visual research enriches when available.
