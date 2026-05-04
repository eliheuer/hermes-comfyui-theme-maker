"""Hermes plugin: ComfyUI theme generator skill + tools."""

from pathlib import Path

from . import schemas, tools

SKILL_NAME = "comfyui-theme"
TOOLSET = "comfyui-theme"


def register(ctx):
    skill_path = Path(__file__).parent / "skills" / SKILL_NAME / "SKILL.md"
    ctx.register_skill(SKILL_NAME, skill_path)

    ctx.register_tool(
        name="list_comfyui_tokens",
        toolset=TOOLSET,
        schema=schemas.LIST_TOKENS,
        handler=tools.list_tokens,
    )
    ctx.register_tool(
        name="write_comfyui_theme",
        toolset=TOOLSET,
        schema=schemas.WRITE_THEME,
        handler=tools.write_theme,
    )
    ctx.register_tool(
        name="apply_comfyui_theme",
        toolset=TOOLSET,
        schema=schemas.APPLY_THEME,
        handler=tools.apply_theme,
    )
    ctx.register_tool(
        name="generate_mood_image",
        toolset=TOOLSET,
        schema=schemas.GENERATE_MOOD_IMAGE,
        handler=tools.generate_mood_image,
    )
    ctx.register_tool(
        name="extract_palette_from_image",
        toolset=TOOLSET,
        schema=schemas.EXTRACT_PALETTE_FROM_IMAGE,
        handler=tools.extract_palette_from_image,
    )
