# hermes-comfyui-theme-maker

Generate cohesive [ComfyUI frontend](https://github.com/Comfy-Org/ComfyUI_frontend)
themes from natural-language descriptions via a
[Hermes Agent](https://hermes-agent.nousresearch.com/) skill plus tools.
The agent drives the loop; ComfyUI generates a reference image; the plugin
extracts the palette and writes a live theme into your dev checkout.

Built for the Hermes Agent Creative Hackathon. Still rough around the edges.

## What it does

A skill (`comfyui-theme-maker`) that loads the canonical ComfyUI
palette schema and design heuristics into Hermes' context, plus seven
tools the agent calls in an agentic loop:

- `list_comfyui_tokens` — return the canonical schema keys per group
  (`node_slot`, `litegraph_base`, `comfy_base`).
- `generate_mood_image` — generate a reference image via your local
  ComfyUI text-to-image stack to anchor palette decisions in real
  pixels rather than guessed colors.
- `extract_palette_from_image` — median-cut quantization on the
  reference image; returns dominant hex colors with weights.
- `write_comfyui_theme` — save a palette JSON in canonical schema to
  the local cache.
- `apply_comfyui_theme` — register the palette via ComfyUI's settings
  HTTP API (`Comfy.CustomColorPalettes`) and set it active. Theme
  appears in Settings → Appearance → Color Palette.
- `render_theme_swatch` — ANSI-colored TUI preview of a theme, grouped
  by schema group. Called automatically after every apply.
- `render_theme_image` — 1080×1080 PNG infographic of a theme. On
  request only (e.g. for sharing).

**Output format is the canonical ComfyUI palette JSON** — the same
shape used by built-in palettes (`src/assets/palettes/*.json`) and
every community theme repo (shahshrey, sizzlebop, gmorks, civitai,
…). Generated themes are drop-in compatible with the existing
ecosystem.

## Stack

- **Hermes Agent** — drives the conversation, plans the loop. Any LLM
  backend hermes-agent supports works (cloud or local).
- **ComfyUI** — runs locally; generates the mood reference image and
  hosts the frontend you re-skin.
- **ComfyUI_frontend** — your dev checkout running `pnpm dev`. Vite HMR
  applies theme changes live.

## Setup

### 1. Install hermes-agent

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
source ~/.zshrc  # or ~/.bashrc
```

### 2. Pick an LLM backend

Run `hermes model` and walk the wizard. Any tool-calling-capable model
hermes-agent supports works.

**Cloud (recommended)** — pick a provider you have credit on (Kimi/
Moonshot, Nous Portal, OpenRouter, etc.) and a model. Verified working:
**Kimi-K2** (Moonshot).

**Local (advanced)** — needs ≥ 64 GB unified memory to coexist with
ComfyUI; even 14B Hermes is memory-tight on 48 GB.

```bash
brew install llama.cpp

mkdir -p ~/models/hermes-4-14b
curl -L --fail -C - --retry 5 \
    https://huggingface.co/bartowski/NousResearch_Hermes-4-14B-GGUF/resolve/main/NousResearch_Hermes-4-14B-Q4_K_M.gguf \
    -o ~/models/hermes-4-14b/NousResearch_Hermes-4-14B-Q4_K_M.gguf

llama-server \
    --model ~/models/hermes-4-14b/NousResearch_Hermes-4-14B-Q4_K_M.gguf \
    --alias Hermes-4-14B-Q4 \
    --ctx-size 65536 -ngl 999 --jinja \
    --cache-type-k q8_0 --cache-type-v q8_0 \
    --host 127.0.0.1 --port 8080
```

In `hermes model`: pick **Custom Endpoint**, base URL
`http://127.0.0.1:8080/v1`, model name `Hermes-4-14B-Q4`, API key
anything. The 14B GGUF reports 40 K context (below hermes-agent's 64 K
minimum); override after the wizard:

```bash
hermes config set model.context_length 65536
hermes config set auxiliary.compression.context_length 65536
```

### 3. Install this plugin

```bash
git clone https://github.com/eliheuer/hermes-comfyui-theme-maker.git
cd hermes-comfyui-theme-maker

# Hermes plugin dirs must be valid Python identifiers — symlink with underscores.
mkdir -p ~/.hermes/plugins
ln -s "$(pwd)" ~/.hermes/plugins/hermes_comfyui_theme_maker
hermes plugins enable hermes_comfyui_theme_maker
```

Verify:

```bash
hermes plugins list | grep hermes_comfyui_theme_maker  # status: enabled
hermes tools list   | grep comfyui-theme-maker         # 7 tools
```

### 4. Install runtime dependencies into hermes-agent's venv

Pillow + drawbot-skia. Use the **full path** to hermes-agent's pip;
shell `pip` installs into the wrong Python:

```bash
~/.hermes/hermes-agent/venv/bin/pip install -r requirements.txt
~/.hermes/hermes-agent/venv/bin/python -c "import PIL, drawbot_skia; print('ok')"
```

The plugin imports these lazily, so it loads regardless — only the two
tools that need them error until installed.

### 5. Make sure ComfyUI is running

The plugin talks to ComfyUI's HTTP API (default
`http://127.0.0.1:8188`) for both image generation and registering
themes. Override with `HERMES_COMFYUI_API_URL=...` if your install
listens elsewhere.

The plugin no longer needs a `ComfyUI_frontend` checkout — themes
register via the settings API and appear in the standard theme menu
just like any imported community palette.

## Usage

```bash
hermes
```

In the chat:

```
> Make me a warm campfire theme.
```

The agent calls `generate_mood_image` (~15-25 s of ComfyUI work),
extracts a palette, maps it onto the canonical schema, writes a
palette JSON, registers it via ComfyUI's settings API, and renders
the ANSI swatch. The theme appears in Settings → Appearance → Color
Palette and is active. Iterate by saying "warmer", "less saturated"
— the agent rewrites and re-registers without regenerating the
reference image.

If ComfyUI is unreachable, the agent falls back to text-only theme
generation.

## Examples

[`examples/campfire.json`](./examples/campfire.json) is a
hand-designed warm-dark reference theme in the canonical schema.
Import it via Settings → Appearance → Color Palette → Import, or
copy into ComfyUI's user settings dir to preload it.

## Tested against

- **LLM**: Kimi-K2 (cloud), verified end-to-end. Local
  Hermes-4-14B GGUF runs but is memory-tight alongside ComfyUI on 48 GB.
- **ComfyUI image gen**: the workflow template in `tools.py` targets
  the **Anima / Qwen** stack (`anima-preview.safetensors`,
  `qwen_3_06b_base.safetensors`, `qwen_image_vae.safetensors`,
  `anima-turbo-lora-v0.1.safetensors`). Other installs (Flux, SDXL,
  etc.) would need the workflow swapped — future work.
- **Output format**: canonical ComfyUI palette JSON, drop-in
  compatible with built-in palettes and community theme repos.
- **Settings API**: ComfyUI single-user mode (default).

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
HERMES_COMFYUI_FRONTEND_PATH=/path/to/ComfyUI_frontend \
    .venv/bin/python scripts/smoke_test.py
```

21 checks; reverts style.css on exit. `.venv/` is gitignored.

## Project documentation

- [`PLAN.md`](./PLAN.md) — vision and load-bearing design decisions.
- [`docs/architecture.md`](./docs/architecture.md) — component map,
  data flow, integration points, failure modes.
- [`docs/comfyui-theme-system.md`](./docs/comfyui-theme-system.md) —
  reference for ComfyUI's existing theme / palette system: schema,
  bootstrap timeline, light/dark mechanics, PrimeVue layering,
  community ecosystem, test coverage.
- [`docs/upstream-pr-opportunities.md`](./docs/upstream-pr-opportunities.md)
  — concrete PRs against `Comfy-Org/ComfyUI_frontend` surfaced by the
  research, with code-shape sketches, file lists, and a sequencing
  recommendation. Anchored to upstream issue
  [#11048](https://github.com/Comfy-Org/ComfyUI_frontend/issues/11048).

## License

GPL-3.0-or-later. See [LICENSE](./LICENSE).
