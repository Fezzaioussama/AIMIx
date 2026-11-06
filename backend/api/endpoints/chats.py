"""The chats a person keeps (the Chat screen's list): list, open, name and delete
them. Each endpoint validates, calls the service and shapes the result (AGENTS.md
§2); the messages themselves are exchanged through ``POST /chat``."""

from __future__ import annotations

from fastapi import APIRouter, Response

from api.deps import Chats
from api.schemas.chat import ChatDetailOut, ChatIn, ChatOut, ChatPatch
from api.services import chats as service

router = APIRouter(prefix="/chats", tags=["chats"])


@router.get("")
def list_chats(access: Chats) -> list[ChatOut]:
    return [ChatOut.model_validate(chat) for chat in service.list_chats(access)]


@router.post("", status_code=201)
def create_chat(body: ChatIn, access: Chats) -> ChatOut:
    return ChatOut.model_validate(service.create(access, body.title))


@router.get("/{chat_id}")
def get_chat(chat_id: int, access: Chats) -> ChatDetailOut:
    return ChatDetailOut.model_validate(service.open_chat(access, chat_id))


@router.patch("/{chat_id}")
def rename_chat(chat_id: int, body: ChatPatch, access: Chats) -> ChatOut:
    return ChatOut.model_validate(service.rename(access, chat_id, body.title))


@router.delete("/{chat_id}", status_code=204)
def delete_chat(chat_id: int, access: Chats) -> Response:
    service.delete(access, chat_id)
    return Response(status_code=204)
