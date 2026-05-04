# Project plan: hermes-comfyui-theme-maker

Vision and load-bearing decisions. The README covers what the plugin is
and how to use it; this doc covers why it's shaped the way it is.

## Vision

Hermes Agent uses ComfyUI as a research and generation partner inside an
agentic loop, producing themes for the ComfyUI frontend that are
**grounded in actual generated visuals** rather than guessed from a
description. Image generation, file I/O, and live-preview run locally
on Apple Silicon (ComfyUI text-to-image on Metal, ComfyUI_frontend dev
server via Vite HMR); the LLM brain driving Hermes can run locally
OR via cloud — whichever fits the user's hardware and budget.

Each piece does what it's strongest at:

- **ComfyUI** — image generation as visual research. A single text-to-
  image call returns an inspiration image whose dominant colors anchor
  the theme palette.
- **Hermes Agent** — multi-step planning and tool use. Interprets the
  user's description, orchestrates the generate → analyze → synthesize
  → apply loop, iterates on feedback.
- **The skill** — design knowledge. Token taxonomy, cascade rules, and
  design heuristics live in `SKILL.md` so the LLM doesn't have to
  rediscover them per turn.

## Load-bearing decisions

### Cloud LLM is the practical path

The original plan was fully local. On a 48 GB Mac with ComfyUI also
running, this didn't survive contact with reality: Hermes-4.3-36B
Q4_K_M (~22 GB) OOMs Metal mid-prompt; Hermes-4-14B Q4_K_M (~8.4 GB)
survives idle but prompt-processing peaks throw memory warnings, and
14B's tool-calling reliability is marginal.

Cloud LLM for the brain (Kimi-K2 verified, Nous Portal Hermes
equivalent) plus local for everything else gets faster turn-around,
no memory pressure, and more reliable structured tool calls. Local
LLM remains documented as an "≥ 64 GB unified memory" alternative.

### Hermes plugin (skill + tools), not MCP

A plugin combining a `SKILL.md` and tools is the Hermes-native shape —
same pattern as the bundled skills shipped with hermes-agent. MCP
would buy portability to other agents at the cost of feeling
external; not the goal for a Nous-aligned submission.

### CSS overrides at the palette layer

ComfyUI_frontend has a clean three-layer token system: raw palette
(`charcoal-*`, `smoke-*`, …), semantic tokens that reference the
palette with separate `:root` (light) and `.dark-theme` (dark)
blocks, and the new app-mode tokens from PR #11317. Overriding the
palette at `:root` cascades through every semantic token, and the
existing dark/light toggle keeps working because semantic tokens
still resolve through the inheritance chain. Output is always one
CSS file overriding palette + app-mode tokens; we never touch the
semantic layer.

### Image-gen-grounded palette vs. text-only

Letting the LLM guess colors from a description uses ComfyUI as a
passive host. Generating a real image and extracting its palette uses
ComfyUI's actual strength. Themes feel coherent because they have a
visual *source*; the agentic loop grows naturally.

### `frontend_path` as an explicit tool argument

Earlier iterations hardcoded user-specific paths, then auto-detected
via candidate lists. Both designs were wrong: hidden state, brittle
defaults. The right answer for an agent is to ask the user once
(saving the answer to memory), then pass the path to every tool
call. No env vars, no candidate lists, no setup.

### Anime mood-image aesthetic (current install constraint)

The Anima/Qwen text-to-image stack is hardcoded into the workflow
template in `tools.py`. This was the user's existing local stack;
photorealistic checkpoints would require another large download. For
palette extraction the stylization doesn't matter — k-means cares
about pixel colors only. Generalizing the workflow template to other
ComfyUI installs is future work.
