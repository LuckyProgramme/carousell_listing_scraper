"use client";

import { FormEvent, useState } from "react";
import { ScanSearch } from "lucide-react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

const ALLOWED_EMAIL = "dealfinder0322@gmail.com";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState(ALLOWED_EMAIL);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (email.trim().toLowerCase() !== ALLOWED_EMAIL) {
      setError("This private app is restricted to its owner account.");
      return;
    }
    setBusy(true);
    const supabase = createClient();
    const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
    if (signInError) {
      setError("The email or password is incorrect.");
      setBusy(false);
      return;
    }
    router.push("/");
    router.refresh();
  }

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-heading">
        <div className="brand"><span className="brand-mark"><ScanSearch aria-hidden="true" /></span><span>Deal Finder</span></div>
        <p className="eyebrow">Private workspace</p>
        <h1 id="login-heading">Sign in to scan your targets</h1>
        <p className="supporting">Your targets and recent results are available only to your account.</p>
        <form onSubmit={signIn}>
          <label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required /></label>
          <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /></label>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button className="primary-button full-button" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
      </section>
    </main>
  );
}
