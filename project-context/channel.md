# Project working channel

Coordinator: root agent. Context librarian: **Lily** ([definition](../.codex/agents/lily.toml)). Shared overview: [context.md](context.md). Opened 2026-09-29 for the documentation/onboarding objective.

This is a durable ownership and handoff log for future subagents. Live messages coordinate execution; this file does not provide scheduling or locking.

## Working agreement

1. Read repository instructions, the overview, this log, and current Git status before claiming work.
2. Obtain a task ID and explicit file scope. Check active entries for overlap; ask the coordinator to resolve conflicting ownership before editing.
3. Use statuses `pending`, `active`, `blocked`, `ready-for-review`, and `completed`. State a concrete blocker and next action when blocked.
4. Preserve other agents' edits and pre-existing untracked files. Keep work within the agreed scope.
5. Serialize channel edits through Lily or the coordinator while agents run concurrently. Send them updates to append rather than racing edits to this shared file.
6. Add dated status updates beneath a task; retain earlier evidence and handoffs. Record exact commands/check results and distinguish static inspection from tests or live execution.
7. On completion, identify changed files, validation, remaining questions, and the recipient's next action. Lily promotes accepted findings into `context.md`.
8. Never include credentials, private keys, local `.env` values, or raw private service responses. Audit mode still uses live services; do not run it as an onboarding check.

## Entry template

Copy this block for each new task and replace every placeholder:

```markdown
### TASK-ID: Short outcome
- Owner: agent name; reviewer/coordinator: name
- Status: pending | active | blocked | ready-for-review | completed
- Updated: YYYY-MM-DD
- Objective: concrete deliverable and acceptance criteria
- Owned files: exact paths or narrow module scope
- Dependencies: task IDs or none
- Evidence/checks: inspected symbols, commands, outcomes; say not run where applicable
- Changes: files changed and resulting behavior/documentation
- Blockers/questions: verified blocker, uncertainty, or none
- Handoff/next action: recipient and specific action

Updates:
- YYYY-MM-DD — status — progress, evidence, and next step
```

## Current tasks

### BUILD-005: Remaining workflow, documentation, verification, and rollout
- Owner: rollout_orchestrator coordinates delegates; root integrates and owns account actions/user decisions; independent reviewers and Lily at milestones
- Status: active
- Updated: 2026-10-02
- Objective: user expanded the durable goal to all remaining approved Tasks 6-10 and requested orchestrated subagent workload distribution. Stop and ask promptly at major account/secret/billing/authorization blockers.
- Owned files: Task 6 delegate owns `.github/workflows/scan.yml`, `scripts/fail_queued_scan.py`, optional `scripts/validate_scan_config.py`, `tests/test_workflow_failure.py`, `tests/test_scan_workflow.py`, and `pyproject.toml`/`uv.lock` only for a pinned YAML test parser. Task 7 delegate owns `.env.example`, `README.md`, `docs/vercel-github-actions.md`, `docs/cloud-run-backend.md`, legacy hosted `docs/plans/` documents, and Node 24 metadata in `package.json`/`package-lock.json`. Root owns context/channel/plan status, `.gitignore`, factual `AGENTS.md` refresh, reusable `.codex/agents/` definitions, and Task 5; reviewers read-only.
- Evidence/checks: final local suite passes 183 Python and 150 web tests; lock, compileall, typecheck, lint, fake-config production build, and actionlint 1.7.12 pass. Isolated Python 3.12.14 locked no-dev installation and checkout prompt discovery pass. Earlier Task 5 independent review passed before later subprocess hardening; orchestrator reviewed Tasks 6-7. Final independent re-review delegates reported usage-limit errors, so root verified integration and notified Lily without overlapping edits. Fresh GitHub metadata confirms public repo/default `main`/push access. Vercel team is accessible but empty; tools lack import/environment mutation and no provider CLI is installed.
- Boundaries: no secrets or runtime data published, no paid service/billing, no live scan or provider mutation before local acceptance and required user setup/authorization. Do not claim deployment or spending controls from local tests.
- Handoff/next action: Tasks 6-8 completed locally. User approved publishing through a PR; root stages reviewed application/workflow/docs only, excludes credentials/runtime data/unrelated review notes, and publishes a PR without merging. Task 9 requires user review/merge and private settings: spending/free-tier verification, GitHub secrets/token, Vercel import/settings, production Auth URLs, migration baseline, then one controlled hosted scan. Root refreshed context as usage-limit fallback; no production acceptance claimed.

### BUILD-004: Task 5 GitHub runner safety
- Owner: root coordinator and implementation; planned independent review: task5_inspector; context refresh: Lily after verification
- Status: completed locally
- Updated: 2026-10-02
- Objective: implement approved Task 5 only: validate runner scan/user UUIDs and ownership, reject non-queued reruns before work, conditionally fail pre-claim startup errors, preserve losing-worker safety and existing scan behavior.
- Owned files: root now owns `src/deal_finder/scan_job.py`, new config-independent `scan_errors.py`, `repository.py`, `supabase_repository.py`, `scan_service.py`, new `tests/test_scan_job.py`, focused service/repository tests, repository doubles, offline test isolation, implementation-plan status, and this entry. Backend delegate hit an account usage limit before editing and returned its design; root took over. Review is read-only; Lily gets context-file ownership after implementation.
- Evidence/checks: baseline full Python suite freshly passed 31 tests. Red contracts exposed missing UUID/owner checks, unsafe pre-claim writes, and traceback leakage. Independent review PASS: 87 focused job/service/adapter tests and 108 full offline Python tests passed. Integration subsequently reproduced an import-time numeric-configuration traceback in two subprocess tests; lazy runtime imports/config-independent errors fix it, with 89 focused tests now passing and 110 pre-workflow cases passing. Both repository doubles implement `fail_queued_scan`; `uv lock --check`, locked editable installation, `compileall -q src`, and `git diff --check` pass. An autouse Requests/socket guard blocks unmocked outbound calls. Initial seven cascade-regression failures were a non-UUID fixture, fixed before final verification. Full suite/review will rerun with Tasks 6-7 integration before publishing.
- Boundaries: preserve prior dirty/untracked work. No workflow implementation, deployment, live scan, Supabase writes, billing/secret changes, push, or commit.
- Handoff/next action: Task 5 requirements audited complete: validated runner IDs/owner, all nonqueued reruns stop before targets, atomic queued startup failure, no-write ambiguous/lost claims, safe output, preserved real cascade gates/snapshot/thumbnail. Continue BUILD-005 Tasks 6-10 under expanded goal; Lily refresh after the workflow/documentation milestone. No hosted acceptance claimed.

### CTX-012: Record locally verified Task 4 recovery and dashboard milestone
- Owner: Lily; reviewer/coordinator: root coordinator
- Status: completed
- Updated: 2026-10-02
- Objective: record BUILD-003 completion and narrow the next boundary to Task 5 Python runner safety.
- Owned files: `project-context/context.md`, `project-context/channel.md` only.
- Evidence/checks: current Git status, recovery route/helper, proxy, dashboard helpers, plan status, and root-supplied verification; no application checks rerun by Lily.
- Changes: refreshed current Tasks 1-4 implementation boundary and 150-test/browser/HTTP evidence; moved BUILD-003 under Current tasks, marked it complete locally, and narrowed BUILD-001 next step to Task 5.
- Handoff/next action: root reports Task 4 local completion; continue with Python runner safety, then workflow/rollout. Historical Python/live-service evidence and all other contributors' edits are preserved.

Updates:
- 2026-10-02 — completed — Only the two context files edited. Focused source/documentation consistency checks and `git diff --check` passed. Application/browser/HTTP checks are root-reported and were not rerun by Lily. No onboarding, credential read, external mutation, scan, deployment, or commit.

### BUILD-003: Task 4 queued recovery and dashboard feedback
- Owner: root coordinator; context refresh: Lily after verification
- Status: completed
- Updated: 2026-10-02
- Objective: implement approved Task 4 only, replacing legacy recovery and making scan actions resilient without losing completed results.
- Owned files: recovery route/helper, scan proxy, dashboard/client helpers, corresponding web tests, implementation-plan status, and this task entry. Preserve all prior work.
- Evidence/checks: Tasks 1-3 baseline is historical; Task 4 starts with five expected-failing recovery contracts. Current Vercel workspace read succeeds after reconnection and has no projects.
- Changes: Vercel recovery uses validated getUser identity and the same origin/deployment guards as Scan Now, storage-only configuration, and atomic owner/queued/UTC cutoff mutation. Dashboard renders uncertain notices, refreshes after every attempt, clears busy in finally, prevents duplicate clicks, keeps completed results on read failure, and offers safe status recheck. Exact API proxy passthrough keeps recovery errors JSON. Added isolated offline UI fixture without production auth bypasses.
- Boundaries: no deployment, workflow dispatch, real scan, live database write, billing change, secret configuration, or Task 5+ implementation.
- Evidence after implementation (root-reported): original five recovery tests first failed normally, then passed. `npm run test:web` passes all 150 tests across nine files, with no expected-failing cases; typecheck and lint pass. Production build with fake public values and empty privileged settings passes. Both production HTTP routes return JSON 403 for missing/foreign Origin, JSON 401 signed out, and GET 405 without redirects. Checked browser chunks have no privileged key/admin markers. Actual-dashboard mock browser inspection passed ambiguous/offline/invalid start, failed-read/manual refresh, recent/recovered/race queue, stage polling, no-targets/failed controls, Results/all-listings navigation and target editor checks; screenshots inspected and captured console errors empty. Initial sandbox test/dev startup failed with spawn EPERM, escalated retries passed. Python checks and live Auth/RLS baseline are historical and were not rerun.
- Handoff/next action: Task 4 is locally complete; next is Task 5 Python runner safety, then workflow/docs/account setup and controlled hosted verification. BUILD-001 stays active.

Updates:
- 2026-10-02 — completed — Root completion audit and local checks cover Task 4; five original recovery contracts now pass normally and 51 additional tests extend the 99-test baseline to 150. Recovery has no GitHub configuration or Cloud Run dependency. Local browser fixture renders actual Dashboard/CSS with fake data and `envDir: false`, without bypassing Next authentication; fixture scripts are documented in README. Local servers stopped after verification. No fresh live Auth/RLS check, database write, dispatch, scan, deployment, billing/secret entry, push, or commit occurred.
- 2026-10-02 — completed — Root confirmed temporary ports 3108/3109 stopped and the agent-created browser tab closed; no hosted resources created. Root reports final `git diff --check` passed.

### CTX-011: Record locally verified implementation Tasks 1-3
- Owner: Lily; reviewer/coordinator: root coordinator
- Status: completed
- Updated: 2026-10-02
- Objective: record BUILD-002 local boundaries and distinguish pending recovery/workflow/hosted rollout.
- Owned files: `project-context/context.md`, `project-context/channel.md` only.
- Dependencies: root-reported BUILD-002 implementation and verification; user-confirmed PLAN-002 execution.
- Evidence/checks: current Git status, plan status, package/test configuration, and focused source inspected read-only; application check results supplied by root.
- Changes: recorded user-confirmed plan execution, local Tasks 1-3 completion, final proxy integration/checks, and next Task 4 boundary; historical Python/live-service evidence remains distinguished.
- Handoff/next action: root reports BUILD-002 local completion; Task 4 recovery/UI and later runner/workflow/account/hosted-test work remain pending. No code, plan, secrets, or external state changed in this refresh.

Updates:
- 2026-10-02 — completed — Only context/channel edited. Lily inspected Git status and focused source/plan/test configuration; application checks are root-reported, not rerun by Lily. Documentation consistency and `git diff --check` passed. No onboarding, credential read, live scan, external mutation, or commit.

### BUILD-002: Implement plan Tasks 1-3
- Owner: root coordinator
- Status: completed
- Updated: 2026-10-02
- Objective: deliver the offline web test harness, server-only scan repository/configuration, and authenticated GitHub Scan Now dispatch.
- Owned files: `package.json`, `package-lock.json`, `vitest.config.mts`, `tsconfig.json`, `tests/web/`, `lib/scans/`, `lib/supabase/admin.ts`, `lib/supabase/server.ts` (optional bounded auth transport), `lib/supabase/proxy.ts` (exact Scan Now integration), `app/api/scan/route.ts`, necessary test-tool lint configuration, and task execution status in the implementation plan. Lily owns shared context refresh after verification.
- Authorization: user confirmed the implementation plan and expanded the active goal to Tasks 1, 2, and 3. Task 4 dashboard/recovery implementation and Tasks 5-10 remain later work.
- Evidence: Scan Now now calls the server-only Node GitHub dispatch service; actual recovery still forwards to Cloud Run. Root reports final web tests exited 0 with 94 passed and five explicitly expected-failing Task 4 contracts (99 across seven files), typecheck/lint passed, and production builds passed with privileged scan configuration empty. Five actual-proxy tests verify exact Scan Now passthrough and preserve page/recovery/login gates. Isolated production HTTP checks with fake public configuration verified missing/foreign Origin JSON 403, signed-out POST JSON 401, and GET 405; temporary server stopped. Source inspection confirms request-time configuration, owner/status/cutoff-scoped repository mutations, bounded no-retry dispatch/storage, validated identity/origin/preview guards, and a fake-credential/no-network Vitest harness.
- Handoff: Tasks 1-3 are locally complete; next boundary is Task 4 recovery route/dashboard notices, followed by Python runner/workflow and hosted rollout. No live workflow dispatch, Auth/database mutation, billing, secret entry, deployment, push, or commit in this scope.

Updates:
- 2026-10-02 — active — Implemented Tasks 1-3 with Vitest 5.0.3 pinned, typed configuration, lazy server-only admin/repository operations, and the actual Scan Now route. Initial actual-route red baseline had 11 failures/one pass before replacement. Root reports 89 passed plus five explicitly expected-failing Task 4 contracts, typecheck/lint success, and two passing production builds with privileged scan configuration empty. Initial sandbox build failed spawn EPERM after compilation; escalated retry passed. Browser-chunk checked admin/config markers had zero matches. Final audit found the existing proxy masked unauthenticated API responses with a login redirect; root is correcting exact Scan Now passthrough and adding proxy regression tests before final completion. Python tests were not rerun; earlier 31 remain historical.
- 2026-10-02 — completed — Final proxy fix passes exactly `/api/scan` to its handler before page claims/redirect logic. Five proxy regressions passed; final web count is 94 passed plus five explicit expected-failing Task 4 contracts (99 total/seven files). Typecheck/lint and post-proxy production build with empty privileged scan configuration passed. Isolated production HTTP checks with fake public configuration verified JSON 403/401 and GET 405; temporary server stopped automatically. Root completed the Tasks 1-3 audit; Task 4 route/UI and Tasks 5-10 remain pending. No live Auth/database mutation, dispatch, scan, deployment, billing/secret entry, push, or commit.

### CTX-010: Record approved specification and implementation plan
- Owner: Lily; reviewer/coordinator: root coordinator
- Status: completed
- Updated: 2026-10-02
- Objective: refresh shared context for written-spec approval and the prepared PLAN-002 implementation plan.
- Owned files: `project-context/context.md`, `project-context/channel.md` only; root owns the specification and plan.
- Dependencies: user-reviewed ARCH-002 specification and coordinator-prepared PLAN-002 plan.
- Evidence/checks: repository instructions, context documents, working-tree status, plan/spec status, and the unchanged scan API routes inspected read-only.
- Changes: recorded written-spec approval, PLAN-002 readiness, and the next review/execution milestone; current Cloud Run source and historical test/live-service evidence remain clearly distinguished.
- Blockers/questions: none for this documentation refresh; implementation and hosted rollout remain pending.
- Handoff/next action: root presents the plan for review and execution-method selection, then implements and verifies the switch before private account setup and a controlled hosted scan.

Updates:
- 2026-10-02 — completed — Documentation-only refresh of the two owned files. No application tests, dependency installation, external mutation, billing/secret change, or scan occurred. Root reports plan self-review against all ten tasks and a passing `git diff --check`; Lily performed static context/source consistency checks only.

### PLAN-002: Plan the Vercel and GitHub Actions switch
- Owner: root coordinator
- Status: completed
- Updated: 2026-10-02
- Objective: prepare a concrete, file-scoped implementation and rollout plan from the approved ARCH-002 specification.
- Owned files: `docs/superpowers/plans/2026-10-02-vercel-github-actions-implementation.md`, approval status in the ARCH-002 spec, and this entry. Context refresh follows through Lily.
- Evidence: user reviewed the specification and explicitly requested the implementation plan. Source still forwards both scan routes to Cloud Run; remote HEAD is locally recorded as origin/main; Node 24 and uv are installed.
- Skill fallback: `writing-plans` was not found in the local skills or plugin cache; root is writing the requested plan directly from the approved specification.
- Handoff: user confirmed the [plan](../docs/superpowers/plans/2026-10-02-vercel-github-actions-implementation.md) and execution in this chat. BUILD-002 implements Tasks 1-3; Task 4 and later runner/workflow/account/hosted-test boundaries remain subsequent work.

Updates:
- 2026-10-02 — ready-for-review — Root prepared and self-reviewed all ten implementation/rollout tasks against the approved specification; configuration separates recovery from GitHub dispatch credentials. Root reports `git diff --check` passed. Writing-plans was unavailable; the plan was prepared directly. Application checks were not rerun, dependencies were not installed, and no external mutation occurred.
- 2026-10-02 — completed — User confirmed plan execution in this chat and authorized the Tasks 1-3 milestone. Plan preparation/review is complete; implementation is tracked in BUILD-002 and the overall hosted objective remains BUILD-001.

### ARCH-002: Replace Cloud Run execution with GitHub Actions
- Owner: root coordinator; context refresh: Lily
- Status: completed
- Updated: 2026-10-02
- Objective: preserve the private Scan Now workflow using Vercel Hobby for the frontend/dispatcher, GitHub Actions for Python execution, and Supabase for persistence, without requiring Google Cloud billing.
- Owned files: root owns `docs/superpowers/specs/2026-10-02-vercel-github-actions-design.md`; Lily owns the context refresh and serialized channel updates.
- Evidence: user confirmed personal use and explicitly approved the conversational architecture. The written [specification](../docs/superpowers/specs/2026-10-02-vercel-github-actions-design.md) was self-reviewed and committed locally as `42e8d26` by root; the user then confirmed review and requested the implementation plan. Root recorded approval and linked the prepared plan. Source inspection confirms both scan API routes still forward to Cloud Run and `scan_job.main` already accepts `SCAN_RUN_ID`.
- Approval boundary: architecture, written specification, and PLAN-002 are user approved. No application implementation, external deployment, workflow dispatch, billing change, or secret entry occurred in the original design/planning task; subsequent Tasks 1-3 implementation is tracked in BUILD-002.
- Handoff: BUILD-002 records Tasks 1-3; root proceeds through remaining plan boundaries and BUILD-001 rollout.

Updates:
- 2026-10-02 — ready-for-review — Written spec records queued dispatch, conditional failure/recovery, runner owner validation, secret placement, free-tier controls, and acceptance checks. Cloud Run remains the current source implementation until the switch is built.
- 2026-10-02 — completed — User reviewed the written specification and requested the implementation plan; approval is recorded in the spec. PLAN-002 is prepared for review. This closes architecture/specification work only, not implementation or deployment.

### CTX-009: Record approved Vercel and GitHub Actions architecture
- Owner: Lily; reviewer/coordinator: root coordinator
- Status: completed
- Updated: 2026-10-02
- Objective: distinguish the approved target architecture from the unchanged Cloud Run implementation and update BUILD-001 next steps.
- Owned files: `project-context/context.md`, `project-context/channel.md`
- Dependencies: ARCH-002 written specification and coordinator-provided user approval.
- Evidence/checks: read repository instructions, both context files, the new specification, manifest, scan job entry point, and working-tree status; focused source inspection confirms `CLOUD_RUN_DISPATCH_URL` in both scan routes and Cloud Run settings in `.env.example`.
- Changes: refreshed the approved target flow, preserved current Cloud Run implementation and historical verification evidence, updated BUILD-001 next steps, and relocated ARCH-002 from the working agreement into task entries. Root's specification and all application files were preserved.
- Blockers/questions: written-spec review and implementation planning remain pending; no context blocker.
- Handoff/next action: root presents the concrete written specification for user review, then prepares the implementation plan; no fresh runtime test or external check is claimed.

Updates:
- 2026-10-02 — completed — Documentation-only refresh of the two owned files. Static source inspection and documentation consistency checks only; no implementation, deployment, billing, secret entry, or scan was performed. The earlier 31-test/frontend verification remains dated historical evidence.

### CTX-001: Establish Lily and onboarding instructions
- Owner: root coordinator
- Status: completed
- Updated: 2026-09-29
- Objective: reusable Codex Lily definition and shared project instructions reflecting the actual repository.
- Owned files: `.codex/agents/lily.toml`, `AGENTS.md`, `CLAUDE.md`
- Dependencies: CTX-002 findings inform contributor instructions.
- Evidence/checks: required Lily TOML fields parsed successfully; shared instructions checked against repository source and official Codex configuration documentation.
- Changes: created Codex-native Lily definition and AGENTS.md; CLAUDE.md imports shared instructions for Claude Code compatibility. Removed the initial Cursor definition created during this task.
- Blockers/questions: none reported.
- Handoff/next action: ready for future project work; final evidence is recorded under CTX-003.

Updates:
- 2026-09-29 — completed — Corrected the initial skill-provided Cursor convention after the user asked about Codex compatibility. Codex uses `.agents/skills/` for skills, `.codex/agents/*.toml` for custom agents, and `AGENTS.md` for project instructions. Native discovery in a fresh session remains untested.

### CTX-002: Generate project context and working channel
- Owner: Lily; reviewer: root coordinator
- Status: completed
- Updated: 2026-09-29
- Objective: create concise, source-backed overview/progress and a usable shared agent work log.
- Owned files: `project-context/context.md`, `project-context/channel.md`
- Dependencies: project agent definition available in CTX-001.
- Evidence/checks: read onboarding skill and Lily definition; inspected manifest, README, example config, ignore rules, CLI, cascade, contracts, integrations, helper symbols, prompt, launcher, recent commit subjects, and working-tree status. `Test-Path tests` returned false; `git ls-files tests` returned no files; `git check-ignore tests/probe.py` confirmed exclusion. `git diff --stat` showed no tracked changes during reconnaissance.
- Changes: created both context files with source anchors, lifecycle, setup, contract/convention notes, verified gaps, progress, maintenance, ownership workflow, and this task log.
- Blockers/questions: runtime and installed-wheel behavior remain unverified; no execution was required for this documentation task.
- Handoff/next action: root verifies artifact contents/links and marks CTX-003 complete; update the overview's pending verification when accepted.

Updates:
- 2026-09-29 — completed — Source inspection and document generation finished. No application code changed; no installs, tests, live calls, or credential reads performed. Existing `REFACTORING_AND_CODE_REVIEW.md` left untouched.

### CTX-003: Verify and close the documentation objective
- Owner: root coordinator
- Status: completed
- Updated: 2026-09-29
- Objective: verify the five documentation/agent artifacts, preserve unrelated files, and close the requested goal.
- Owned files: final status corrections in `project-context/context.md` and `project-context/channel.md`; artifact corrections coordinated with Lily.
- Dependencies: CTX-001 and CTX-002.
- Evidence/checks: `ast.parse` succeeded for all 13 `src/deal_finder/*.py` files; `tomllib` parsed the manifest, confirmed `deal_finder.deal_finder:main`, and validated Lily's required fields. All five artifacts exist and are not ignored; relative Markdown links resolve; no stale Cursor references or trailing whitespace remain in current instructions. `git diff --check` passed and no tracked files changed. These are static checks, not test-suite results.
- Changes: verified source anchors, corrected a draft claim about a missing lockfile (tracked `uv.lock` exists), updated native Codex paths, and finalized progress.
- Blockers/questions: none reported.
- Handoff/next action: user or coordinator can assign the next task using the entry template; Lily maintains the overview and shared log.

Updates:
- 2026-09-29 — completed — All requested artifacts created and inspected. Existing untracked review notes were preserved. Application execution, test-suite success, and fresh-session agent discovery were not claimed.

### OPS-001: Verify Supabase MCP connectivity
- Owner: root coordinator
- Status: completed
- Updated: 2026-09-29
- Objective: determine whether Supabase MCP is available and authenticated for this Codex session without changing project or database state.
- Owned files: `project-context/channel.md` only
- Dependencies: none
- Evidence/checks: read `project-context/context.md`; confirmed the application architecture currently uses Google Sheets rather than Supabase; repository root has no `.mcp.json`; the Supabase MCP `list_projects` call succeeded and returned an `ACTIVE_HEALTHY` project named `deal-finder`; a read-only `list_tables` call against its `public` schema succeeded and returned no tables.
- Changes: recorded this connectivity check only; no application, Supabase project, schema, or data changes were made.
- Blockers/questions: none.
- Handoff/next action: Supabase MCP is connected and authenticated; future integration work should first define whether Supabase is intended to replace or supplement Google Sheets.

Updates:
- 2026-09-29 — completed — Verified both account-level and project-level read access through Supabase MCP. The `deal-finder` Supabase project is healthy but its `public` schema is empty.

### ARCH-001: Normalize the live Sheet model and review UI/Supabase seams
- Owner: root coordinator; architecture explorer: architecture_scan
- Status: completed
- Updated: 2026-09-29
- Objective: inspect the configured Google Sheet read-only, propose a normalized relational schema, and produce the requested deep-module architecture review for a future UI and Supabase adapter.
- Owned files: `project-context/channel.md` only; temporary review artifact outside the repository
- Dependencies: OPS-001 confirmed Supabase MCP connectivity; user made the configured Google Sheet publicly readable for this inspection.
- Evidence/checks: exported the live workbook read-only and inspected all four tabs. `Price List` has one populated target plus five formatting/validation rows; `Current Deals` has headers and no records; `All Listings` has 11 unique listings; legacy `History` has 160 unique listing IDs. `History` uses the 12-column legacy contract rather than the current 17-column writer contract. Price List cell G5 contains `=SUM(#REF!)`. History has 58 missing categories, 141 missing bundle values, mixed text/date cell types, and four non-positive savings values; all stored savings otherwise equal deal price minus Carousell price. The architecture explorer independently inspected source and history and supplied four deletion-test-backed deepening candidates.
- Changes: created and opened `C:\Users\johnl\AppData\Local\Temp\architecture-review-20260929-144954.html`, containing the live-workbook findings, a normalized Supabase ERD draft, four architecture candidates, and a top recommendation. No Google Sheet, Supabase project, schema, or application code was changed.
- Blockers/questions: none for the requested analysis deliverables. Tenancy remains a deliberate follow-on decision before owner/workspace columns, RLS, or a migration are finalized. The requested architecture skill also references a `codebase-design` skill that is not installed, so its required vocabulary and principles were applied directly from the architecture skill instead.
- Handoff/next action: analysis is complete. If the user selects a deepening candidate, run the grilling/domain-modeling stage and resolve tenancy before writing a migration or changing application behavior.

Updates:
- 2026-09-29 — ready-for-review — Live workbook evidence replaced the earlier source-only draft. Top recommendation is canonical domain records first, then introduce the real persistence seam while building the Supabase adapter.
- 2026-09-29 — completed — Completion audit confirmed the report and workbook snapshot exist, the report contains the normalized schema plus all four deepening candidates and a top recommendation, the repository still has no `.mcp.json`, and Supabase MCP still sees the `deal-finder` project as `ACTIVE_HEALTHY`. Candidate selection and implementation are optional follow-on work, not missing analysis deliverables.

### BUILD-001: Rebuild Deal Finder as a private hosted application
- Owner: root coordinator; context librarian: Lily; reviewer: unassigned
- Status: active
- Updated: 2026-09-30
- Objective: deliver the approved Supabase-only, on-demand hosted application and verify the complete authenticated Scan Now workflow before retiring the Sheets workflow.
- Owned files: root coordinator owns application and deployment changes until narrower ownership is recorded; Lily owns only `project-context/context.md` and `project-context/channel.md`.
- Dependencies: OPS-001 and ARCH-001 are complete; [design.md](design.md) records the approved Compact List interface.
- Evidence/checks: implementation includes the Next.js frontend, Supabase migration/repository, reusable scan service, Flask dispatcher, Cloud Run job entry point, Docker/deployment documentation, and Python tests. Local checks passed: Python `compileall`, frontend typecheck/lint/build, and 31 pytest tests with one Windows cache warning. Live read-only verification confirms the schema/security/cron, one confirmed allowlisted Auth user with signup and anonymous access disabled, exactly one imported target, and zero scan runs/listings/evaluations. Final code inspector verdict: PASS.
- Changes: canonical hosted application code is present. Results/Dashboard deal data loads only the newest completed scan while the newest overall scan drives progress/status; non-allowed frontend users are redirected through `/auth/denied` and signed out; ESLint ignores generated Python/test caches; dispatcher IAM documentation uses `roles/run.jobsExecutorWithOverrides`; evaluations preserve immutable `target_snapshot_id` and allow multiple target decisions per listing; a lost atomic claim raises `ScanClaimError` without updating status; and the frontend provides authenticated **Release if stuck** recovery for stale queued records.
- Blockers/questions: the live schema exists, but remote migration history is empty because the SQL was run manually. ARCH-002 and PLAN-002 are approved; Tasks 1-4 are locally complete under BUILD-002/BUILD-003. Tasks 5-10 runner/workflow/docs/account setup/spending controls/secrets/controlled scan remain pending. Performance advice remains INFO-only: three unindexed composite foreign keys and unused indexes on the new low-volume tables.
- Handoff/next action: root proceeds to Task 5 Python runner safety, then workflow/docs/account boundaries and a controlled hosted scan. Reconcile migration history without reapplying the live schema. BUILD-001 stays active until hosted execution is verified; Google Cloud billing/deployment is superseded.

Updates:
- 2026-09-30 — active — User approved changing all layers together. The accepted behavior is single-user Supabase email/password access for `dealfinder0322@gmail.com`, closed public registration, editable frontend targets, Scan Now only, one active scan, Cloud Run dispatcher/job, Vercel frontend, and Compact List result rows using Carousell thumbnail URLs with a fallback.
- 2026-09-30 — active — Scan-generated listings, deals, evaluations, status/errors, and history expire after three days; targets persist. Import targets only, retain the CLI temporarily on Supabase, and add no application-enforced 30-minute timeout until completed scans are measured.
- 2026-09-30 — active — Implemented the hosted application locally and resolved backend inspector blockers. Dashboard/Results rows now come only from the newest completed scan, while progress/status follows the newest overall scan. The 72-hour policy exists only in Supabase cleanup, not as a frontend query window.
- 2026-09-30 — active — Added the sole-user page gate (`/auth/denied` signs out disallowed users), safe target deletion (`target_id` becomes null while the immutable snapshot remains), and protected `POST /v1/scans/recover-queued` recovery for owner-scoped queued scans older than 15 minutes by default; running stages are never modified.
- 2026-09-30 — active — Corrected Cloud Run IAM guidance to `roles/run.jobsExecutorWithOverrides` and excluded generated Python/test caches from ESLint. Frontend typecheck/lint/build passed; pytest passed 29 tests with one Windows cache warning. No live migration, deployment, billing change, or secret configuration was performed.
- 2026-09-30 — active — Final reinspection fixes added immutable `target_snapshot_id` with unique `(listing_id, target_snapshot_id)` for multi-target listing evaluations; claim loss now raises `ScanClaimError` without changing scan status; and `/api/scan/recover` powers the queued **Release if stuck** action. Python compileall and frontend typecheck/lint/build passed; pytest now passes 31 tests with the same Windows cache warning. No live services were used.
- 2026-09-30 — active — User manually ran the Supabase SQL. Read-only MCP verification found all four expected public tables empty with RLS, owner policies/authenticated grants, active-scan and snapshot uniqueness, active daily cleanup at `17 3 * * *`, and no security lints. Migration history is empty because the SQL bypassed migration tooling. Performance advisor findings are INFO-only: three unindexed composite foreign keys and unused indexes on empty tables. Final code inspector verdict is PASS; Auth and hosted deployment gates remain.
- 2026-09-30 — active — Auth/target cutover verified. The sole confirmed Auth user is `dealfinder0322@gmail.com` (`749743db-c366-47c9-9373-bec966857b32`); new-user signup and anonymous sign-ins are off, confirm email is on, and email login is enabled. Imported exactly one enabled `legion 5` target from public Price List `B7:K8` with Hardware / `computers-tech` / Item Name / bundle true / PHP 60,000 deal price / null retail / empty keywords and notes. Counts are targets 1 and scan runs/listings/evaluations 0. Hosted deployment remains pending.
- 2026-10-02 — active — User confirmed personal use and approved Vercel Hobby frontend/server dispatch plus GitHub Actions Python execution, replacing Cloud Run as the deployment target. ARCH-002 written specification is self-reviewed and ready for user review. No implementation/deployment/billing/secrets/scan occurred in this design task; historical Supabase and local-check evidence is preserved.
- 2026-10-02 — active — User reviewed the written specification and requested the implementation plan. ARCH-002 approval is recorded; PLAN-002 contains ten self-reviewed implementation/rollout tasks and is ready for review and execution-method selection. Source still uses Cloud Run. No application tests, dependency installation, external mutation, billing/secret configuration, or scan occurred during planning.
- 2026-10-02 — active — User confirmed plan execution and Tasks 1-3. BUILD-002 now implements the offline harness, server-only storage/configuration, and GitHub Scan Now dispatch; actual recovery/UI, runner/workflow, and hosted rollout remain pending. Fresh web/build verification is recorded in BUILD-002; Python and live Supabase evidence remains historical. No live Auth/database mutation, dispatch, scan, deployment, billing/secret configuration, push, or commit occurred.
- 2026-10-02 — active — BUILD-003 Task 4 is locally complete: direct validated Vercel recovery, exact API proxy passthrough, dashboard notices/refresh safeguards, and 150 passing web tests with no expected-failing cases. Typecheck/lint/build, local HTTP, and actual-Dashboard mock-browser checks passed as reported by root. Task 5 Python runner safety is next; Tasks 5-10 and hosted verification remain pending. No fresh live Auth/RLS/database mutation, workflow dispatch, real scan, deployment, billing/secret change, push, or commit.

### CTX-004: Refresh context for the approved hosted rebuild
- Owner: Lily; reviewer/coordinator: root coordinator
- Status: completed
- Updated: 2026-09-30
- Objective: distinguish verified current behavior from the approved redesign, record every accepted architecture/UI decision, and establish durable ownership for the active build.
- Owned files: `project-context/context.md`, `project-context/channel.md`
- Dependencies: BUILD-001 decisions supplied by the coordinator; no application implementation dependency.
- Evidence/checks: read repository instructions, onboarding and Supabase skills, both context documents, `pyproject.toml`, `project-context/design.md`, current Git status, and focused symbols in `deal_finder.py`, `deal_engine.py`, `models.py`, `sheets_handler.py`, `sheets_writer.py`, `.env.example`, and README. Baseline remains commit `96857a4`; existing untracked files were preserved.
- Changes: updated the overview date/objective, added the approved target architecture and current implementation boundary, recorded active build ownership, and preserved all earlier task history.
- Blockers/questions: none for the context refresh. Deployment and application behavior remain unverified because this task made no application, database, or external-service changes.
- Handoff/next action: root reviews this entry and proceeds with BUILD-001; Lily refreshes the context after each substantial architecture or workflow milestone.

Updates:
- 2026-09-30 — completed — Only the two context files were edited. No credential files were read, no application code was changed, and no tests, deployments, migrations, or live pipeline runs were performed.

### CTX-005: Record the locally verified BUILD-001 milestone
- Owner: Lily; reviewer/coordinator: root coordinator
- Status: completed
- Updated: 2026-09-30
- Objective: update shared context for the implemented hosted application, resolved backend inspector findings, and latest local verification without conflating local readiness with remote rollout.
- Owned files: `project-context/context.md`, `project-context/channel.md`
- Dependencies: BUILD-001 implementation and inspector fixes supplied by the coordinator.
- Evidence/checks: inspected current working-tree status and focused source/docs for newest-completed result loading, newest-scan status, denied-user sign-out, queued recovery filters, target snapshots/null references, Supabase cleanup, Cloud Run IAM guidance, ESLint ignores, package scripts, and current entry points. Coordinator-provided verification reports frontend typecheck/lint/build passed and pytest passed 29 tests with one Windows cache warning.
- Changes: refreshed architecture, flow, directory/command, verification, and unresolved-rollout sections; updated BUILD-001 evidence, changes, blockers, handoff, and milestone history.
- Blockers/questions: no context blocker. The Supabase migration and all hosted deployment/billing/secret steps remain unapplied or unperformed.
- Handoff/next action: root reviews the context delta and continues BUILD-001 through the explicit rollout gates.

Updates:
- 2026-09-30 — completed — Only the two context files were edited during this refresh. `project-context/progress-report.md`, application code, migration SQL, deployment configuration, and credentials were not modified.

### CTX-006: Record final BUILD-001 reinspection fixes
- Owner: Lily; reviewer/coordinator: root coordinator
- Status: completed
- Updated: 2026-09-30
- Objective: capture the final evaluation identity, atomic claim safety, queued recovery UI, and verification delta without changing implementation artifacts.
- Owned files: `project-context/context.md`, `project-context/channel.md`
- Dependencies: BUILD-001 reinspection fixes supplied by the coordinator.
- Evidence/checks: inspected `models.py`, `scan_service.py`, the Supabase migration, repository/service tests, `app/api/scan/recover/route.ts`, and the Dashboard recovery action. Coordinator-provided verification reports Python compileall, frontend typecheck/lint/build, and 31 pytest tests passed; pytest emitted one Windows cache warning.
- Changes: updated current BUILD-001 evidence and architecture notes while retaining the earlier 29-test milestone as historical evidence.
- Blockers/questions: no context blocker; live Supabase, Cloud Run, Vercel, billing, secrets, and end-to-end scan verification remain pending.
- Handoff/next action: root reviews the final documentation delta and continues through the controlled rollout gates.

Updates:
- 2026-09-30 — completed — Only `project-context/context.md` and `project-context/channel.md` were edited. The progress report and application/deployment files were preserved.

### CTX-007: Record live Supabase schema verification
- Owner: Lily; reviewer/coordinator: root coordinator
- Status: completed
- Updated: 2026-09-30
- Objective: promote the manually applied Supabase schema to verified live state, preserve migration-history and advisor caveats, and narrow BUILD-001 to the remaining authentication and deployment gates.
- Owned files: `project-context/context.md`, `project-context/channel.md`
- Dependencies: user-applied SQL and coordinator-provided read-only Supabase MCP inspection; final code inspector verdict.
- Evidence/checks: live MCP inspection found four empty public tables, RLS on each, expected owner policies/authenticated grants, active-scan and `(listing_id, target_snapshot_id)` uniqueness, daily cleanup scheduled at `17 3 * * *`, no security-advisor lints, empty migration history, and INFO-only performance findings for three unindexed composite foreign keys plus unused indexes. Final code inspector verdict: PASS.
- Changes: removed stale “unapplied schema” claims, recorded the live database evidence and migration-tracking gap, and updated BUILD-001 blockers/handoff to Auth and hosted rollout work.
- Blockers/questions: migration history needs reconciliation; Auth account/signup settings and all Cloud Run/Vercel/billing/secret/end-to-end deployment checks remain pending.
- Handoff/next action: root continues BUILD-001 from the Auth and deployment gates; do not reapply the live schema blindly.

Updates:
- 2026-09-30 — completed — Documentation-only refresh. No application, database, Auth, deployment, billing, or secret mutation was performed.

### CTX-008: Record Auth and target cutover
- Owner: Lily; reviewer/coordinator: root coordinator
- Status: completed
- Updated: 2026-09-30
- Objective: record the verified sole-user Auth configuration and exact one-target import, then narrow BUILD-001 to migration-history and hosted deployment gates.
- Owned files: `project-context/context.md`, `project-context/channel.md`
- Dependencies: coordinator-provided `auth.users`, dashboard, imported target, and table-count verification.
- Evidence/checks: verified report identifies one email-confirmed Auth user (`dealfinder0322@gmail.com`, UUID `749743db-c366-47c9-9373-bec966857b32`); dashboard settings have new-user signup and anonymous access off, confirm email on, and email provider enabled. Exactly one enabled `legion 5` target from public Price List `B7:K8` exists; scan runs, listings, and evaluations remain empty.
- Changes: updated current Auth/data state, BUILD-001 evidence, remaining blockers, handoff, and milestone history.
- Blockers/questions: remote migration history remains empty; Cloud Run/Vercel, billing, protected secrets, and controlled end-to-end scan remain pending.
- Handoff/next action: root continues with migration-history reconciliation and hosted rollout; do not re-import the target or recreate the Auth user.

Updates:
- 2026-09-30 — completed — Documentation-only refresh. No application, database, Auth, or deployment mutation was performed.
