# Task 4 offline dashboard inspection

Run from the repository root after installing the pinned web test dependencies:

```powershell
node node_modules/vite/bin/vite.js --config tests/web/manual/vite.config.mts
```

Open `http://127.0.0.1:3108/?scenario=ambiguous`. This renders the actual dashboard and CSS, with an isolated mock client; it never loads `.env`, signs in, writes to Supabase, or dispatches GitHub. It is not a Next.js route and must not be deployed.

Check `ambiguous`, `offline`, `invalid`, and `refresh-failure` by pressing Scan Now. The first three retain the previous deal and disable another start after loading queued status. With `refresh-failure`, busy clears, previous results remain, and Refresh status is available. Use Restore mock connection followed by Refresh status to restore polling without a second POST.

Check `recent`, `race`, and `recovered` with Release if stuck. Recent keeps the queue; race changes to scanning without a release; recovered shows failure/release feedback and permits a new start. `running` never offers release. `failed` offers Try Again; `no-targets` disables starting. Inspect Results and Targets, including the target edit dialog, to confirm unchanged navigation.

This is browser UI evidence only. Production Auth, RLS, deployment, and hosted scans require the later rollout checks.
