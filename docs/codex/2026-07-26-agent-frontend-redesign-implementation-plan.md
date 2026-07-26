# Data Agent Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Data Agent frontend as a conversation-first workspace with a task home, focused conversation view, narrow history drawer, dedicated tools pages, and the approved ivory-yellow and gray-indigo visual language.

**Architecture:** Keep the existing React/Vite stack and backend clients. Split the current `App.tsx` controller and presentation into a small History API route model, a workspace controller hook, focused view components, and dedicated CSS files; preserve the existing session, SSE replay, approval, secret-input, scheduling, metric-identity, and authentication behavior.

**Tech Stack:** React 19, TypeScript 5.8, Vite 7, Vitest 2, Testing Library, Lucide React, existing fetch/SSE clients, plain CSS.

## Global Constraints

- Product code changes belong only in `data-agent/frontend/`.
- Do not add a routing library, state-management library, component framework, or other dependency.
- Keep HttpOnly-cookie authentication and every existing backend API/event contract unchanged.
- Preserve SSE deduplication and ordered replay by `runId + sequence`.
- Preserve approvals, pending interactions, secret input, optimistic user messages, retries, reconnects, metric-identity version checks, and scheduler idempotency behavior.
- The approved palette is `#FAF8F2` canvas, `#F4EEDF` navigation, `#D8C89A` primary action, `#536779` accent, and `#343732` primary text.
- Do not use green, gradients, decorative status pills, a permanent conversation sidebar, or a persistent execution side panel.
- The desktop history drawer is 230–280 px and never wider than 30% of the viewport; mobile history is full screen.
- The user explicitly authorized updating existing frontend tests for the intentional task-home, history-drawer, process-disclosure, and palette changes. Preserve behavioral coverage rather than deleting it.
- Make no backend, Metric Platform, root-build, or root-submodule-pointer changes.
- Before every commit, inspect `git status --short` inside `data-agent/` and stage only files from the current task.

---

## File Structure

### New files

- `frontend/src/app/workspaceRoute.ts` — parse, format, navigate, and subscribe to workspace routes.
- `frontend/src/hooks/useAgentWorkspace.ts` — session loading, active-session state, SSE replay, submissions, approvals, interactions, reconnects, and metric identities.
- `frontend/src/components/shell/AppShell.tsx` — responsive global frame and account actions.
- `frontend/src/components/shell/GlobalRail.tsx` — new task, history, tools, and account navigation.
- `frontend/src/components/conversation/TaskHome.tsx` — task-first landing page and starter objectives.
- `frontend/src/components/conversation/HistoryDrawer.tsx` — searchable 230–280 px session overlay.
- `frontend/src/components/conversation/ConversationView.tsx` — conversation header, notices, messages, action requests, and composer composition.
- `frontend/src/components/conversation/ConversationMessageItem.tsx` — user/assistant message rendering and citation artifacts.
- `frontend/src/components/conversation/ProcessDisclosure.tsx` — borderless “已处理 Ns” run disclosure.
- `frontend/src/components/conversation/Composer.tsx` — prompt input, identity context, keyboard behavior, and submit action.
- `frontend/src/components/tools/ToolsWorkspace.tsx` — scheduled-task and metric-identity routes with return-to-conversation behavior.
- `frontend/src/styles/shell.css` — application shell, navigation, route surfaces, and responsive navigation.
- `frontend/src/styles/conversation.css` — task home, messages, disclosure, notices, action requests, and composer.
- `frontend/src/styles/history.css` — history overlay, search, session rows, and mobile full-screen behavior.
- `frontend/src/styles/tools.css` — tools navigation and shared tool-page layout.

### Modified files

- `frontend/src/AuthenticatedApp.tsx` — authentication-only boundary and authenticated application handoff.
- `frontend/src/App.tsx` — route/view composition using the controller hook.
- `frontend/src/domain/agentPrototype.ts` — add the optional run duration consumed by the process disclosure.
- `frontend/src/api/backendAgentClient.ts` — derive run duration from ordered backend-event timestamps.
- `frontend/src/main.tsx` — import the new focused style sheets.
- `frontend/src/styles.css` — approved design tokens and global reset only.
- `frontend/src/auth.css` — redesign login and authentication loading states.
- `frontend/src/scheduled-tasks.css` — restyle the existing scheduler UI within the tools workspace.
- `frontend/src/metric-platform.css` — restyle metric identity and action-request components.
- `frontend/src/components/metric/MetricIdentityManager.tsx` — support page presentation while preserving secure credential handling.
- `frontend/src/components/scheduler/ScheduledTaskWorkspace.tsx` — accept the tools shell rather than owning top-level workspace switching.
- Existing `frontend/src/App*.test.tsx`, `frontend/src/visualPalette.test.ts`, `frontend/src/workspaceVisualHierarchy.test.ts`, and `frontend/src/workspaceScrollLayout.test.ts` — update intentional page-entry and presentation assertions while preserving behavioral coverage.

---

### Task 1: Lock the approved visual contract

**Files:**
- Modify: `frontend/src/visualPalette.test.ts`
- Modify: `frontend/src/workspaceVisualHierarchy.test.ts`
- Modify: `frontend/src/workspaceScrollLayout.test.ts`
- Modify: `frontend/src/styles.css`
- Create: `frontend/src/styles/shell.css`
- Create: `frontend/src/styles/conversation.css`
- Create: `frontend/src/styles/history.css`
- Create: `frontend/src/styles/tools.css`
- Modify: `frontend/src/main.tsx`

**Interfaces:**
- Produces CSS variables `--color-canvas`, `--color-surface`, `--color-navigation`, `--color-primary-action`, `--color-accent`, `--color-text`, `--color-muted`, and `--color-line`.
- Produces stable layout classes `.app-shell`, `.global-rail`, `.conversation-pane`, `.conversation-messages`, `.history-drawer`, and `.composer-surface`.

- [ ] **Step 1: Change the three source-inspection tests to the approved contract**

Use one `readWorkspaceStyles()` helper in each relevant test to concatenate the focused CSS files:

```ts
function readWorkspaceStyles() {
  return ['styles.css', 'styles/shell.css', 'styles/conversation.css', 'styles/history.css']
    .map((file) => readFileSync(resolve(process.cwd(), 'src', file), 'utf8'))
    .join('\n');
}
```

Assert these exact tokens and prohibitions in `visualPalette.test.ts`:

```ts
expect(css).toContain('--color-canvas: #faf8f2;');
expect(css).toContain('--color-surface: #fffefa;');
expect(css).toContain('--color-navigation: #f4eedf;');
expect(css).toContain('--color-primary-action: #d8c89a;');
expect(css).toContain('--color-accent: #536779;');
expect(css).toContain('--color-text: #343732;');
expect(css).not.toContain('#1f7a68');
expect(css).not.toContain('linear-gradient(');
expect(css).not.toContain('backdrop-filter:');
```

Update hierarchy and containment assertions to require `.composer-surface`, a borderless assistant body, `.history-drawer`, `.conversation-messages`, and the 280 px/30 vw drawer constraint instead of `.session-rail`.

- [ ] **Step 2: Run the three tests and verify the old CSS fails**

Run:

```powershell
npm test -- visualPalette.test.ts workspaceVisualHierarchy.test.ts workspaceScrollLayout.test.ts
```

Expected: FAIL because the approved variables and new layout classes do not exist.

- [ ] **Step 3: Replace `styles.css` with tokens and global reset**

The token block must be:

```css
:root {
  color-scheme: light;
  font-family:
    Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --color-canvas: #faf8f2;
  --color-surface: #fffefa;
  --color-navigation: #f4eedf;
  --color-primary-action: #d8c89a;
  --color-accent: #536779;
  --color-text: #343732;
  --color-muted: #74756f;
  --color-line: #e3ddd1;
  --color-error: #8a5148;
}

html,
body,
#root {
  height: 100%;
  overflow: hidden;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--color-canvas);
  color: var(--color-text);
}

button,
input,
select,
textarea {
  font: inherit;
}
```

Add the stable class skeletons to the four new CSS files, including:

```css
.history-drawer {
  position: absolute;
  inset: 0 auto 0 0;
  width: min(280px, 30vw);
  min-width: 230px;
  overflow: hidden;
}

.conversation-pane {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-height: 0;
  overflow: hidden;
}

.conversation-messages {
  min-height: 0;
  overflow-y: auto;
}
```

- [ ] **Step 4: Import the focused CSS files from `main.tsx`**

The import order must be:

```ts
import './styles.css';
import './styles/shell.css';
import './styles/conversation.css';
import './styles/history.css';
import './styles/tools.css';
import './auth.css';
import './scheduled-tasks.css';
import './metric-platform.css';
```

Remove the `control-plane.css` import. Remove the `metric-platform.css` side-effect import from `App.tsx`.

- [ ] **Step 5: Run visual contract tests**

Run:

```powershell
npm test -- visualPalette.test.ts workspaceVisualHierarchy.test.ts workspaceScrollLayout.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit the visual foundation**

```powershell
git add frontend/src/styles.css frontend/src/styles frontend/src/main.tsx frontend/src/visualPalette.test.ts frontend/src/workspaceVisualHierarchy.test.ts frontend/src/workspaceScrollLayout.test.ts
git commit -m "style: establish agent workspace design tokens"
```

---

### Task 2: Add explicit routes and the authenticated shell

**Files:**
- Create: `frontend/src/app/workspaceRoute.ts`
- Create: `frontend/src/components/shell/AppShell.tsx`
- Create: `frontend/src/components/shell/GlobalRail.tsx`
- Modify: `frontend/src/AuthenticatedApp.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.sessionPersistence.test.tsx`
- Modify: `frontend/src/App.authentication.test.tsx`
- Modify: `frontend/src/styles/shell.css`
- Modify: `frontend/src/auth.css`

**Interfaces:**
- Produces `WorkspaceRoute`, `parseWorkspaceRoute`, `workspaceRoutePath`, `navigateWorkspace`, and `subscribeWorkspaceRoute`.
- `App` receives optional `subject`, `onLogout`, and `onAuthenticationRequired` props. Production passes the real account callbacks; isolated component tests use safe display/no-op defaults.
- `AppShell` receives the current route, history state, account label, and navigation callbacks.

- [ ] **Step 1: Update route-facing tests**

In `App.sessionPersistence.test.tsx`, make `/` assert the task-home heading. In the persistence case, set the session route before rendering and retain the existing reload assertion:

```tsx
expect(await screen.findByRole('heading', { name: '今天想解决什么数据问题？' }))
  .toBeInTheDocument();

window.history.replaceState(null, '', '/sessions/session_second');
render(<App />);
expect(await screen.findByRole('heading', { name: 'Second session' })).toBeInTheDocument();
```

In `App.authentication.test.tsx`, render the required authenticated props and keep the existing `401` callback assertion:

```tsx
render(
  <App
    subject="admin"
    onLogout={vi.fn().mockResolvedValue(undefined)}
    onAuthenticationRequired={onAuthenticationRequired}
  />,
);
```

- [ ] **Step 2: Run the route-facing tests**

Run:

```powershell
npm test -- App.sessionPersistence.test.tsx App.authentication.test.tsx
```

Expected: FAIL because the home route and new props do not exist.

- [ ] **Step 3: Create `workspaceRoute.ts`**

Implement this public model:

```ts
export type WorkspaceRoute =
  | { kind: 'home' }
  | { kind: 'session'; sessionId: string }
  | { kind: 'scheduled' }
  | { kind: 'identities' };

export function parseWorkspaceRoute(pathname = window.location.pathname): WorkspaceRoute;
export function workspaceRoutePath(route: WorkspaceRoute): string;
export function navigateWorkspace(route: WorkspaceRoute, replace?: boolean): void;
export function subscribeWorkspaceRoute(listener: (route: WorkspaceRoute) => void): () => void;
```

Use `/`, `/sessions/:id`, `/tools/scheduled`, and `/tools/identities`. Invalid and malformed paths return `{ kind: 'home' }`.

- [ ] **Step 4: Create `GlobalRail` and `AppShell`**

`GlobalRail` must expose labeled buttons rather than filled tiles:

```ts
interface GlobalRailProps {
  route: WorkspaceRoute;
  onNewTask: () => void;
  onToggleHistory: () => void;
  onOpenTools: () => void;
  onOpenAccount: () => void;
}
```

`AppShell` must expose:

```ts
interface AppShellProps {
  route: WorkspaceRoute;
  subject: string;
  historyOpen: boolean;
  onNewTask: () => void;
  onToggleHistory: () => void;
  onOpenTools: () => void;
  onLogout: () => Promise<void>;
  children: ReactNode;
}
```

Use accessible names `新任务`, `会话历史`, `工具`, and `账户菜单`.

- [ ] **Step 5: Reduce `AuthenticatedApp` to authentication**

Remove the `workspace` state and top workspace switcher. On success render:

```tsx
<App
  subject={session.subject}
  onLogout={logout}
  onAuthenticationRequired={() => setSession(null)}
/>
```

Keep login, session restoration, logout, and all HttpOnly-cookie behavior unchanged. Correct any garbled Chinese literals in this file while editing it.

- [ ] **Step 6: Compose the shell in `App.tsx`**

Add route state using `parseWorkspaceRoute()` and `subscribeWorkspaceRoute()`. Keep test-friendly defaults while production supplies the authenticated account:

```ts
interface AppProps {
  subject?: string;
  onLogout?: () => Promise<void>;
  onAuthenticationRequired?: () => void;
}

export default function App({
  subject = 'admin',
  onLogout = async () => undefined,
  onAuthenticationRequired,
}: AppProps) {
```

Render the temporary task-home heading for `/`; keep the existing conversation body for session routes until later tasks extract it. Adjust the existing session-load effect so loading sessions while the route is `/` populates the store without calling `updateSessionPath`; only a session route selects and restores a conversation.

- [ ] **Step 7: Restyle authentication and shell**

Use the approved tokens. Login remains a single centered form. Do not add illustrations, gradients, feature lists, or marketing copy.

- [ ] **Step 8: Run authentication and persistence tests**

Run:

```powershell
npm test -- App.authentication.test.tsx App.sessionPersistence.test.tsx
```

Expected: PASS.

- [ ] **Step 9: Commit routing and shell**

```powershell
git add frontend/src/app frontend/src/components/shell frontend/src/AuthenticatedApp.tsx frontend/src/App.tsx frontend/src/auth.css frontend/src/styles/shell.css frontend/src/App.authentication.test.tsx frontend/src/App.sessionPersistence.test.tsx
git commit -m "feat: add conversation-first workspace shell"
```

---

### Task 3: Extract the Agent workspace controller

**Files:**
- Create: `frontend/src/hooks/useAgentWorkspace.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.backendRecovery.test.tsx`
- Modify: `frontend/src/App.reliability.test.tsx`

**Interfaces:**
- Consumes existing `createFetchAgentBackendClient`, `createMetricIdentityClient`, `applyBackendAgentEvent`, `orderBackendEvents`, and domain store functions.
- Produces `AgentWorkspaceController` for all later presentation tasks.

- [ ] **Step 1: Preserve reliability assertions while changing test entry paths**

For tests that need an existing conversation, set the path before render:

```ts
window.history.replaceState(null, '', '/sessions/session_backend');
```

Open the history drawer through the `会话历史` button before locating or switching sessions. Keep all existing request URLs, duplicate-event, optimistic-message, `401`, approval-lock, retry, and reconnect assertions.

- [ ] **Step 2: Run the two focused suites**

Run:

```powershell
npm test -- App.backendRecovery.test.tsx App.reliability.test.tsx
```

Expected: FAIL where tests still assume the permanent sidebar or old controller composition.

- [ ] **Step 3: Define `AgentWorkspaceController`**

Export:

```ts
export interface AgentWorkspaceController {
  sessions: AgentSession[];
  active: AgentSession | null;
  loading: boolean;
  backendSessionsAvailable: boolean;
  prompt: string;
  setPrompt: (value: string) => void;
  metricIdentities: MetricIdentitySummary[];
  newSessionMetricIdentityId: string | null;
  setNewSessionMetricIdentityId: (value: string | null) => void;
  statusNotice: string | null;
  failedSubmission: FailedSubmission | null;
  streamState: 'idle' | 'connected' | 'reconnecting';
  isSending: boolean;
  isAwaitingAgent: boolean;
  isConfirming: boolean;
  isResolvingInteraction: boolean;
  interactionError: string | null;
  startTask: (objective: string) => Promise<void>;
  activateSession: (sessionId: string) => void;
  submitPrompt: (content: string) => Promise<void>;
  retrySubmission: () => Promise<void>;
  reconnectEventStream: () => Promise<void>;
  bindCurrentMetricIdentity: (identityId: string | null) => Promise<void>;
  resolvePendingInteraction: (optionId: string) => Promise<void>;
  submitPendingSecret: (value: string) => Promise<void>;
  handleApproval: (decision: 'approved' | 'rejected') => Promise<void>;
  handleMetricIdentitiesChanged: (identities: MetricIdentitySummary[]) => void;
}
```

- [ ] **Step 4: Move existing state and side effects without changing behavior**

Move session loading, metric-identity loading, event subscription maps, replay reduction, submission, retry, approval, interaction, secret, binding, and reconnect logic from `App.tsx`. Preserve the existing comments around deterministic replay and optimistic messages.

Change initial loading behavior: an empty backend list remains empty and renders the task home; do not create a default server session during page load. If the backend is unavailable, retain the existing local-prototype fallback.

- [ ] **Step 5: Make route/session synchronization explicit**

When a session route resolves to a loaded session, call `activateSession`. When it does not exist after loading, replace the route with `{ kind: 'home' }`. `startTask(objective)` derives a title from the first 40 characters, creates the local or backend session, sends the objective against the returned session ID without waiting for React state propagation, subscribes to events, and then navigates to the session route.

- [ ] **Step 6: Replace controller code in `App.tsx` with the hook**

`App.tsx` should select the view from the route and controller. It must not duplicate fetch, SSE, or interaction state.

- [ ] **Step 7: Run controller-sensitive tests**

Run:

```powershell
npm test -- App.backendRecovery.test.tsx App.reliability.test.tsx App.sessionPersistence.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit the controller extraction**

```powershell
git add frontend/src/hooks/useAgentWorkspace.ts frontend/src/App.tsx frontend/src/App.backendRecovery.test.tsx frontend/src/App.reliability.test.tsx
git commit -m "refactor: isolate agent workspace state"
```

---

### Task 4: Build task home and narrow history drawer

**Files:**
- Create: `frontend/src/components/conversation/TaskHome.tsx`
- Create: `frontend/src/components/conversation/HistoryDrawer.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/App.sessionPersistence.test.tsx`
- Modify: `frontend/src/styles/conversation.css`
- Modify: `frontend/src/styles/history.css`

**Interfaces:**
- `TaskHome` consumes identities, selected identity, busy state, and `onSubmit(objective)`.
- `HistoryDrawer` consumes sessions, active session ID, open state, and session selection.

- [ ] **Step 1: Update existing home and session-list tests**

Replace old permanent-sidebar assertions with:

```tsx
expect(screen.queryByRole('dialog', { name: '会话历史' })).not.toBeInTheDocument();
fireEvent.click(screen.getByRole('button', { name: '会话历史' }));
expect(screen.getByRole('dialog', { name: '会话历史' })).toBeInTheDocument();
```

Keep the existing search filtering and session switching assertions after opening the drawer. Add no new test file.

- [ ] **Step 2: Run affected App tests**

Run:

```powershell
npm test -- App.test.tsx App.sessionPersistence.test.tsx
```

Expected: FAIL because the focused components do not exist.

- [ ] **Step 3: Create `TaskHome`**

Use:

```ts
interface TaskHomeProps {
  identities: MetricIdentitySummary[];
  metricIdentityId: string | null;
  busy: boolean;
  onMetricIdentityChange: (value: string | null) => void;
  onSubmit: (objective: string) => Promise<void>;
}
```

Render the heading `今天想解决什么数据问题？`, one composer, and three text-row starters:

- `排查最近失败的任务`
- `分析核心指标异常`
- `创建每日巡检任务`

Clicking a starter fills and submits that exact objective.

- [ ] **Step 4: Create `HistoryDrawer`**

Use:

```ts
interface HistoryDrawerProps {
  open: boolean;
  sessions: AgentSession[];
  activeSessionId: string | null;
  onClose: () => void;
  onSelect: (sessionId: string) => void;
}
```

Render `role="dialog"` and `aria-label="会话历史"`, keep search local to the drawer, group the current list under `最近会话`, truncate titles with CSS, close after selection, and restore focus to the history trigger.

- [ ] **Step 5: Compose home and drawer in `App.tsx`**

The `/` route renders `TaskHome`. Submitting calls the controller's atomic `startTask(objective)` action. The history drawer overlays both home and conversation routes.

- [ ] **Step 6: Apply approved home and drawer styles**

Use large ivory surfaces, text rows with fine dividers, no shortcut cards, no filled navigation tiles, and the exact desktop drawer dimensions from the global constraints.

- [ ] **Step 7: Run home/history tests**

Run:

```powershell
npm test -- App.test.tsx App.sessionPersistence.test.tsx workspaceScrollLayout.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit task home and history**

```powershell
git add frontend/src/components/conversation/TaskHome.tsx frontend/src/components/conversation/HistoryDrawer.tsx frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/App.sessionPersistence.test.tsx frontend/src/styles/conversation.css frontend/src/styles/history.css
git commit -m "feat: add task home and history drawer"
```

---

### Task 5: Rebuild the focused conversation and process disclosure

**Files:**
- Create: `frontend/src/components/conversation/ConversationView.tsx`
- Create: `frontend/src/components/conversation/ConversationMessageItem.tsx`
- Create: `frontend/src/components/conversation/ProcessDisclosure.tsx`
- Create: `frontend/src/components/conversation/Composer.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/domain/agentPrototype.ts`
- Modify: `frontend/src/api/backendAgentClient.ts`
- Modify: `frontend/src/App.thinkingPresentation.test.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/styles/conversation.css`

**Interfaces:**
- Consumes `AgentSession`, `AgentRunStep`, existing markdown/citation/result components, and controller actions.
- Produces the stable accessible labels `消息列表`, `执行过程`, and `Prompt`.

- [ ] **Step 1: Update process-presentation assertions**

Set a session route before render. Replace old “思考过程” button expectations with:

```tsx
const disclosure = await screen.findByRole('button', { name: /执行过程/ });
expect(disclosure).toHaveTextContent(/已处理 \d+s|正在处理/);
fireEvent.click(disclosure);
const process = screen.getByLabelText('执行过程');
expect(within(process).getByText('metrics.query')).toBeInTheDocument();
```

Keep assertions that the final assistant answer renders after the disclosure and that tool details are hidden until expanded.

- [ ] **Step 2: Run conversation presentation tests**

Run:

```powershell
npm test -- App.thinkingPresentation.test.tsx App.test.tsx
```

Expected: FAIL because `ProcessDisclosure` and the new composition do not exist.

- [ ] **Step 3: Extract `ConversationMessageItem`**

Move markdown, citation selection, and `MetricResultCard` behavior unchanged. User messages receive a neutral warm surface; assistant messages remain borderless.

- [ ] **Step 4: Add deterministic run duration**

Extend `AgentRun` with:

```ts
durationSeconds?: number;
```

In `backendAgentClient.ts`, derive it from ordered event timestamps:

```ts
function runDurationSeconds(events: BackendAgentEvent[]): number | undefined {
  const ordered = orderBackendEvents(events);
  if (ordered.length < 2) return undefined;
  const startedAt = Date.parse(ordered[0].occurredAt);
  const finishedAt = Date.parse(ordered.at(-1)!.occurredAt);
  if (!Number.isFinite(startedAt) || !Number.isFinite(finishedAt)) return undefined;
  return Math.max(1, Math.round((finishedAt - startedAt) / 1000));
}
```

Set `durationSeconds: runDurationSeconds(run.events)` in `toAgentRun`. Do not change backend DTOs.

- [ ] **Step 5: Create `ProcessDisclosure`**

Use:

```ts
interface ProcessDisclosureProps {
  run: AgentRun;
  pending: boolean;
}
```

Use `run.durationSeconds` when available; otherwise show `已处理` for terminal runs and `正在处理` for active runs. The completed label with duration is `已处理 Ns`. Default expansion is `false` for terminal runs and `true` while running or waiting. Render steps as plain rows above one bottom divider, with no pill or surrounding card.

- [ ] **Step 6: Create `Composer`**

Use:

```ts
interface ComposerProps {
  value: string;
  disabled: boolean;
  busy: boolean;
  identityLabel: string;
  onChange: (value: string) => void;
  onSubmit: () => Promise<void>;
}
```

Preserve Enter submit, Shift+Enter newline, IME composition guards, `aria-busy`, label `Prompt`, and button name `发送`.

- [ ] **Step 7: Create `ConversationView`**

Compose the header, identity selector, inline notices, message list, pending state, `ProcessDisclosure`, existing approval/interaction/secret components, and `Composer`. Preserve the current “do not steal scroll when the user scrolled away from the bottom” threshold behavior.

- [ ] **Step 8: Remove presentation code from `App.tsx`**

Leave only route composition, shell state, tool selection, and controller wiring. Delete the old mode pills from the persistent conversation footer; starter objectives replace them on the home page.

- [ ] **Step 9: Run conversation and reliability suites**

Run:

```powershell
npm test -- App.thinkingPresentation.test.tsx App.test.tsx App.reliability.test.tsx
```

Expected: PASS.

- [ ] **Step 10: Commit the conversation rebuild**

```powershell
git add frontend/src/components/conversation frontend/src/App.tsx frontend/src/domain/agentPrototype.ts frontend/src/api/backendAgentClient.ts frontend/src/App.thinkingPresentation.test.tsx frontend/src/App.test.tsx frontend/src/styles/conversation.css
git commit -m "feat: rebuild focused agent conversation"
```

---

### Task 6: Integrate scheduled tasks and metric identities as tool pages

**Files:**
- Create: `frontend/src/components/tools/ToolsWorkspace.tsx`
- Modify: `frontend/src/components/metric/MetricIdentityManager.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/scheduled-tasks.css`
- Modify: `frontend/src/metric-platform.css`
- Modify: `frontend/src/styles/tools.css`

**Interfaces:**
- `ToolsWorkspace` selects `scheduled` or `identities` and provides a return action.
- `MetricIdentityManager` supports both dialog and page presentation without changing credential state or API calls.

- [ ] **Step 1: Add page presentation to metric identity management**

Change props to:

```ts
interface MetricIdentityManagerProps {
  presentation?: 'dialog' | 'page';
  open?: boolean;
  client: MetricIdentityClient;
  identities: MetricIdentitySummary[];
  onClose?: () => void;
  onChanged: (identities: MetricIdentitySummary[]) => void;
  onAuthenticationRequired?: () => void;
}
```

Compute visibility with:

```ts
const visible = presentation === 'page' || open === true;
if (!visible) return null;
```

For `presentation="page"`, render the existing content in a `<section aria-label="指标身份管理">` without a backdrop, modal semantics, or close button. Preserve password clearing, verification, deactivation confirmation, and sanitized notices.

- [ ] **Step 2: Preserve scheduler ownership and Agent return behavior**

Keep `ScheduledTaskWorkspace.onOpenAgent` unchanged. `ToolsWorkspace` passes its `onBack` callback through this prop so `ScheduledTaskEditor` can return to the prior conversation. Do not change list, execute, edit, delete, history, or idempotency behavior.

- [ ] **Step 3: Create `ToolsWorkspace`**

Use:

```ts
interface ToolsWorkspaceProps {
  section: 'scheduled' | 'identities';
  identities: MetricIdentitySummary[];
  identityClient: MetricIdentityClient;
  onIdentitiesChanged: (values: MetricIdentitySummary[]) => void;
  onBack: () => void;
  onAuthenticationRequired: () => void;
}
```

Render local navigation buttons for `定时任务` and `指标身份`; use `navigateWorkspace` for section changes and a `返回对话` button that returns to the last session route or `/`.

- [ ] **Step 4: Wire tool routes in `App.tsx`**

Render `ToolsWorkspace` for `/tools/scheduled` and `/tools/identities`. Preserve the last conversation route in a ref whenever a session route becomes active.

- [ ] **Step 5: Restyle existing tool components**

Use ivory backgrounds, fine dividers, muted straw-gold primary actions, gray-indigo links/active navigation, and semantic red only for destructive or error states. Remove green decorative styling and excessive small filled chips.

- [ ] **Step 6: Run scheduler, identity, and full type checks**

Run:

```powershell
npm test -- App.test.tsx App.authentication.test.tsx
npx tsc -b --pretty false
```

Expected: tests PASS and TypeScript exits 0.

- [ ] **Step 7: Commit tool integration**

```powershell
git add frontend/src/components/tools frontend/src/components/metric/MetricIdentityManager.tsx frontend/src/App.tsx frontend/src/scheduled-tasks.css frontend/src/metric-platform.css frontend/src/styles/tools.css
git commit -m "feat: move management into tool workspaces"
```

---

### Task 7: Finish responsive behavior, accessibility, and cleanup

**Files:**
- Modify: `frontend/src/styles/shell.css`
- Modify: `frontend/src/styles/conversation.css`
- Modify: `frontend/src/styles/history.css`
- Modify: `frontend/src/styles/tools.css`
- Modify: `frontend/src/auth.css`
- Modify: `frontend/src/App*.test.tsx`
- Modify: `frontend/src/workspaceVisualHierarchy.test.ts`
- Modify: `frontend/src/workspaceScrollLayout.test.ts`
- Delete only if no import or class reference remains: `frontend/src/control-plane.css`

**Interfaces:**
- Mobile uses bottom navigation, full-width conversation, full-screen history, and safe-area-aware composer spacing.
- Focus returns from the history drawer and tool pages to a predictable navigation control.

- [ ] **Step 1: Add mobile and reduced-motion rules**

At `max-width: 720px`:

```css
.app-shell {
  grid-template-columns: 1fr;
  grid-template-rows: minmax(0, 1fr) auto;
}

.global-rail {
  grid-row: 2;
  flex-direction: row;
  padding-bottom: max(8px, env(safe-area-inset-bottom));
}

.history-drawer {
  width: 100%;
  min-width: 0;
}

.composer-surface {
  margin-bottom: max(12px, env(safe-area-inset-bottom));
}
```

Add `@media (prefers-reduced-motion: reduce)` to disable nonessential transitions.

- [ ] **Step 2: Audit labels and focus behavior**

Verify all icon buttons have accessible names, the drawer uses dialog semantics, closing restores focus, live regions do not announce unchanged steps repeatedly, and destructive buttons retain textual labels.

- [ ] **Step 3: Remove obsolete selectors and garbled copy**

Search:

```powershell
rg -n "session-rail|workspace-switcher|thinking-block|#1f7a68|linear-gradient|backdrop-filter|锟|鈥|瀵|浼" frontend/src
```

Remove obsolete selectors and correct garbled Chinese strings in files touched by this plan. Do not alter backend payloads or unrelated documentation.

- [ ] **Step 4: Run format**

Run:

```powershell
npm run format
npm run format:check
```

Expected: format writes only planned frontend files; format check exits 0.

- [ ] **Step 5: Run the complete frontend suite**

Run:

```powershell
npm test
```

Expected: all existing and authorized-updated tests PASS.

- [ ] **Step 6: Run production build**

Run:

```powershell
npm run build
```

Expected: Prettier, TypeScript, and Vite build all exit 0 and produce `dist/`.

- [ ] **Step 7: Perform manual browser verification**

Check desktop at 1440×900 and mobile at 390×844:

1. Login and authentication restoration
2. Task home and starter objective submission
3. Session creation and deep-link refresh
4. Streaming events and ordered process rows
5. Completed disclosure defaulting closed
6. Approval, pending interaction, and secret input
7. Failed submission retry and SSE reconnect
8. History open/search/select/close and focus return
9. Scheduled task list/editor/execution history
10. Metric identity add/verify/password replacement/deactivate
11. Browser back/forward between conversation and tools
12. Mobile bottom navigation, full-screen history, software-keyboard-safe composer

- [ ] **Step 8: Inspect repository status**

Run:

```powershell
git status --short
git diff --check
```

Expected: only planned frontend changes or generated `dist/` output already ignored by the repository; no backend or root files changed.

- [ ] **Step 9: Commit final responsive and cleanup work**

```powershell
git add frontend/src/styles/shell.css frontend/src/styles/conversation.css frontend/src/styles/history.css frontend/src/styles/tools.css frontend/src/auth.css frontend/src/App.test.tsx frontend/src/App.authentication.test.tsx frontend/src/App.backendRecovery.test.tsx frontend/src/App.reliability.test.tsx frontend/src/App.sessionPersistence.test.tsx frontend/src/App.thinkingPresentation.test.tsx frontend/src/workspaceVisualHierarchy.test.ts frontend/src/workspaceScrollLayout.test.ts
git commit -m "style: finish responsive agent workspace"
```

Do not update or commit the root `data-agent` Git link in this task.

---

## Final Verification

From `data-agent/frontend/`:

```powershell
npm run format:check
npm test
npm run build
```

From `data-agent/`:

```powershell
git status --short
git log -7 --oneline
```

From the workspace root:

```powershell
git status --ignore-submodules=none --short
```

Expected outcome:

- All frontend tests pass.
- The production build succeeds.
- The Data Agent submodule contains only the intentional frontend commits.
- The root repository still shows its pre-existing submodule state and does not pin a new Data Agent revision without separate user authorization.
