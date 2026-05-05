"""Hermes plugin: ComfyUI theme generator skill + tools."""

from pathlib import Path

from . import schemas, tools

SKILL_NAME = "comfyui-theme-maker"
TOOLSET = "comfyui-theme-maker"


def register(ctx):
    skill_path = Path(__file__).parent / "skills" / SKILL_NAME / "SKILL.md"
    ctx.register_skill(SKILL_NAME, skill_path)

    handlers = [
        ("list_comfyui_tokens", schemas.LIST_COMFYUI_TOKENS, tools.list_comfyui_tokens),
        ("write_comfyui_theme", schemas.WRITE_COMFYUI_THEME, tools.write_comfyui_theme),
        ("apply_comfyui_theme", schemas.APPLY_COMFYUI_THEME, tools.apply_comfyui_theme),
        ("generate_mood_image", schemas.GENERATE_MOOD_IMAGE, tools.generate_mood_image),
        ("extract_palette_from_image", schemas.EXTRACT_PALETTE_FROM_IMAGE, tools.extract_palette_from_image),
        ("render_theme_swatch", schemas.RENDER_THEME_SWATCH, tools.render_theme_swatch),
        ("render_theme_image", schemas.RENDER_THEME_IMAGE, tools.render_theme_image),
    ]
    for name, schema, handler in handlers:
        ctx.register_tool(
            name=name, toolset=TOOLSET, schema=schema, handler=handler,
        )
