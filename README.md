# hermes-comfyui-theme-maker

Generate cohesive [ComfyUI frontend](https://github.com/Comfy-Org/ComfyUI_frontend)
themes from natural-language descriptions via a
[Hermes Agent](https://hermes-agent.nousresearch.com/) skill plus tools.
The agent drives the loop; ComfyUI generates a reference image; the plugin
extracts the palette and writes a live theme into your dev checkout.

Built for the Hermes Agent Creative Hackathon. Still rough around the edges.

## What it does

- A **skill** (`comfyui-theme-maker`) that loads the canonical ComfyUI token
  taxonomy and design heuristics into Hermes' context.
- Six **tools** the agent calls in an agentic loop:
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
  - `render_theme_swatch` — render a theme as ANSI-colored blocks in
    the terminal, grouped by category. The agent calls this after
    apply so each generation ends with a visual preview in your TUI.
- Targets the three-layer token surface: **palette** (foundational color
  ramps), **semantic** (cascades automatically), and the new **app-mode**
  tokens introduced by ComfyUI_frontend PR #11317
  (`app-mode-semi-customizable-layout`).

## Stack

Three pieces, run roughly independently:

- **Hermes Agent** — drives the conversation, plans the agentic loop,
  calls this plugin's tools. Any LLM backend that hermes-agent supports
  works (cloud or local). Cloud is the recommended path; local needs
  enough memory headroom to coexist with ComfyUI.
- **ComfyUI** — runs locally on your GPU. Generates the mood reference
  image (the visual research) and hosts the frontend you re-skin.
- **ComfyUI_frontend** — your dev checkout running `pnpm dev`. Vite HMR
  applies theme changes live in the browser.

This plugin is the glue: a Hermes Agent **skill** (design knowledge for
the LLM) plus five **tools** the agent calls in order.

## Setup

### 1. Install hermes-agent

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
source ~/.zshrc  # or ~/.bashrc
```

### 2. Pick an LLM backend

Run `hermes model` and walk through the interactive wizard. Any provider
hermes-agent supports works as long as the model can do structured tool
calling. Two paths:

**Cloud (recommended)** — fast, no local memory cost, works anywhere:

- Pick a provider you have credit on: Kimi/Moonshot, Nous Portal,
  OpenRouter, OpenAI, Anthropic, etc.
- Pick a tool-calling-capable model when prompted. Verified working
  during development: **Kimi-K2** (Moonshot). Larger Hermes models on
  Nous Portal also work.
- Set as default.

**Local (advanced)** — runs on your machine, no API calls, but needs
real memory headroom. On a 48 GB Apple Silicon Mac with ComfyUI also
loaded, even the 14B Hermes variant runs into peak-memory pressure
during prompt processing. Reach for this only if you have ≥ 64 GB
unified memory, or are willing to stop ComfyUI between turns.

To run local:

```bash
brew install llama.cpp

mkdir -p ~/models/hermes-4-14b
curl -L --fail -C - --retry 5 \
    https://huggingface.co/bartowski/NousResearch_Hermes-4-14B-GGUF/resolve/main/NousResearch_Hermes-4-14B-Q4_K_M.gguf \
    -o ~/models/hermes-4-14b/NousResearch_Hermes-4-14B-Q4_K_M.gguf

llama-server \
    --model ~/models/hermes-4-14b/NousResearch_Hermes-4-14B-Q4_K_M.gguf \
    --alias Hermes-4-14B-Q4 \
    --ctx-size 65536 \
    -ngl 999 \
    --host 127.0.0.1 \
    --port 8080 \
    --jinja \
    --cache-type-k q8_0 \
    --cache-type-v q8_0
```

Then in `hermes model`, pick **Custom Endpoint**, base URL
`http://127.0.0.1:8080/v1`, model name `Hermes-4-14B-Q4`, API key
anything. The Hermes-4-14B GGUF reports a 40 K context in its metadata
which is below hermes-agent's 64 K minimum, so:

```bash
hermes config set model.context_length 65536
hermes config set auxiliary.compression.context_length 65536
```

### 3. Install this plugin

```bash
# Clone wherever you keep code. The plugin will be referenced by
# absolute path from the symlink below, so the location doesn't matter.
git clone https://github.com/eliheuer/hermes-comfyui-theme-maker.git
cd hermes-comfyui-theme-maker

# Hermes plugin dirs must be valid Python identifiers — symlink with underscores.
mkdir -p ~/.hermes/plugins
ln -s "$(pwd)" ~/.hermes/plugins/hermes_comfyui_theme_maker

# Hermes discovers plugins in this directory but won't load them until
# you explicitly enable them.
hermes plugins enable hermes_comfyui_theme_maker
```

Verify it loaded with `hermes plugins list` (status should be
`enabled`), `hermes skills list` (should include `comfyui-theme-maker`), and
`hermes tools list` (should include all five tools above).

The plugin imports Pillow at runtime for palette extraction. If your
hermes-agent venv doesn't already have it:

```bash
~/.hermes/hermes-agent/venv/bin/pip install Pillow
```

### 4. Tell the agent where your ComfyUI_frontend lives

There's no env var or config to set up — the agent just asks. On the
first theme request of a session, Hermes will say something like:

> Where is your ComfyUI_frontend checkout? e.g. `~/code/ComfyUI_frontend`

Tell it the absolute path. The agent saves it to memory for future
sessions, so you only get asked once per machine.

> **Scope note:** this plugin currently targets a **dev checkout** of
> ComfyUI_frontend (the source tree you'd run `pnpm dev` against), not
> a regular installed ComfyUI's bundled production UI. Themes apply
> via Vite HMR on the dev server. Skinning a non-dev ComfyUI install
> would need to plug into ComfyUI's runtime CSS injection mechanism
> instead — that's a future direction.

### 5. Start ComfyUI_frontend

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
> Use the comfyui-theme-maker skill to make me a warm campfire theme.
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

- **LLM backend**: Kimi-K2 (Moonshot, cloud) — verified working
  end-to-end during the hackathon. Local Hermes-4-14B GGUF also runs
  but is memory-tight alongside ComfyUI on 48 GB hardware.
- **ComfyUI image gen**: the workflow template wired into `tools.py`
  targets the **Anima / Qwen** text-to-image stack
  (`anima-preview.safetensors`, `qwen_3_06b_base.safetensors`,
  `qwen_image_vae.safetensors`, `anima-turbo-lora-v0.1.safetensors`).
  Other ComfyUI installs (Flux, SDXL, etc.) would need the workflow
  template swapped — generalising this is future work.
- **ComfyUI_frontend**: `main` and PR #11317 branch
  `app-mode-semi-customizable-layout` in graph mode, app mode, and
  builder mode.

## Project documentation

- [`PLAN.md`](./PLAN.md) — vision and load-bearing design decisions.
- [`docs/architecture.md`](./docs/architecture.md) — component map,
  data flow, file layout, integration points, failure modes.

## License

GPL-3.0-or-later. See [LICENSE](./LICENSE).
