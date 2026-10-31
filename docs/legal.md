# Legal pages and data-protection requests

The app serves three public pages, in French (the operator's jurisdiction):
`/legal` (mentions légales), `/privacy` (politique de confidentialité, cookies
included) and `/terms` (conditions générales d'utilisation). The landing footer,
the sign-in and sign-up cards and the Settings page link to all three; the
sign-up card says which terms and policy apply before an account is created.

This is not legal advice. The texts describe what the code does; the business
facts and the choices below are the operator's, ideally checked by a lawyer.

## Where the text lives

| File | What it holds |
|---|---|
| `frontend/src/features/legal/operator.ts` | `OPERATOR`: every fact about who runs the service. `null` shows on the pages as a visible "[à compléter : …]" marker, and the pages carry a "Version provisoire" note while any fact is missing |
| `frontend/src/features/legal/documents/*.ts` | The three documents, Markdown with `{{fact}}` placeholders (`fillFacts`) |
| `frontend/src/core/routes.ts` | `LEGAL_LINKS`: the three paths and their link labels |

A placeholder that names no fact fails the tests (`fillFacts.test.ts`), so a typo
never ships.

## Facts to fill before opening to the public

| Fact | Why it is asked |
|---|---|
| `name`, `legalForm`, `address`, `registration`, `vatNumber`, `phone`, `publicationDirector` | LCEN art. 1-1 (formerly 6 III): name, address, telephone, RCS/RNE number, share capital for a company, and the publication director. A paid service is a professional one: its operator cannot stay anonymous. Sole traders show "EI" and their RNE/SIREN; a regular paid activity must be registered in the RNE |
| `host` | LCEN art. 1-1: the host's name, address and telephone. The repository deploys on Railway (`railway.json`); confirm the account and use Railway's legal details |
| `contactEmail`, `contactLanguages` | GDPR requests (art. 12), illegal-content reports and the single point of contact a hosting service owes users and authorities (DSA art. 11, 12, 16) |
| `dataLocation` | Where the Railway service, its volume (the SQLite database and users' files) and any backup are. Railway offers an EU West (Amsterdam) region; a volume stays in its service's region |
| `dataProtectionOfficer` | GDPR art. 13: the DPO's contact, or a sentence saying none is designated |
| `serverLogRetention`, `backupRetention` | GDPR art. 13 and 5(1)(e): how long Railway keeps the access logs Uvicorn writes (IP address, path, status) and how long backups keep deleted data |
| `transferSafeguards` | GDPR art. 44–49: OpenRouter, Together AI, Tavily, E2B and Railway process data in the US. Name the safeguard for each (EU-US Data Privacy Framework certification, or standard contractual clauses in its DPA) |
| `pricing` | Price, billing, renewal, or that the service is free. Paid consumer contracts bring the pre-contract information, the 14-day withdrawal right with its online withdrawal function, and the online cancellation function (Code de la consommation L221-5, L221-18, L221-21, L215-1-1) |
| `minimumAge` | Who may open an account (18 is the prudent default for a contract) |
| `consumerMediator` | A consumer mediator is required when consumers are customers (L612-1, L616-1). The EU ODR-platform link is no longer required |
| `competentCourt` | Courts for disputes with professional customers |

## Keeping the pages true

The privacy policy quotes the code's behaviour and these defaults. Change the text
when you change them:

| Setting or code | Quoted as |
|---|---|
| `REFRESH_COOKIE_NAME`, `JWT_REFRESH_DAYS` | The `aimix_refresh` cookie, 1 day |
| `missionStorage.ts` prefix | The `aimix.mission.v1.*` session storage |
| `AUTH_*`, `REGISTRATION_*`, `USER_RATE_LIMIT_*` windows | Rate-limit fingerprints kept for their window ("une heure au plus"), then pruned as later requests come (`repositories/rate_limits.py`) |
| `AGENT_BUILTIN_TOOLS`, `TAVILY_API_KEY`, `E2B_API_KEY` | The search and sandbox services named as recipients |
| `ALLOW_SERVER_LLM_KEY` | Off: model calls run under the user's own provider account. Turning it on makes the provider the operator's processor, so add it to the recipients and transfers |

Adding a tracker of any kind (analytics, an embedded video, a remote font) needs
consent first under loi 78-17 art. 82, and the Content-Security-Policy in
`backend/api/middleware.py` blocks it until the policy is changed on purpose.

## Answering a data-protection request

Signed-in users serve themselves on **Settings → Account**: download a copy of
everything the account holds (`GET /api/account/export`; files are listed and
downloaded from the Files page), change the password, delete the account
(`POST /api/account/delete`). An account past `ACCOUNT_EXPORT_MAX_CHARS` is refused
the in-app copy and gets one from you. Someone who cannot sign in writes to the
contact address; once you have checked that the account is theirs, run in
the service shell (Railway: `docker-entrypoint.sh` runs it as the app user):

```bash
docker-entrypoint.sh python -m api.cli export-user USERNAME > export.json
docker-entrypoint.sh python -m api.cli delete-user USERNAME   # asks for the name again
```

Answer within one month (GDPR art. 12(3)). A deletion is immediate in the
database and the files; backups keep the data for `backupRetention`.

## Generated content

Model output is labelled in the app (`core/ui/AiNotice.tsx`: chat, run results,
mission deliverables), and the PDF and Word files agents save carry
"AI-generated" in their metadata (`api/services/artifacts/contracts.py`). AI Act
art. 50 applies from 2 August 2026; for systems already on the market, the
machine-readable marking of art. 50(2) is due by 2 December 2026. Markdown, text
and CSV artifacts, chat replies and API responses carry no machine-readable mark
yet: check the Commission's Code of Practice on transparency of AI-generated
content before that date.
