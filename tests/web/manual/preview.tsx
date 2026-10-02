import { createRoot } from "react-dom/client";
import { DashboardShell } from "@/components/dashboard-shell";
import { advanceScan, initialData, mockFetch, restoreConnection, scenario } from "./mock-client";
import "@/app/globals.css";

// No real credentials, Auth, database, route writes or dispatches in this fixture.
window.fetch = mockFetch;
createRoot(document.getElementById("root")!).render(<>
  <aside aria-label="Offline verification controls" style={{ padding: 12, background: "#fff2cc" }}>
    Offline Task 4 fixture: {scenario}. All requests are mocked. <button type="button" onClick={restoreConnection}>Restore mock connection</button> <button type="button" onClick={advanceScan}>Advance mock scan</button>
  </aside>
  <DashboardShell email="example@example.com" initialData={initialData} />
</>);
