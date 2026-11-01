"""Result deliveries: their owner lists them and switches one off or on (Settings →
Webhooks), reads one (the chat's card), confirms it (a first message is posted to its
address) or cancels it. Setting an address happens by chat
(``services/chat_tools/deliveries.py``); confirming never does, so a person always clicks
before results leave the server."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from api.schemas.deliveries import DeliveryOut, DeliveryPatch
from api.services.deliveries import service
from api.throttling import user_rate_limit
from api.webhook_deps import Deliveries, DeliverySending

router = APIRouter(prefix="/deliveries", tags=["deliveries"])


@router.get("")
def list_deliveries(access: Deliveries) -> list[DeliveryOut]:
    return [DeliveryOut.model_validate(view) for view in service.views(access)]


@router.get("/{delivery_id}")
def get_delivery(delivery_id: int, access: Deliveries) -> DeliveryOut:
    return DeliveryOut.model_validate(service.view(access, delivery_id))


@router.patch("/{delivery_id}")
def update_delivery(delivery_id: int, body: DeliveryPatch, access: Deliveries) -> DeliveryOut:
    return DeliveryOut.model_validate(service.set_enabled(access, delivery_id, body.enabled))


@router.post("/{delivery_id}/confirm", dependencies=[Depends(user_rate_limit)])
async def confirm_delivery(
    delivery_id: int, access: Deliveries, sending: DeliverySending
) -> DeliveryOut:
    """Post a first message to the address; once it is accepted, every run's result
    goes there (502 ``delivery_failed`` when it is not, and nothing changes). Rate
    limited per account, like every route that reaches out."""
    return DeliveryOut.model_validate(await service.confirm(access, delivery_id, sending))


@router.delete("/{delivery_id}", status_code=204)
def delete_delivery(delivery_id: int, access: Deliveries) -> Response:
    service.remove(access, delivery_id)
    return Response(status_code=204)
