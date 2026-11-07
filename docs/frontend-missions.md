# Frontend: the Missions workspace and the run report

The two parts of the React app that hand a run's work over to the person: the Missions
workspace, and the run report it shares with the Runs page and the builder. The rest of
the app (routing, `core/`, the other features, conventions and tests) is in
[frontend.md](frontend.md).

## `features/mission` — the Missions workspace

The mission workspace at `/mission` (a new mission) and `/mission/<pipeline id>`
(reopen one) is the front door: a person says what they want done, AIMIx builds a
team of agents, shows it, runs it and delivers the results, and the person changes
the team by talking to it. It adds no backend of its own: it composes generation
(`POST /api/pipelines/generate`), revision (`/revise`), saving and background runs,
on one screen.

**The screen.** `useMissionLayout` picks one of four layouts (`missionPanes.ts`, a
registry per layout for the grid, which panes show and how each is placed):

- **`tabs`**, below `xl` (1280px): one pane at a time behind Conversation, Team and
  Results tabs (ARIA tabs, arrow keys, Home and End); the Results tab carries the newest
  run's status ("Running"). A mission opened with a run opens on Results, unless the
  person picked a tab first; a run started here keeps them in the conversation.
- **`settling`**, from `xl`, while a reopened mission's team and newest run load
  (`useLatestRun`'s `checked`): only the conversation and "Loading your mission…", so the
  screen settles once instead of snapping from three panes into two columns. It is latched:
  once settled, it stays settled for the visit.
- **`three`**, from `xl` with no run yet: conversation, team and the planned results side
  by side.
- **`twoUp`**, from `xl` once the team has run: the conversation beside one main column
  with compact Team | Results tabs. Results comes forward for each new run; the person's
  pick holds until the next one. Focus never moves on its own.

The conversation column is 20rem at `xl` and 24rem at `2xl` in every wide layout, so it
does not jump when a run starts. All panes stay mounted, so a half-written message and
scroll positions survive a switch; a link in the conversation ("See the team") brings its
pane forward and moves focus to that pane's heading. Layout changes and tab switches are
instant (the tabs' `ActivePill` still glides).

- **Conversation** (an ARIA `log`, so AIMIx's answers are announced). Empty, it asks
  "What do you want to get done?" with four example missions, the template
  quick-starts (one click makes the person's own saved pipeline from a template) and
  the newest saved missions. The first message *describes* the mission: a team is
  generated and, in plain words, AIMIx lists each agent, what it delivers, its tools
  and what the person provides. Every later message is a *change request*: AIMIx
  answers with the changes in words (`describeChange`), a preview, and inline Apply
  and Discard. **Run it** — the button under the box, or the phrase typed (`isRunRequest`
  takes whole phrases only, so "run the research in parallel" is still a change) —
  puts the run's inputs in the conversation (`RunInputCard`, "Attach a document" and
  "Add a web page" included) and starts the run. Nothing is sent while AIMIx is working
  (Stop cancels it), and the box says why. The box takes `PLAN_DESCRIPTION_MAX_LENGTH`
  characters before there is a team and `REVISION_INSTRUCTION_MAX_LENGTH` after, and
  says so once full.
- **Documents in the message box.** Beside the microphone, "Attach a document" (several
  files at once) and "Add a link" (the same `WebPageField` as the run form); files
  dropped on the box are attached too (it lights up while they are held over it), and a
  link written in the message is offered as "Read example.com for your team". Each
  becomes a chip above the text: its name (a link as host and path), "Reading…", then
  "1 page · 195 characters", or the server's reason in amber; removing one cancels its
  reading and moves focus to the next chip, else back to the text; a chip that leaves on
  its own (its document went into the open run form) hands focus on the same way. Each is
  read on its own, so no reading waits for another. A mission takes `MAX_PLAN_DOCUMENTS`
  (5), and the box says so; the same file (name, size and date) or page (by the link
  given or where it led) is not added twice ("report.pdf is already attached."). The
  documents belong to the mission until a run takes them: a message planned with them
  (the description, or the answers to the planner's questions) sends each read one's
  name, size and first 2,000 characters (`documents` on `POST /api/pipelines/generate`;
  the plan then has a `documents` run input), and names them on the person's bubble.
  Planning never goes without one still being read: until it is, Send and the questions'
  buttons wait and say "Waiting for report.pdf to be read…". **Run it** opens the form
  with their blocks in the `documents` input (or the free text of a team without named
  inputs), as many as one run takes (`RUN_INPUT_MAX_LENGTH`), and the box lets go of
  those. A team whose inputs are all meant for something else gets no guess: the box
  keeps them and asks "Put them in:" with a button per input. One that does not fit stays
  for the next run, and the box says so. One still being read when the form is open
  goes into it when read, and the form's Run waits for it. A change request does not read
  them, so they stay. Only the names and sizes are kept with the conversation; the text
  lives in memory, so after a reload, or once a run has taken them, a form whose
  `documents` input is empty with nothing coming says "Attach your documents again under
  “Your documents”: AIMIx keeps only their names, not their text.".
- **Team.** What the person provides, then the agents as people (`TeamRoster`), live
  while a run works (a run of exactly this team, as in the builder). Selecting an agent opens a drawer over the results with the
  builder's own step editor (`StepCard`: role, task, tools, model, prompt); it is a
  non-modal dialog (focus moves in, Escape closes and hands focus back) and agents
  cannot be edited while a run works. "Open in builder" saves and opens the pipeline
  in the advanced mode, which links back with "Open in mission view".
- **Results.** One centred 36rem reading column. Before the first run,
  `PlannedDeliverables`: "When your team has run, you get this:" (or "these:"), each
  deliverable as a dashed item (its title, expected output and "by {role}"), then who
  checks the work ("The Orchestrator checks the work before it reaches you."); the final
  check is left out of the list unless it is the only output, as the report does. Then the
  newest run's [run report](#the-run-report-featuresrunsreport) at level 3, with "Open in
  Runs" and, when the team changed since, "This run used an earlier version of this
  pipeline.". The swap from the planned list to a report, or from one run to the next,
  fades out in 150 ms then rises 8px over 250 ms (a 150 ms fade each way under reduced
  motion); nothing animates on load. While the run is not known yet the column says
  "Loading your results…" after 400 ms.

**Layout rule.** The screen is exactly the window's height and each pane scrolls inside
itself, so nothing may make the page scroll. The grid's pane row is bounded
(`minmax(0,1fr)`; without it the row grows with the tallest pane; `twoUp` puts the tab
row above it), every
scrolling area is `relative` (visually hidden `sr-only` text is absolutely positioned and
would otherwise escape it and stretch the page), each pane `overflow-clip`s what
decoration spills past its edge (the sparks around "Run it"), and the root clips what is
left. A new scrolling area inside a pane needs `relative` too.

**Saving.** A mission is a pipeline. A new mission is a draft in the tab until it
first runs: starting a run saves it (named from the plan, else from the first words
of the description) and moves the address to `/mission/<id>` without rebuilding the
screen (router state `{ adopted }`, see `useWorkspaceIdentity`); opening it in the
builder saves it too. Edits to a saved mission — the drawer, an applied change — are
saved `AUTOSAVE_DELAY_MS` (1.5 s) after the last one, and always before a run; one
save runs at a time. A failed save shows on the team pane and waits for the next edit.

**What is kept, and where.** The server keeps the team and its runs: reopening
`/mission/<id>` loads the pipeline and its newest run (`useLatestRun`). The
*conversation* is client state in this version: JSON in `sessionStorage`, one entry per
mission (`aimix.mission.v1.<pipeline id>`, or `….new` for a draft, which also keeps
the draft team), at most 200 messages, every access in try/catch. It lasts for the tab:
another tab or browser starts that mission's conversation again from a greeting with
its team. The keys name no account, so all of them are forgotten (`forgetAllMissions`)
when the session ends (a logout, or the server refusing the session) and again when
someone signs in: the next account in the tab never finds the last one's prompts, team
brief or draft team. A proposal that was waiting when the page was left shows as no longer
available, and a message left unanswered is said to be. Keeping conversations on the
server would need a table and endpoints; that is not part of this version.

| File | Role |
|---|---|
| `MissionPage.tsx`, `useWorkspaceIdentity.ts`, `missionAddress.ts` | The route: reads the id, redirects an address that is not one, and rebuilds the workspace when another mission is opened (not for a new mission's own first save) |
| `MissionWorkspace.tsx`, `useMissionLayout.ts`, `usePanes.ts`, `missionPanes.ts`, `PaneHeader.tsx`, `MissionTabs.tsx` | The panes in their layout (`PaneGrid`; a pane is a tab panel when a tab names it, else a region named by its heading); which layout applies, when it has settled and when Results comes forward without moving focus (`useMissionLayout`, `OPENS_RESULTS` per layout); which pane is in front and where focus goes (`usePanes`: `select` and `show` count as the person's choice, `preset` does not); the pane title bar (screen readers only when a tab names the pane, unless it has controls); the tabs, full or compact over a subset (`panes`, `compact`) |
| `useMission.ts` | The workspace's state, composed from the hooks below; routes what the person sends (describe, answer the planner's open questions, run it, or a change), plans with the documents read so far (waiting while one is read: `planWaitsFor`) and hands them to "Run it" (`runIt`); what the open run form makes of the box (`runWaitsFor`, the `placement` of the ones it did not take, `documentsGone`); opens the mission in the builder |
| `useMissionDocuments.ts`, `missionDocuments.ts` | The documents and pages added in the message box: each read on its own request (several at once, each cancelled when removed or when the screen goes), at most `MAX_PLAN_DOCUMENTS`, none twice (`isAttached`: a file by `fileKey`, a page by either address), a status line for screen readers, the one still being read (`reading`), and a sink that puts a document read while the run form is open straight into it. The pure side: what a message keeps (`noteOf`), what the planner reads (`planDocumentOf`: the first `PLAN_DOCUMENT_EXCERPT_CHARS`, and the name cut to `PLAN_DOCUMENT_NAME_MAX_LENGTH`, since a redirect can make a page's address longer; never half an emoji), where the run form takes them (`documentsTarget`: the `documents` input, the free text, or `null` so the person picks), what fits (`withDocuments`, which leaves out one past `RUN_INPUT_MAX_LENGTH` and says which it took) and the link to offer (`unattachedLink`) |
| `useMissionTeam.ts` | The team on screen: loads a saved mission by id, edits (swap, patch or remove an agent), one-at-a-time saving, autosave. Saving keeps the team's identity, so a proposal made for it stays valid |
| `useTeamGeneration.ts` | Description → team over `POST /api/pipelines/generate` (`planMission`): the planner may ask questions first (`may_ask`); the answers, or a skip, plan the team without asking again. The `Briefing` carries the documents too. Cancellable, plain words for failures, nothing saved |
| `useMissionProposals.ts` | Change requests over `useRevisePipeline`: each gets an answer in the conversation that shows the live proposal and keeps its outcome (applied, discarded, failed, stopped, expired) |
| `useMissionRun.ts` | "Run it": the inputs form in the conversation, opened with the mission's documents in it (`ask` returns the ones it took, or `null` when no form opened; `place` puts documents in the open form, in an input picked or where the team takes them, as far as they fit, measured against the newest values so documents arriving together count each other), saving then starting a run, following it (`useFollowedRun`) |
| `useMissionConversation.ts`, `missionMessages.ts`, `missionStorage.ts`, `missionShape.ts` | The conversation as plain JSON data (notes, team descriptions, the planner's questions, proposals, forms, runs; a message of the person's may name the documents that went with it, `DocumentNote`: name, pages, characters, never the text), its `sessionStorage` copy, and `missionShape`'s checks of what is read back (a message or draft that does not fit is left out, never allowed to break the screen; a message kept before documents existed has none and still loads) |
| `missionIntent.ts`, `teamBrief.ts` | Pure: which phrases mean "run it"; a team as words (agents, tasks, tools, what to provide) |
| `ConversationPane.tsx`, `MissionComposer.tsx`, `MissionStart.tsx`, `useRecentMissions.ts` | The conversation pane: the log, the message box (Enter sends, Shift + Enter adds a line; `noValidate`, so a half-typed link never blocks Send), the empty state with examples, templates and recent missions |
| `ComposerAttachments.tsx`, `DocumentPlacementNotice.tsx`, `ComposerTools.tsx` | The message box's documents: the chips (icon, name and details, then × in its own column; a link's label shown whole, a file name cut once at its end; they come in with a 200 ms fade, scale and blur and leave in 150 ms, only a 150 ms fade under reduced motion, `AnimatePresence` with `initial={false}`; the list is capped at `max(4.5rem, 12dvh)` and scrolls), the caption "Your team gets these when it runs." once there is a team, the limit and "already attached" notice and a polite status; while a run form is open, why the ones left are not in it, naming them, with a button per input when the team has none meant for documents (`DocumentPlacementNotice`); the toolbar (attach, add a link, dictate, send; 44px under a finger, as is "Run it"). The box is a drop zone (`core/hooks/useFileDrop`) |
| `MessageItem.tsx`, `TeamMessageView.tsx`, `QuestionsMessageView.tsx`, `ProposalMessageView.tsx`, `InputsMessageView.tsx`, `RunMessageView.tsx`, `Bubble.tsx`, `messageContext.ts` | One view per kind of answer, in a registry (a new kind is a new entry); the context carries the live proposal, form, run and open questions each one needs. The questions view offers each suggested answer as a chip (a radio underneath) beside a field for one's own; a message typed meanwhile answers all of them; its buttons wait while a document of the box is still being read. The run form waits for one the box will hand it, and asks for the documents again when they are gone |
| `TeamPane.tsx`, `TeamRoster.tsx`, `StepDrawer.tsx`, `useStepDrawer.ts` | The team pane (what the person provides, then `TeamRoster`: the agents as people, step by step, the ones of one step "together", each with its role, what it makes, a Deliverable or "Checks the work" badge, its live status, round and a check's outcome, and the start of its work once done; a card opens the agent while the team can be edited) and the agent drawer (its editor is the builder's `StepCard`, so it has the two flow sections too, over the team's own steps); the hook follows the team (a removed agent closes it) and gives focus back |
| `ResultsPane.tsx`, `PlannedDeliverables.tsx` | The results pane: one centred 36rem column (its scroller sets `--sticky-top: 0px`), the planned deliverables and who checks them before the first run, then the newest run's `RunReport` (level 3, "Open in Runs", the earlier-version note); the swap fades (M1 below) |

`testData.ts` (fixtures and `routeFetch`, a fetch stand-in that answers
`"METHOD /api/path"`) and `testRender.tsx` serve the tests.

## The run report (`features/runs/report`)

**Each run reads as one document its team hands over.** One component, `RunReport`,
renders a run the same way in three places:

| Where | Heading level `L` | Extras |
|---|---|---|
| The mission's Results pane (`ResultsPane`) | 3, under the pane's h2 | "Open in Runs", the earlier-version note |
| The Runs page (`RunDetail`: h1 "Runs", h2 the pipeline's name and `RunByline`) | 3 | the team's diagram in the appendix, Delete once the run has ended |
| The builder's "Latest run" section (`PipelineBuilderPage`) | 2, under the page's h1 | "Open in Runs", the earlier-version note |

Render it as `<RunReport key={run.id} run={…} control={…} level={2 | 3} extras={…} />`:
`control` is anything with `RunControls` (`useRun`'s state, or the mission's and builder's
`FollowedRun`), and the `key` gives each run fresh, closed panels and nothing to announce.
Every model output is rendered exactly once on the page.

**Its parts, in a fixed order** (a part with nothing to say renders nothing):

1. **Outcome header** (`OutcomeHeader`, a `<header>`): the heading (h`L`, focusable, its
   words swapped by `SwapText`), one plain sentence (and the "Open Settings" hint when no
   provider is set up), the action row (`ActionRow`: Stop, which reads "Stopping…" until
   it is answered, or Resume / raise the limit through `ResumeControl`, then the screen's
   own actions, "What the service said" for a failure, and the report's only
   `role="alert"`, the last action's error), the sign-off line (`SignOff`), the jump links
   for two deliverables or more (`JumpLinks`), the meta line (`MetaLine`: status · elapsed
   · cost · "Open in Runs", dots drawn by CSS, `dotted.ts`), what the team was given
   (`GivenLine`), the version note, and the 2px brand-gradient progress rule
   (`ProgressRule`: done / total; dim while working, full at the end, faded to slate when
   the run ended short). After Stop, Resume or a raised limit, focus goes to the heading
   once the action is answered, unless the person moved it.
2. **Approval cards** (`PendingApprovals` → `ApprovalCard`), only while the run waits.
3. **Deliverables** (`DeliverableList`, a region): the AI notice once, as soon as any step
   has written something, then one deliverable per output step in run order. The final
   check is not one, unless it is the only output. A ready deliverable is a document
   (`DeliverableDoc`): a sticky title row (h`L`, Copy and Download) that sticks below
   `--sticky-top` (a frosted ground shows only while it is stuck, where the browser
   supports scroll-state container queries, so no darker band sits on the page at rest;
   elsewhere the ground always shows), a byline ("by Writer · llama-4 · $0.0123 · 1,204 words ·
   Approved by the Orchestrator": who wrote it, on which model, what it cost once it used
   anything, and the character count under 300 words), and the Markdown through
   `RenderedMarkdown` with its own headings from h`L+1`. Copy (`DeliverableActions`)
   writes formatted text and plain text at once (`copyRich`); Download offers .html, .txt
   and .md (`DOWNLOAD_FORMATS` in `deliverableFiles.ts`) in a small menu that Escape, a
   choice, a press outside or the keyboard leaving it closes. A deliverable not ready yet is a dashed slot
   (`DeliverableSlot`) exactly where its document will land, with its state in words
   ("Being written · 5.0 s", "Starts when Research is done", "Waiting for your OK ·
   Review the request", "Not made: its condition was not met…").
4. **Was this useful?** (`FeedbackRow`), once the run has ended: two thumbs (Useful,
   Not useful; press the chosen one again to take it back) and a note for the next team
   ("What should the next team do differently?"), saved with the rating through
   `control.rate`; "Saved. The next team you plan will know." once it is. The planner
   reads the notes of the person's latest runs when it builds a new team.
5. **Saved during this run** (`RunFiles`, `useRunFiles`): the workspace files saved
   between the run's start and end (±2 s, open-ended while it works, since the files'
   times are the server's; there is no per-run record of files yet),
   pictures first with a preview (`PicturePreview`), each downloadable (`FileRow` without
   Delete), and "All files". Looked up only when an agent had a file-saving tool, again
   as steps finish; a failed lookup hides the part.
6. **How your team got there** (`TeamWork`), folded at first: "What each agent did" (one
   `TimelineRow` per agent, by stage, with its status, cost, model, round, its tool
   use in words from `toolWords.ts` and what it looked at (each call's `target`: the
   query, the page, the file, the question; the first six, then "and N more"), then
   "Read it above" (a deliverable that is ready),
   "Read the check above" or "Show what it wrote"), "What your team was given" (`RunGiven`: each typed text,
   document and page with its size, the server's notes on what was cut or not read, and
   an excerpt), and on the Runs page "The team", the run's own diagram.

**States.** `reportModel(run)` is the pure view of a run: its deliverables, its reviewer,
how many agents are done and the outcome, one of `queued`, `running`, `checking` (the
reviewer is working), `fixing` (the reviewer sent work back and rounds are left),
`waiting`, `done`, `doneNothing` (every deliverable skipped), `limit` (the spending
limit), `failed`, `stopped` and `interrupted`, from a lookup per run status. The words
come from registries keyed by those kinds: `outcomeCopy.ts` (heading and sentence),
`signOffCopy.ts` (the sign-off line and each byline's check), `stepCopy.ts` (slot and
timeline words), `reviewRounds.ts` (where each review loop stands). Work the reviewer
sent back reads "Being revised · round 2 of 3" until it is done again.

**The sign-off** says whether to trust the work: "Checked and approved by the
Orchestrator.", "Approved by the Orchestrator after 1 round of fixes.", "The Orchestrator
is checking the work…", "The Orchestrator asked for fixes." or "Not checked: …", with
"Read the full check" opening the reviewer's
whole answer beside a 1px brand-gradient rule. A byline carries the check only for a
deliverable the reviewer reads: the stage just before its own, and the deliverables of
its loop's earlier stages (as `StepNode._work` hands them over), never one before its
loop. A long check (over 1,500 characters) or a long agent text gets a second "Hide …" at
its end (`BottomHide`), which brings its toggle into view and takes focus back to it.

**For screen readers.** `useRunAnnouncements` turns each poll into at most one sentence
("Draft ready.", "Your team finished: 2 deliverables ready, approved by the
Orchestrator.", "The Orchestrator asked for fixes. Round 2 of 3 has started.", "Your team
needs your OK: …", "You stopped the run.", "Your team is working again." after a resume
or an answered request), silent on the first render; `core/ui/Announcer` speaks it from a
polite status line under `<body>`, and the conversation's run bubble updates its line
without speaking it (`aria-live="off"`), so nothing is said twice. The outcome heading is
named by its current words (`aria-label`), so the focus it takes after Stop or Resume
never reads the old words still swapping out. Jumps (`useJump`) scroll smoothly (at
once under reduced motion) and then focus the target heading or toggle without a second
scroll; ids come from `reportIds(run.id)`.

**Motion.** Built on the `core/ui/motionTokens.ts` scale (see
[frontend.md](frontend.md#coreui--shared-presentation-and-motion)); nothing animates on
load and nothing counts up.

| # | What moves | How | Reduced motion |
|---|---|---|---|
| M1 | The mission's Results content swaps (planned → report, run → run) | out: fade 150 ms; in: fade and rise 8px, 250 ms smooth-out | fade 150 ms each way |
| M2 | Words swapping in place (`SwapText`: the outcome heading, slot words) | out up 4px with a 2px blur, in from below, 150 ms each | fade only |
| M3 | The progress rule | `scaleX` and opacity, CSS, smooth-out | no transition |
| M4 | The sign-off landing | rise 8px out of a 2px blur, 400 ms smooth-out, 150 ms after the heading | fade 150 ms, no delay |
| M5 | The hand-over: a slot becomes its document | slot blurs out in 150 ms; the document rises 8px over 400 ms (out of a blur only when 1,500 characters or fewer), `filter` cleared after | fade 150 ms both ways |
| M6 | Live slots | `ShinyText` shimmer on the words, static bars, a ticking time | static |
| M7 | Disclosures (`Foldable`) | grid row plus fade and 2px blur; small: open 250 ms, close 150 ms; large: 350 / 250 ms; the chevron flips in 250 ms | no transition |
| M8 | Copy feedback | the icon swaps with `ICON_SPRING`; "Copy" / "Copied" cross-fade in one grid cell, so the width holds | fade |
| M9 | The Download menu | open: fade and scale from 0.97, 250 ms; close: 150 ms | fade |
| M10 | Pressing a run button (`RUN_BUTTON`) | `active:scale-[0.96]`, 150 ms | no scale |
| M12 | Jumps | smooth `scrollIntoView`, then focus | instant |
| M13 | Tabs and layouts | panels and layouts switch at once; `ActivePill` glides | — |

| File | Role |
|---|---|
| `RunReport.tsx` | The report: header, approvals, then the body (`ReportBody`: deliverables, files, appendix) and the `Announcer`; `ReportExtras` (`linkToRuns`, `actions`, `note`, `diagram`) |
| `OutcomeHeader.tsx`, `ActionRow.tsx`, `MetaLine.tsx`, `JumpLinks.tsx`, `ProgressRule.tsx`, `dotted.ts` | The outcome header and its rows (above) |
| `FeedbackRow.tsx` | "Was this useful?": the thumbs and the note (above) |
| `SignOff.tsx`, `checkTone.ts`, `BottomHide.tsx` | The sign-off line and the full check; each check tone's icon and colour (`CHECK_TONE`, shared with the bylines); the second "Hide …" of a long text |
| `DeliverableList.tsx`, `DeliverableDoc.tsx`, `DeliverableActions.tsx`, `DeliverableSlot.tsx`, `deliverableFiles.ts` | The deliverables, the hand-over (M5), Copy and Download (`safeFileName`, `htmlDocument`) and the slots |
| `RunFiles.tsx`, `useRunFiles.ts`, `runFiles.ts` | "Saved during this run": the listing (cancelled on unmount, kept while a new one loads), and the pure window and file-saving tools (`FILE_SAVING_TOOLS`, mirroring the backend's toolbox) |
| `TeamWork.tsx`, `TimelineRow.tsx`, `RunGiven.tsx`, `runGiven.ts` | The appendix; `runGiven` reads a run's inputs back into parts with `splitDocuments` (`pipelineInputs.ts`, beside the `[Document: …]` header it reads) and the server's notes ("[Document truncated: …]", "[Not read: pages 4-7 (…).]") |
| `reportModel.ts`, `reviewRounds.ts`, `outcomeCopy.ts`, `signOffCopy.ts`, `stepCopy.ts` | Pure: the model and the words (above); `reviewerDefinition` (the last step, by stage, with a review) is shared with `PlannedDeliverables` |
| `useRunAnnouncements.ts`, `jump.ts`, `textStyles.ts` | The announcements, the jumps, and the looks of the report's text links and text buttons (`TEXT_LINK`, `TEXT_BUTTON`) |
| `reportTestData.ts`, `testReport.tsx` | Test fixtures (a team with two parallel writers and a reviewer that can send work back; the old flow fixture) and `renderReport(run, …)`, which also skips animations in report specs |

Elsewhere in `features/runs` the report uses `toolWords.ts` (`TOOL_WORDS`: each tool's
use in words, "3 web searches · 1 page read, 1 failed", and an approval asked in plain
words), `PendingApprovals` (it exports `askedBy`; the report's `Announcer` speaks for it)
and `RunControls` from `useRun.ts`.
