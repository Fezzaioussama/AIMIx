"""Public descriptions of tools that pipeline agents may call."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ToolDescriptorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    description: str
    source: str
