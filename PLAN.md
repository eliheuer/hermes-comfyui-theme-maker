# Project plan: hermes-comfyui-theme-maker

This document captures the vision, roadmap, and load-bearing decisions for
the project so future coding sessions don't have to relitigate them.

## Vision

Hermes Agent uses ComfyUI as a research and generation partner inside an
agentic loop, producing themes for the ComfyUI frontend that are
**grounded in actual generated visuals** rather than guessed from a
description. The full loop runs on Apple Silicon with no cloud
dependency: a local `llama-server` serving Hermes-4.3-36B-GGUF on Metal,
ComfyUI running its existing Anima/Qwen text-to-image stack on Metal,
and the ComfyUI_frontend dev server live-reloading themes via Vite HMR.

Each tool is doing what it's strongest at:

- **ComfyUI** — image generation. Used here as visual research: a single
  text-to-image call returns an "inspiration" image whose dominant
  colors anchor the theme palette.
- **Hermes Agent** — agentic multi-step planning + tool use. Used here
  to interpret a vague description, decide whether to do visual
  research, orchestrate the generate → analyze → synthesize → apply
  loop, and iterate on user feedback.
- **The skill** — design knowledge. The token taxonomy, cascade rules,
  and design heuristics live in `SKILL.md` so the LLM doesn't have to
  rediscover them per turn.

## What we're building (the agentic loop)

Target end-to-end flow when a user types something like *"make a
campfire theme"* into a `hermes` chat:

1. Hermes loads the `comfyui-theme-maker` skill, reads the design knowledge
   and token taxonomy.
2. Hermes calls `list_comfyui_tokens` to ground itself in the real
   override surface.
3. Hermes plans: *"a campfire vibe is ambiguous; I'll generate a
   reference image to anchor concrete colors."*
4. Hermes calls `generate_mood_image("campfire embers in autumn forest,
   dusk, glowing logs")`. ComfyUI runs its Anima turbo workflow and
   returns a path to the generated PNG.
5. Hermes calls `extract_palette_from_image(path, n_colors=8)`.
   K-means returns 8 dominant hex colors.
6. Hermes designs the theme: maps the dark palette anchors onto the
   `charcoal` ramp, the warm anchors onto a `coral`/`gold` ramp,
   chooses Run/Stop colors, and calls `write_comfyui_theme`.
7. Hermes calls `apply_comfyui_theme`. Vite HMR live-reloads the
   browser. User sees both the reference image and a theme grounded in
   it.
8. User: *"warmer, less green."* Hermes adjusts overrides (no new image
   needed) and re-applies. Iterate until the user is satisfied.

Text-only fallback: if ComfyUI is unreachable or `generate_mood_image`
fails, Hermes skips steps 4–5 and goes straight to text-only theme
generation. The current MVP is exactly this fallback.

## Roadmap

Three layers, ship in order. Each is independently demoable.

### Layer 1 — text-only theme generation (DONE)

- Plugin scaffold: `__init__.py`, `plugin.yaml`, `schemas.py`, `tools.py`,
  `token_inventory.py`.
- Skill: `skills/comfyui-theme-maker/SKILL.md` with token taxonomy, cascade
  rules, design heuristics, worked example.
- Tools: `list_comfyui_tokens`, `write_comfyui_theme`,
  `apply_comfyui_theme`.
- Hand-designed reference theme: `examples/campfire.css`.
- Smoke test: `scripts/smoke_test.py` (15/15 pass against real
  ComfyUI_frontend on PR branch).

### Layer 2 — image-gen palette research (NEXT, today's main build)

- New tool: `generate_mood_image(prompt: str) -> {path, ...}` — submits
  a text-to-image workflow to the local ComfyUI HTTP API, polls for
  completion, returns the generated image path.
- New tool: `extract_palette_from_image(path: str, n_colors: int) ->
  {colors: [hex...]}` — k-means dominant color extraction.
- Workflow template: a parameterizable Anima/Qwen turbo workflow JSON
  derived from the user's existing `image_anima_preview--turbo.app.json`.
- Skill update: extend `SKILL.md` with the visual-research workflow,
  guidance on when to skip the image step, and how to map extracted
  palette anchors onto the token ramps.
- Smoke test extension: add live ComfyUI tests guarded by an env var so
  CI / unattended runs still pass.

### Layer 3 — memory of aesthetic preferences (STRETCH)

- After the user accepts a theme, write a small memory record via
  Hermes' memory subsystem: what mode, what color family, what was
  rejected, what was kept.
- Skill consults memory on subsequent runs. Demo angle: "the agent
  learns your taste over sessions."
- This is a Nous-distinctive hook (their tagline is "self-improving
  AI agent") and ~30 min of work *if* Hermes' memory API is
  ergonomic. Skip if it isn't.

## Time budget for today

Hackathon submission deadline is end of today (2026-05-03). Working
backward:

| Block | Estimate | What |
|---|---|---|
| GGUF download finishes | ~30 min | Background — already running |
| Layer 2 build (`generate_mood_image`) | 60 min | Workflow template extract, HTTP submit + poll, error paths |
| Layer 2 build (`extract_palette_from_image`) | 30 min | Pillow + scikit-learn or numpy k-means |
| Skill update + plugin re-register | 20 min | Document new tools in `SKILL.md` |
| End-to-end smoke against real stack | 30 min | `hermes` → describe vibe → image generated → theme applied |
| Layer 3 (memory) if time | 30 min | Optional |
| Demo capture + submission | 30 min | Screen recording, submission form |

Roughly 3–4 hours of focused build remaining once download finishes.
Scope discipline: layer 2 is the ship gate; layer 3 only if comfortable.

## Load-bearing decisions

Decisions already made and the reasoning, so we don't relitigate.

### Why `llama.cpp` over Ollama or MLX

Nous Research publishes the **official** GGUF for Hermes-4.3-36B
themselves; `llama.cpp` is the engine that format targets. Ollama wraps
`llama.cpp` and adds friction (its own model registry, Modelfile
format). MLX has no Hermes conversion in `mlx-community`. The
hermes-agent quickstart docs reference `llama.cpp` by name (`--ctx-size
65536`). "Use the weights Nous publishes, in the format Nous publishes
them, with the engine they target" is the right Nous-native story.

### Why a Hermes plugin (skill + tools), not MCP

Hermes' extension model has skills (markdown context), tools (Python
functions), MCP servers (external processes), and plugins (the package
that bundles skills + tools). A plugin combining a `SKILL.md` and three
tools is the **Hermes-native** shape — same pattern as the 671 bundled
skills in their repo. MCP would buy portability to Claude Code /
OpenCode at the cost of feeling external; that's not the goal for a
Nous hackathon submission.

### Why CSS custom-property overrides at the palette layer

ComfyUI_frontend already has a clean three-layer token system:

- **Palette** (`_palette.css`) — raw color ramps.
- **Semantic** (`design-system/style.css`) — semantic tokens that
  reference the palette, with separate `:root` (light) and `.dark-theme`
  (dark) blocks.
- **App-mode** (`src/assets/css/style.css`, PR #11317) — local app-mode
  tokens, currently hard-coded hex.

Overriding the palette layer at `:root` cascades through every semantic
token automatically, and the user's existing dark/light toggle keeps
working because semantic tokens still resolve through the inheritance
chain. So our output is always a single CSS file overriding palette
tokens (and a small set of app-mode tokens) — we never touch the
semantic layer.

### Why image-gen-based palette research vs. pure text generation

A text-only path is "Hermes calls an LLM and writes some CSS." It uses
ComfyUI as a host but not as a generator. Adding `generate_mood_image`
+ `extract_palette_from_image` makes ComfyUI's core competency
(diffusion image generation) part of the agentic loop, gives Hermes
real visual anchors instead of guessed colors, and produces a more
compelling demo because there's an actual image being generated on
screen.

### Why the Anima/Qwen aesthetic for mood images

The user's existing local stack is Anima (anime-style fine-tunes of
Qwen Image). Switching to a photorealistic checkpoint (Flux/SD3) means
another ~12 GB download we don't have time for. Anime style is fine for
palette extraction — k-means doesn't care about photorealism, only
pixel colors — and the stylization adds character to the demo rather
than detracting from it.

### Why warm-grounded over neon for the reference theme

User feedback: a synthwave/neon default reads as a tired AI-art trope.
The reference theme `examples/campfire.css` uses burnt-wood neutrals,
ember oranges, and amber yellows. The aesthetic recommendation also
landed in long-term memory so future defaults don't drift back to neon.

### Why Hermes-4-14B (not 4.3-36B) on a 48 GB Mac

We initially picked Hermes-4.3-36B Q4_K_M because Nous publishes the
official GGUF and it's their flagship sub-70B model. **It does not fit
in this hardware envelope.** Discovered live during the hackathon:

- Model in Metal memory: ~22 GB.
- KV cache at the 64K context hermes-agent requires (even with the
  `q8_0` cache-type trick that halves it from fp16): ~10 GB.
- ComfyUI with Anima loaded: ~6–8 GB.
- macOS background, browser, dev servers: ~10 GB baseline.
- Total: ~50 GB on a 48 GB system → wired memory pegs at ~33 GB and
  macOS starts throwing out-of-memory warnings; Metal command buffers
  fail with `kIOGPUCommandBufferCallbackErrorOutOfMemory` mid-prompt.

Switching to **Hermes-4-14B Q4_K_M** (Bartowski's GGUF) drops the
model to ~8.4 GB and KV cache to ~3 GB at the same 64K context.
Total budget becomes ~30 GB instead of ~50 GB — comfortable. 14B
handles the agent flow cleanly because the work is "pick palette
anchors and emit JSON," not deep multi-step reasoning. Quality
difference is real but not load-bearing for this project.

Operational rule: **on 48 GB unified memory with ComfyUI also
running, cap the local LLM at ~14B Q4_K_M.** Bigger models need a
bigger machine or a swap that boots ComfyUI in/out per request.

## Open questions

Resolve when implementing layer 2:

1. **Workflow template extraction.** The user has
   `image_anima_preview--turbo.app.json` saved. Need to convert this from
   the UI workflow format to the API "prompt" format (different
   structure), parameterize the prompt text and image size, and bundle
   it with the plugin.
2. **K-means dependency.** Pillow + numpy is sufficient for k-means
   without scikit-learn, but scikit-learn is one line cleaner. Pick
   based on what's already in the hermes-agent venv vs. needs install.
3. **Image generation latency.** Anima turbo on M4 with the LoRA
   should be ~5–15 seconds for 512×512. Need to confirm and decide on
   an acceptable timeout for `generate_mood_image`.
4. **Iteration without re-generation.** User says "warmer" — Hermes
   should reuse the existing palette anchors and just remix, not
   regenerate the image. Worth making explicit in `SKILL.md`.

## What this project demonstrates

For the hackathon submission:

- **Both tools at full power.** ComfyUI generating images, Hermes
  orchestrating an agentic loop. Neither is a passive host.
- **Local-first.** Every model and every tool runs on the user's M4.
  No cloud dependency, no API keys for the core flow.
- **Plugin-native.** Hermes' first-class skill + tool + plugin model,
  not a generic MCP wrapper.
- **Practical.** The output is a real CSS theme that integrates with an
  active ComfyUI_frontend PR (#11317) — not a toy. The project doubles
  as a forcing function for the upcoming theme-system redesign the PR
  description mentions.
