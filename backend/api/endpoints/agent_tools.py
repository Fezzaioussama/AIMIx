"""Authenticated tool catalogue for the pipeline builder."""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import ToolCatalog
from api.schemas.agent_tools import ToolDescriptorOut

router = APIRouter(prefix="/agent-tools", tags=["agent-tools"])


@router.get("")
async def list_agent_tools(catalog: ToolCatalog) -> list[ToolDescriptorOut]:
    return [ToolDescriptorOut.model_validate(tool) for tool in await catalog.available()]
