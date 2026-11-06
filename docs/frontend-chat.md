# Frontend: the Chat screen

The Chat screen at `/chat`: a conversation with the assistant that builds and runs
workflows by talking. The chats live on the server (`/api/chats`, see
[api-reference.md](api-reference.md#chats)), so one can be opened again from any tab or
device, and the assistant remembers a long one through its own notes
([backend.md](backend.md#services), `chat_memory`). This page covers `features/chat`;
the rest of the frontend is in [frontend.md](frontend.md).

## `features/chat`

| File | Role |
|---|---|
| `ChatPage.tsx` | The screen: the chat list beside the conversation from `md` up (a drawer the header's "Your chats" button opens below it), the header (the screen's name, the open chat's title, what its replies have cost so far as a compact `CostText`, "New chat" once there is a conversation), an `Aurora`, the transcript, the composer. "New chat" starts a fresh one: nothing is made on the server until something is said |
| `ChatList.tsx` | The person's chats, the one last written to first, each with its title (`UNTITLED_CHAT` until something was said) and when it was last written to; the open one carries `aria-current`. Hovering (or focusing, or a touch screen) shows Rename and Delete: renaming is an inline field (Enter saves, Escape or leaving it cancels), deleting asks in place ("Delete this chat?", Delete or Keep it, the latter focused). "New chat" at the top; what went wrong is an alert |
| `useChats.ts` | The list (`GET /chats`), which chat is open (`openId`, kept for the tab by `chatStorage`), `ensure()` (the open chat's id, or a chat made now with `POST /chats`: `send` calls it for the first message, so the list never fills with empty chats), `select`, `startNew`, `rename`, `remove` (each true once done, else the error is shown), and `refresh`, read again once a reply ends so the list shows the chat's new title and time |
| `useChatStream.ts` | Owns the transcript of the open chat: opening a chat loads its messages (`GET /chats/<id>`; a saved reply's tools come back as the screen showed them, one still running when the reply was cut as stopped), a fresh chat starts with the greeting. `send(prompt)` adds the person's message and an empty reply, gets the chat to send in from `ensureChat`, streams `POST /chat` with its `chat_id` and the browser's zone, folds text and tool events into the reply as they come, keeps the `usage` event that ends it on the message, then calls `onReplyEnd`. Switching chats aborts a reply in progress (the server keeps what came); a chat `send` just made is not loaded again over the reply streaming into it. A failed reply is shown with its reason |
| `chatStorage.ts` | Which chat the tab has open (`sessionStorage`, `aimix.chat.open.v1`): `readOpenChat`, `writeOpenChat`, and `forgetChat`, which main.tsx calls when the session ends. Blocked storage only means a fresh chat on return |
| `chatUsage.ts` | `totalUsage(messages)`: what every reply of the chat used in all, for the header |
| `ChatMessages.tsx` | `MessageBubble` animates each bubble in (`renderMarkdown` for the assistant), `TypingIndicator` stands in until a reply has text or a tool, `ChatSuggestions` offers starters to a fresh chat |
| `ToolActivity.tsx` | One tool a reply used; what it made shows through `ACTION_VIEWS`: a link (a mission, a run, Schedules), a `WebhookCard` (`useWebhookLink` reads the link, never stored) or a `DeliveryCard` (Confirm or Cancel through `useDelivery`) |
| `ChatComposer.tsx` | The message box with its microphone, and `AiNotice` under it |

## What the server keeps, and what the tab keeps

The server keeps every chat and its messages, each reply with the tools it used and
what its model calls used and cost. The tab keeps only which chat is open, so leaving
the screen (to open what the assistant built) and coming back reopens the same chat,
and a new tab or device starts with the list. Signing out forgets the open chat.

The assistant reads a chat's newest messages that fit in `CHAT_HISTORY_MAX_CHARS`; the
older ones become its notes once (`CHAT_SUMMARY_MAX_CHARS`), which it reads in their
place from then on. The screen shows every message regardless; the notes are only in
the account's copy. A chat holds at most `CHAT_MAX_MESSAGES` messages, after which
sending answers `409 chat_full` and the person starts a new chat; an account keeps at
most `CHATS_MAX_PER_USER` chats.
