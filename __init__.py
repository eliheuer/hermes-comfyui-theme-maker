"""Hermes plugin: ComfyUI theme generator skill + tools."""

from pathlib import Path

from . import schemas, tools

SKILL_NAME = "comfyui-theme"
TOOLSET = "comfyui-theme"


def register(ctx):
    skill_md = (
        Path(__file__).parent / "skills" / SKILL_NAME / "SKILL.md"
    ).read_text()
    ctx.register_skill(SKILL_NAME, skill_md)

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
