# Data Agent Frontend Redesign

**Date:** 2026-07-26
**Status:** Approved
**Owning repository:** `data-agent/`

## Purpose

Redesign the complete Data Agent frontend, from login through conversation and secondary management tools, around a focused conversational workflow. The redesign must improve visual hierarchy, reduce persistent interface chrome, make Agent execution understandable without dominating the answer, and preserve every existing backend capability and security boundary.

The primary users are data developers and data operations personnel. They need access to execution details, errors, approvals, scheduled tasks, and metric identities, but those technical capabilities should appear on demand rather than compete with the conversation.

## Success criteria

- Login leads to a task-first home page where the primary action is describing a goal.
- A user can start or resume a conversation without first understanding the management structure.
- Conversation history does not permanently reduce the reading width.
- Agent execution remains inspectable through a compact, borderless disclosure.
- Approvals, secret input, failures, and reconnect actions are visually distinct only when user action is required.
- Scheduled tasks and metric identities remain fully usable in dedicated secondary workspaces.
- Refresh, deep links, and browser navigation restore the selected page and session.
- The interface remains usable on desktop and mobile and retains keyboard and screen-reader semantics.
- Existing authentication, session, event-stream, approval, interaction, scheduling, and metric-identity contracts remain unchanged.

## Product structure

### Primary flow

The product is conversation-first:

1. An unauthenticated user sees a single login form.
2. A successful login opens the task home page at `/`.
3. The user enters an analysis, investigation, or scheduling objective.
4. The application creates a session and navigates to `/sessions/:id`.
5. The conversation shows the result as the main content and exposes execution details inline.
6. History and tools are opened only when requested.

### Global navigation

A narrow navigation rail contains icon-only entry points for:

- New task
- Conversation history
- Tools
- Account and settings

The active destination is indicated with a small gray-indigo marker and icon color, not a filled navigation tile. Desktop navigation remains narrow. Mobile navigation moves to the bottom edge.

### Task home

The task home page contains:

- A short prompt asking what data problem the user wants to solve
- The main composer
- The selected metric identity as lightweight composer metadata
- A short list of starter tasks rendered as text rows separated by fine rules

The page does not contain a dashboard, operational metrics, marketing content, or a grid of colored cards.

### Conversation

The conversation uses a centered reading column. The user's messages have one neutral, light warm background. Agent messages render directly on the page without a surrounding card.

The header shows the conversation title and lightweight context controls. The composer remains anchored at the bottom of the conversation pane without covering the last message.

## Agent execution disclosure

Execution details are part of the message flow, not a pill, card, or persistent side panel.

Collapsed state:

```text
已处理 34s ›
────────────────────────
```

Expanded state:

```text
已处理 34s ⌄
⌘ 查询任务执行记录
⌁ 计算失败率趋势
✓ 识别异常责任域
────────────────────────
```

While a run is active, the disclosure shows the current step. After completion it collapses by default. The final answer follows immediately after the divider.

## User-action states

Ordinary messages and execution details do not use cards. A bordered action region is reserved for states that require a user decision or sensitive input:

- Mutation approval
- Secret input
- Structured pending interaction

The region uses a fine neutral border and a single gray-indigo leading rule. Primary confirmation uses the muted straw-gold action color. Cancellation remains neutral.

Connection failures and recoverable submission failures render as compact inline notices with an in-place retry action. The application preserves the current messages, draft, and run progress while reconnecting. Recoverable errors do not open modal dialogs.

## Conversation history

Conversation history is a temporary drawer rather than a permanent sidebar.

- Desktop width: 230–280 px
- Desktop maximum: 30% of the viewport
- Mobile width: full screen
- Long titles: one line with ellipsis
- Contents: search, grouped session titles, and update times

Opening the drawer overlays the left side of the conversation instead of resizing the reading column. Closing it restores focus to the invoking control.

## Secondary tools

Scheduled tasks and metric identities live in a dedicated tools workspace. The workspace provides the full width required for tables, editors, execution history, and identity management. Data-source operations continue through the existing conversational Agent capability rather than adding a new management page.

Tool routes are:

- `/tools/scheduled`
- `/tools/identities`

The tools workspace has a clear return-to-conversation action. Navigating to a tool preserves the active session, unsent draft, scroll position, and expanded execution disclosure. Returning restores that state.

## Visual language

### Palette

The interface uses a very light yellow family without making the page visibly yellow at first glance:

| Role | Color | Usage |
| --- | --- | --- |
| Canvas | `#FAF8F2` | Main page and conversation background |
| Navigation | `#F4EEDF` | Large navigation region |
| Primary action | `#D8C89A` | Send and primary confirmation |
| Accent | `#536779` | Active navigation, links, process focus, secondary icons |
| Primary text | `#343732` | Headings and body text |

Green is not used. Red is reserved for errors and destructive semantics and is not a decorative accent.

### Color and surfaces

- Large surfaces establish the warm tone.
- Small controls rely on text, fine borders, and whitespace rather than filled color blocks.
- No gradients are used.
- Ordinary content is not placed inside cards.
- Shadows are limited to floating surfaces such as the composer and history drawer.
- Border radii remain moderate and do not turn status text into pills.

### Typography and spacing

The visual hierarchy relies primarily on type weight, line height, and whitespace. Agent answers use a comfortable reading measure and generous line height. Metadata is smaller and lower contrast but remains accessible.

## Authentication

`AuthenticatedApp` remains the authentication boundary. The login page uses the same ivory canvas, gray-indigo accent, and muted straw-gold primary action. It remains a single form and does not add promotional content.

HttpOnly cookie authentication, `/auth/session` state restoration, logout behavior, and the response to a `401` remain unchanged.

## Frontend architecture

The current large application component is split into focused units:

- `AppShell`: global navigation, route outlet, account actions, and responsive structure
- `TaskHome`: new-task composer and starter tasks
- `ConversationView`: conversation header, message list, state notices, and bottom composer
- `ProcessDisclosure`: active and completed execution details
- `ActionRequest`: approval and pending-interaction presentation boundary
- `Composer`: prompt entry, identity context, submission, and draft behavior
- `HistoryDrawer`: history search, session switching, and focus management
- `ToolsWorkspace`: secondary tool routing and return behavior

Existing metric, scheduling, markdown, artifact, and interaction components are reused where their behavior is already correct. Styling changes should not trigger unrelated backend or domain refactors.

No new frontend state-management library is introduced. A focused workspace controller or hook owns session loading, active-session selection, event subscriptions, submission state, reconnection, and route synchronization.

## Routing and state flow

Supported routes are:

- `/`
- `/sessions/:id`
- `/tools/scheduled`
- `/tools/identities`

The backend session remains the source of truth. Event streams apply incremental updates to the corresponding session. The URL represents the selected top-level view and active session, enabling refresh and browser history restoration.

Ephemeral view state includes:

- Composer drafts keyed by session
- Message scroll positions keyed by session
- Process-disclosure expansion keyed by run
- History-drawer visibility
- The last conversation visited before entering tools

On authentication failure, ephemeral state is discarded and the authentication boundary is shown. On recoverable transport failure, ephemeral state is retained and the user receives an in-place retry or reconnect action.

## Responsive behavior

Desktop:

- Narrow global rail
- Centered conversation reading column
- 230–280 px overlay history drawer
- Full-width tools workspace

Mobile:

- Bottom global navigation
- Full-width conversation
- Full-screen history view
- Tool tables adapt to stacked rows or controlled horizontal scrolling
- Pending actions remain inline and do not exceed the viewport

The composer must account for the software keyboard and safe-area insets.

## Accessibility

- All icon-only navigation controls have accessible names and visible focus states.
- Drawer focus is contained while open and returns to the invoking control when closed.
- Run, reconnect, error, and approval status use appropriate live-region behavior without repeatedly announcing unchanged content.
- Enter submits and Shift+Enter inserts a newline.
- Reduced-motion preferences disable nonessential transitions.
- Text and controls meet accessible contrast targets across the approved palette.

## Verification

Repository instructions prohibit adding or modifying test-related code unless explicitly requested. Implementation therefore keeps the existing tests unchanged and verifies the redesign with:

- Existing frontend test suite
- Prettier format check
- TypeScript project build
- Vite production build
- Manual desktop and mobile checks for login, task creation, session restoration, streaming execution, process disclosure, approval, pending interaction, reconnect, history switching, tool navigation, keyboard use, and focus behavior

## Non-goals

- Backend contract changes
- New Agent, scheduling, metric-identity, or data-connection capabilities
- A dashboard-first landing page
- A permanent conversation sidebar
- A persistent execution side panel
- New frontend frameworks or state libraries
- Changes to existing test code
