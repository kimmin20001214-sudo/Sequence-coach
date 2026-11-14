import { useState } from "react";
import { login, type User } from "./api";
import { Card } from "./ui";

export default function Login({ onLogin, notice }: { onLogin: (u: User) => void; notice?: string }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onLogin(await login(username.trim(), password));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="shell">
      <div style={{ maxWidth: 420, margin: "64px auto 0" }}>
        <Card title="로그인" desc="팀장에게 받은 아이디와 비밀번호를 입력해 주세요.">
          <form onSubmit={submit} style={{ display: "grid", gap: 14 }}>
            <label className="field">
              <span className="field-label">아이디</span>
              <input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">비밀번호</span>
              <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            {(error || notice) && <div className="banner err" role="alert">{error || notice}</div>}
            <button type="submit" className="btn primary" disabled={busy || !username.trim() || !password}>
              {busy ? "확인 중…" : "로그인"}
            </button>
          </form>
        </Card>
      </div>
    </div>
  );
}
