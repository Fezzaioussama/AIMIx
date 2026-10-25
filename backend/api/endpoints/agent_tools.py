"""Authenticated tool catalogue for the pipeline builder. Listing opens a
connection to every MCP server the user can reach, so it is rate-limited per
account (``user_rate_limit``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import ToolCatalog, user_rate_limit
from api.schemas.agent_tools import ToolDescriptorOut

router = APIRouter(prefix="/agent-tools", tags=["agent-tools"])


@router.get("", dependencies=[Depends(user_rate_limit)])
async def list_agent_tools(catalog: ToolCatalog) -> list[ToolDescriptorOut]:
    return [ToolDescriptorOut.model_validate(tool) for tool in await catalog.available()]
