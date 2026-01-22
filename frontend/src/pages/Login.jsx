// frontend/src/pages/Login.jsx

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api";

export default function Login() {
  const [secretKey, setSecretKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(secretKey);
      navigate("/upload", { replace: true });
    } catch (err) {
      setError(err?.message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ maxWidth: 520, margin: "0 auto" }}>
      <h1 className="h1">Login</h1>
      <p className="muted">Enter the shared passcode to access the app.</p>

      <form onSubmit={onSubmit} className="stack">
        <div className="field">
          <label className="label">Passcode</label>
          <input
            type="password"
            value={secretKey}
            onChange={(e) => setSecretKey(e.target.value)}
            placeholder="Shared passcode"
            disabled={busy}
            autoFocus
          />
        </div>

        {error && <div className="alert">{error}</div>}

        <button className="btn" type="submit" disabled={busy || !secretKey.trim()}>
          {busy ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}
