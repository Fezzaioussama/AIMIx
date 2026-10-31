"""The signed-in user's account: change its password, take a copy of its data,
delete it (GDPR art. 15, 17 and 20). Each endpoint validates, calls the account
services and shapes the result (AGENTS.md §2).

Each one checks a password or reads everything the account holds, so each is
rate-limited per account (``user_rate_limit``); a wrong password also counts
toward the account's sign-in lockout (AUTH_ACCOUNT_FAILURE_LIMIT).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from api.deps import Account, Now, Signer
from api.endpoints.auth import clear_refresh_cookie, set_refresh_cookie
from api.schemas.account import AccountDeleteIn, AccountExportOut, PasswordChangeIn
from api.schemas.auth import AccessTokenResponse
from api.services import account_data, accounts
from api.throttling import one_export_at_a_time, user_rate_limit

router = APIRouter(prefix="/account", tags=["account"], dependencies=[Depends(user_rate_limit)])


@router.post("/password")
def change_password(
    body: PasswordChangeIn, response: Response, account: Account, signer: Signer
) -> AccessTokenResponse:
    """Every other session ends; this one goes on with the new token pair."""
    policy = accounts.sign_in_policy(account.settings)
    change = accounts.PasswordChange(body.current_password, body.new_password, policy)
    tokens = accounts.change_password(account.session, signer, account.user, change)
    set_refresh_cookie(response, tokens.refresh, account.settings)
    return AccessTokenResponse(access=tokens.access)


@router.get(
    "/export",
    dependencies=[Depends(one_export_at_a_time)],
    responses={200: {"model": AccountExportOut}},
)
def export_account(account: Account, now: Now) -> Response:
    """Everything the account holds, as a JSON file to save."""
    options = account_data.ExportOptions(now, account.settings.account_export_max_chars)
    export = account_data.export_account(account.session, account.user, account.files, options)
    return Response(
        AccountExportOut.model_validate(export).model_dump_json(),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="aimix-account-{now:%Y-%m-%d}.json"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/delete", status_code=204)
def delete_account(body: AccountDeleteIn, response: Response, account: Account) -> None:
    """Delete the account, its files and everything it owns; this cannot be undone."""
    given = accounts.GivenPassword(body.password)
    policy = accounts.sign_in_policy(account.settings)
    accounts.confirm_password(account.session, account.user, given, policy)
    account_data.delete_account(account.session, account.user, account.files)
    clear_refresh_cookie(response, account.settings)
