export default function InnstillingerPage() {
  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ marginLeft: 240, background: "var(--canvas)" }}
    >
      <div style={{ textAlign: "center" }}>
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "center",
          width: 48, height: 48, borderRadius: 12,
          background: "var(--surf-2)",
          border: "1px solid var(--bdr-1)",
          margin: "0 auto 16px",
        }}>
          <svg width="20" height="20" viewBox="0 0 16 16" fill="none" style={{ color: "var(--tx-3)" }}>
            <path d="M2 5h12M2 11h12" stroke="currentColor" strokeWidth="1.3"/>
            <circle cx="10" cy="5" r="2" fill="var(--surf-2)" stroke="currentColor" strokeWidth="1.3"/>
            <circle cx="6" cy="11" r="2" fill="var(--surf-2)" stroke="currentColor" strokeWidth="1.3"/>
          </svg>
        </div>
        <p style={{ fontSize: 13, fontWeight: 600, color: "var(--tx-1)", margin: 0 }}>Innstillinger</p>
        <p style={{ fontSize: 12, color: "var(--tx-3)", marginTop: 4 }}>Under arbeid</p>
      </div>
    </div>
  );
}
