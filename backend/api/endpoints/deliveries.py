"""Result deliveries, as their owner's card in the chat shows them: read one, confirm
it (a first message is posted to its address), or cancel it. Setting an address and
switching it happen by chat (``services/chat_tools/deliveries.py``); confirming never
does, so a person always clicks before results leave the server."""

from __future__ import annotations

from fastapi import APIRouter, Response

from api.deps import CurrentUser, DbSession, Secrets
from api.schemas.deliveries import DeliveryOut
from api.services.deliveries import service
from api.services.deliveries.service import DeliveryAccess
from api.webhook_deps import DeliverySending

router = APIRouter(prefix="/deliveries", tags=["deliveries"])


@router.get("/{delivery_id}")
def get_delivery(
    delivery_id: int, user: CurrentUser, session: DbSession, box: Secrets
) -> DeliveryOut:
    return DeliveryOut.model_validate(service.view(DeliveryAccess(session, user, box), delivery_id))


@router.post("/{delivery_id}/confirm")
async def confirm_delivery(
    delivery_id: int,
    user: CurrentUser,
    session: DbSession,
    box: Secrets,
    sending: DeliverySending,
) -> DeliveryOut:
    """Post a first message to the address; once it is accepted, every run's result
    goes there (502 ``delivery_failed`` when it is not, and nothing changes)."""
    access = DeliveryAccess(session, user, box)
    return DeliveryOut.model_validate(await service.confirm(access, delivery_id, sending))


@router.delete("/{delivery_id}", status_code=204)
def delete_delivery(
    delivery_id: int, user: CurrentUser, session: DbSession, box: Secrets
) -> Response:
    service.remove(DeliveryAccess(session, user, box), delivery_id)
    return Response(status_code=204)
