# hermes-comfyui-theme-maker

Generate cohesive [ComfyUI frontend](https://github.com/Comfy-Org/ComfyUI_frontend)
themes from natural-language descriptions, fully locally on Apple Silicon, via
a [Hermes Agent](https://hermes-agent.nousresearch.com/) skill plus tools.

Built for the Hermes Agent Creative Hackathon.

## What it does

- A **skill** (`comfyui-theme`) that loads the canonical ComfyUI token
  taxonomy and design heuristics into Hermes' context.
- Five **tools** the agent calls in an agentic loop:
  - `list_comfyui_tokens` — return every overridable CSS custom property.
  - `generate_mood_image` — generate a reference image via your local
    ComfyUI text-to-image stack to anchor palette decisions in real
    pixels rather than guessed colors.
  - `extract_palette_from_image` — median-cut quantization on the
    reference image, returns dominant hex colors with weights.
  - `write_comfyui_theme` — write a theme file to your ComfyUI_frontend
    checkout.
  - `apply_comfyui_theme` — activate the theme via a single `@import`,
    picked up by Vite HMR.
- Targets the three-layer token surface: **palette** (foundational color
  ramps), **semantic** (cascades automatically), and the new **app-mode**
  tokens introduced by ComfyUI_frontend PR #11317
  (`app-mode-semi-customizable-layout`).

## Stack — fully local on Mac M-series

- **llama.cpp** (Metal) serving
  [Hermes-4-14B-GGUF](https://huggingface.co/bartowski/NousResearch_Hermes-4-14B-GGUF)
  (Bartowski's quants of the Nous Research model). 14B is the right
  size on a 48 GB M4 with ComfyUI also running — the 36B variant maxes
  out unified memory once Metal-locked KV cache and ComfyUI's
  loaded weights are in play.
- **hermes-agent** CLI driving the conversation, pointed at the local
  llama-server endpoint.
- **ComfyUI** running locally for both (a) hosting the frontend we
  re-skin and (b) generating mood reference images that anchor each
  theme's palette.
- This plugin packaged as a Hermes skill + toolset.
- Your existing **ComfyUI_frontend** Vite dev server for live preview.

## Setup

### 1. Install llama.cpp and the Hermes model

```bash
brew install llama.cpp

# Q4_K_M (~8.4 GB). The right size on a 48 GB M4 with ComfyUI loaded.
mkdir -p ~/models/hermes-4-14b
curl -L --fail -C - --retry 5 \
    https://huggingface.co/bartowski/NousResearch_Hermes-4-14B-GGUF/resolve/main/NousResearch_Hermes-4-14B-Q4_K_M.gguf \
    -o ~/models/hermes-4-14b/NousResearch_Hermes-4-14B-Q4_K_M.gguf
```

The 36B variant (`NousResearch/Hermes-4.3-36B-GGUF`) is technically
sharper, but on 48 GB unified memory the 22 GB model + 64K context KV
cache + Metal-locked ComfyUI weights blow past the ceiling. 14B
handles agentic tool-calling for this project comfortably.

### 2. Start the inference server

```bash
llama-server \
    --model ~/models/hermes-4-14b/NousResearch_Hermes-4-14B-Q4_K_M.gguf \
    --ctx-size 65536 \
    -ngl 999 \
    --host 127.0.0.1 \
    --port 8080 \
    --jinja \
    --cache-type-k q8_0 \
    --cache-type-v q8_0
```

Flags worth knowing:

- `--ctx-size 65536` — hermes-agent requires a 64K-token context at
  minimum.
- `-ngl 999` — offload every layer to Metal (full GPU acceleration).
- `--jinja` — required for tool calling; enables Jinja chat templates
  so OpenAI-style `tool_calls` round-trip correctly.
- `--cache-type-k q8_0 --cache-type-v q8_0` — store the KV cache in
  8-bit instead of 16-bit; halves cache memory at negligible quality
  cost. Important on tight RAM.

This exposes an OpenAI-compatible endpoint at `http://127.0.0.1:8080`.

### 3. Install hermes-agent

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
source ~/.zshrc  # or ~/.bashrc
```

Then run `hermes model` and walk through the interactive wizard:

- Pick **Custom Endpoint** (the OpenAI-compatible / VLLM / Ollama
  category).
- Base URL: `http://127.0.0.1:8080/v1`
- Model name: `NousResearch_Hermes-4-14B-Q4_K_M.gguf`
- API key: any string (the local server doesn't check) — `sk-noauth`
  is fine.
- Set as default.

### 4. Install this plugin

```bash
git clone https://github.com/eliheuer/hermes-comfyui-theme-maker.git \
    ~/GH/repos/hermes-comfyui-theme-maker

# Hermes plugin dirs must be valid Python identifiers — symlink with underscores.
mkdir -p ~/.hermes/plugins
ln -s ~/GH/repos/hermes-comfyui-theme-maker \
      ~/.hermes/plugins/hermes_comfyui_theme_maker

# Hermes discovers plugins in this directory but won't load them until
# you explicitly enable them.
hermes plugins enable hermes_comfyui_theme_maker
```

Verify it loaded with `hermes plugins list` (status should be
`enabled`), `hermes skills list` (should include `comfyui-theme`), and
`hermes tools list` (should include all five tools above).

The plugin imports Pillow at runtime for palette extraction. If your
hermes-agent venv doesn't already have it:

```bash
~/.hermes/hermes-agent/venv/bin/pip install Pillow
```

### 5. Point the plugin at your ComfyUI_frontend checkout

The default is `~/Work/comfy/repos/ComfyUI_frontend`. Override with:

```bash
export HERMES_COMFYUI_FRONTEND_PATH=/path/to/your/ComfyUI_frontend
```

### 6. Start ComfyUI_frontend

In a separate terminal:

```bash
cd /path/to/ComfyUI_frontend
pnpm dev
```

## Usage

```bash
hermes
```

Then in the chat:

```
> Use the comfyui-theme skill to make me a warm campfire theme.
  Use the visual-research workflow: generate a mood image first,
  extract its palette, then write and apply the theme.
```

Hermes will run the agentic loop:

1. Call `list_comfyui_tokens` to ground itself in the real token surface.
2. Plan a mood prompt for the diffusion model.
3. Call `generate_mood_image(...)` — ComfyUI generates a reference PNG
   via your installed text-to-image stack (~15-25 s).
4. Call `extract_palette_from_image(...)` — median-cut quantization
   returns the dominant colors with weights.
5. Map extracted colors onto ramps using the design heuristics in
   `SKILL.md` (dark anchors → `charcoal-*`, warm accents → `coral-*`
   or `gold-*`, etc.) and call
   `write_comfyui_theme(name=…, overrides=…)`.
6. Call `apply_comfyui_theme(name=…)`.

Vite HMR live-reloads the browser. Iterate by saying "make it warmer"
or "less saturated" — Hermes will rewrite and re-apply without
re-generating the reference image.

If ComfyUI isn't running or image generation fails, Hermes falls back
to text-only theme generation and tells you so in the summary.

## Examples

`examples/` contains hand-designed reference themes you can apply
directly without running Hermes — useful as known-good baselines to
compare against LLM output, or for offline preview.

- [`campfire.css`](./examples/campfire.css) — warm dark theme. Charcoal
  ramp shifted to burnt-wood browns, coral and gold ramps tuned to ember
  oranges and amber yellows, forest-green Run / warm-red Stop.

To apply one manually:

```bash
cp examples/campfire.css \
   "$HERMES_COMFYUI_FRONTEND_PATH/src/assets/css/themes/"
```

Then in `hermes`: `apply_comfyui_theme(name="campfire")`. Or add the
`@import` line to `style.css` by hand.

## How it works

ComfyUI_frontend exposes a clean three-layer CSS custom-property system:

1. **Palette** (`_palette.css`) — raw color ramps (`charcoal-*`,
   `smoke-*`, etc.).
2. **Semantic** (`design-system/style.css`) — semantic tokens that
   reference the palette (`base-foreground`, `secondary-background`, …).
3. **App-mode** (`src/assets/css/style.css`) — local tokens for the new
   App Mode redesign (`--app-mode-go-*`, `--app-mode-widget-*`).

This plugin emits a single `theme.css` file that overrides tokens at the
palette and app-mode layers. The semantic layer cascades automatically.
`apply` injects one `@import` line into `style.css` between sentinel
comments — idempotent, removable, single source of truth.

> **Heads up:** `apply_comfyui_theme` modifies your tracked
> `src/assets/css/style.css`. To revert: `git restore
> src/assets/css/style.css`.

## Tested against

- ComfyUI_frontend `main`
- ComfyUI_frontend PR #11317 branch `app-mode-semi-customizable-layout`
  in graph mode, app mode, and builder mode

## Project documentation

For the design vision, roadmap, and load-bearing decisions:

- [`PLAN.md`](./PLAN.md) — vision, roadmap (current MVP / next /
  stretch), time budget, decisions with rationale, open questions.
- [`docs/architecture.md`](./docs/architecture.md) — component map,
  end-to-end data flow, file layout, integration points, tool
  inventory, failure modes.
- [`docs/comfyui-api-notes.md`](./docs/comfyui-api-notes.md) — ComfyUI
  HTTP API reference for the planned image-gen tools.

## License

GPL-3.0-or-later. See [LICENSE](./LICENSE).
