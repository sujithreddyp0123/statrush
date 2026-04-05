/**
 * StatRush Frontend v4.0
 *
 * FIX 1  — Zero LLM calls. fetchPrediction() removed entirely.
 * FIX 3  — No hardcoded PLAYERS or PROP_LINES. All data from backend.
 * FIX 10 — Only call: POST /v1/predictions. Render what backend returns.
 *
 * API contract (what backend returns):
 *   { player_id, player_name, stat_type, line, prediction, probability,
 *     confidence, regression, implied_prob, edge_pct, is_high_value,
 *     kelly_fraction, stat_edge, signals, summary, explanation_ready }
 */

import { useState, useEffect } from "react";

const ORANGE  = "#FF6B00";
const ORANGE_B = "#FF8C00";
const OGLOW   = "rgba(255,107,0,0.35)";
const GREEN   = "#00C97A";
const RED     = "#FF4757";

// ─── API base — reads VITE_API_URL at build time, falls back to local ─
const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8001";

// ─── Auth token (in prod: read from localStorage after login) ────────
const getAuthToken = () => localStorage.getItem("sr_token") || "";

// ─── Central API client ──────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const token = getAuthToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

// ─── API calls (FIX 3 + FIX 10) ──────────────────────────────────────
const fetchPlayers = () => apiFetch("/v1/players/");
const fetchProps   = (playerId) => apiFetch(`/v1/props/?player_id=${playerId}`);
const fetchPrediction = (playerId, statType, line) =>
  apiFetch("/v1/predictions/", {
    method: "POST",
    body: JSON.stringify({
      player_id:         playerId,
      stat_type:         statType,
      line:              line,
      game_date:         new Date().toISOString(),
      include_explanation: false,
    }),
  });

// ─── Countdown timer ─────────────────────────────────────────────────
function GameCountdown({ gameTimeUtc }) {
  const [timeLeft, setTimeLeft] = useState("");
  const [status, setStatus] = useState("upcoming");

  useEffect(() => {
    if (!gameTimeUtc) return;
    const calc = () => {
      const now      = new Date();
      const gameTime = new Date(gameTimeUtc);
      const diff     = gameTime - now;
      if (diff <= 0 && diff > -7200000) { setStatus("live");     setTimeLeft("LIVE");  return; }
      if (diff <= -7200000)             { setStatus("final");    setTimeLeft("FINAL"); return; }
      const totalSecs = Math.floor(diff / 1000);
      const hours = Math.floor(totalSecs / 3600);
      const mins  = Math.floor((totalSecs % 3600) / 60);
      const secs  = totalSecs % 60;
      if (hours > 0) {
        setTimeLeft(`${hours}h ${String(mins).padStart(2,"0")}m`);
        setStatus("upcoming");
      } else if (mins <= 30) {
        setTimeLeft(`${String(hours).padStart(2,"0")}:${String(mins).padStart(2,"0")}:${String(secs).padStart(2,"0")}`);
        setStatus("soon");
      } else {
        setTimeLeft(`${mins}m`);
        setStatus("upcoming");
      }
    };
    calc();
    const iv = setInterval(calc, 1000);
    return () => clearInterval(iv);
  }, [gameTimeUtc]);

  const styles = {
    live:     { bg: "rgba(0,201,122,0.15)",    color: "#00C97A", border: "rgba(0,201,122,0.3)" },
    soon:     { bg: "rgba(255,107,0,0.15)",    color: "#FF6B00", border: "rgba(255,107,0,0.3)" },
    upcoming: { bg: "rgba(255,255,255,0.05)",  color: "rgba(255,255,255,0.45)", border: "rgba(255,255,255,0.08)" },
    final:    { bg: "rgba(255,255,255,0.03)",  color: "rgba(255,255,255,0.2)",  border: "rgba(255,255,255,0.05)" },
  };
  const s = styles[status];
  return (
    <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 6, background: s.bg, color: s.color,
      border: `1px solid ${s.border}`, fontFamily: "'DM Mono',monospace", fontWeight: 700,
      letterSpacing: "0.04em", display: "inline-flex", alignItems: "center", gap: 4,
      animation: status === "live" ? "blink 1.5s infinite" : "none" }}>
      {status === "live" && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#00C97A", display: "inline-block" }} />}
      {timeLeft}
    </span>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────
const SRLogo = ({ size = 36 }) => (
  <svg width={size} height={size} viewBox="0 0 100 100">
    <rect x="14" y="14" width="72" height="72" rx="7" fill="none"
      stroke={ORANGE} strokeWidth="5" transform="rotate(45 50 50)"
      style={{ filter: `drop-shadow(0 0 6px rgba(255,107,0,0.6))` }} />
    <polygon points="50,8 44,21 56,21" fill={ORANGE} />
    <polygon points="50,92 44,79 56,79" fill={ORANGE} />
    <text x="50" y="62" textAnchor="middle" fill={ORANGE}
      fontSize="33" fontWeight="900" fontFamily="'Syne',sans-serif" letterSpacing="-2">SR</text>
  </svg>
);

const Ring = ({ confidence }) => {
  const r = 22, cx = 28, cy = 28, sw = 4;
  const circ = 2 * Math.PI * r;
  const col = confidence >= 80 ? ORANGE_B : confidence >= 65 ? "#FFB347" : "#666";
  return (
    <svg width={56} height={56}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={sw} />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={col} strokeWidth={sw}
        strokeDasharray={`${(confidence / 100) * circ} ${circ}`} strokeLinecap="round"
        transform={`rotate(-90 ${cx} ${cy})`}
        style={{ transition: "stroke-dasharray 0.9s ease", filter: confidence >= 65 ? `drop-shadow(0 0 5px ${col})` : "none" }} />
      <text x={cx} y={cy + 5} textAnchor="middle" fill={col}
        fontSize="10" fontWeight="700" fontFamily="'DM Mono',monospace">{confidence}%</text>
    </svg>
  );
};

const EdgeBar = ({ edge }) => {
  const col = edge >= 8 ? GREEN : edge >= 3 ? ORANGE_B : edge >= 0 ? "#FFB347" : "#666";
  const w   = Math.min(Math.abs(edge) / 15 * 100, 100);
  return (
    <div style={{ width: "100%", marginTop: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 9, color: "rgba(255,255,255,0.35)", fontFamily: "'DM Mono',monospace", letterSpacing: "0.1em" }}>EDGE VS BOOK</span>
        <span style={{ fontSize: 11, fontFamily: "'DM Mono',monospace", fontWeight: 700, color: col }}>
          {edge > 0 ? "+" : ""}{edge.toFixed(1)}%
        </span>
      </div>
      <div style={{ height: 4, borderRadius: 2, background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${w}%`, background: col, borderRadius: 2, transition: "width 0.8s ease", boxShadow: edge > 0 ? `0 0 8px ${col}60` : "none" }} />
      </div>
    </div>
  );
};

const Spinner = ({ size = 18 }) => (
  <div style={{ width: size, height: size, border: `2px solid rgba(255,107,0,0.15)`, borderTop: `2px solid ${ORANGE}`, borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />
);

const ErrorBanner = ({ message, onRetry }) => (
  <div style={{ padding: "12px 16px", background: "rgba(255,71,87,0.08)", border: "1px solid rgba(255,71,87,0.2)", borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
    <span style={{ fontSize: 13, color: RED }}>⚠ {message}</span>
    {onRetry && <button onClick={onRetry} style={{ fontSize: 11, color: ORANGE, background: "none", border: "none", cursor: "pointer", fontFamily: "'DM Mono',monospace" }}>Retry</button>}
  </div>
);

// ─── Main App ─────────────────────────────────────────────────────────
export default function StatRush() {
  // ── Games sidebar state ───────────────────────────────────────
  const [games,        setGames]        = useState([]);
  const [gamesLoading, setGamesLoading] = useState(true);
  const [expandedGame, setExpandedGame] = useState(null);

  // ── Player data (fallback + search) ──────────────────────────
  const [players, setPlayers] = useState([]);

  const [sel,    setSel]    = useState(null);
  const [props,  setProps]  = useState([]);
  const [propsLoading, setPropsLoading] = useState(false);
  const [propsError,   setPropsError]   = useState(null);

  // ── Predictions ───────────────────────────────────────────────
  const [preds, setPreds] = useState({});

  // ── UI state ──────────────────────────────────────────────────
  const [query,    setQuery]    = useState("");
  const [showDrop, setShowDrop] = useState(false);
  const [tab,      setTab]      = useState("props");
  const [exp,      setExp]      = useState(null);

  // ── Load games on mount ───────────────────────────────────────
  useEffect(() => {
    apiFetch("/v1/games/today")
      .then(data => {
        setGames(data || []);
        setGamesLoading(false);
        if (data && data.length > 0) {
          setExpandedGame(data[0].game_id);
          if (data[0].players.length > 0) setSel(data[0].players[0]);
        }
      })
      .catch(() => {
        setGamesLoading(false);
        fetchPlayers().then(p => { setPlayers(p); if (p.length) setSel(p[0]); });
      });
    // Always load players for search fallback
    fetchPlayers().then(setPlayers).catch(() => {});
  }, []);

  // ── Load props when player changes ───────────────────────────
  useEffect(() => {
    if (!sel) return;
    setProps([]);
    setPropsError(null);
    setPropsLoading(true);
    setExp(null);
    fetchProps(sel.id)
      .then(data => { setProps(data); setPropsLoading(false); })
      .catch(e => { setPropsError(e.message); setPropsLoading(false); });
  }, [sel?.id]);

  // ── Fetch predictions when props load ────────────────────────
  useEffect(() => {
    if (!sel || props.length === 0) return;
    props.forEach(prop => {
      const key = `${sel.id}_${prop.stat_type}`;
      if (preds[key]) return;
      setPreds(prev => ({ ...prev, [key]: { loading: true, data: null, error: null } }));
      fetchPrediction(sel.id, prop.stat_type, prop.line)
        .then(data => setPreds(prev => ({ ...prev, [key]: { loading: false, data, error: null } })))
        .catch(e   => setPreds(prev => ({ ...prev, [key]: { loading: false, data: null, error: e.message } })));
    });
  }, [sel?.id, props]);

  // ── Search filter ─────────────────────────────────────────────
  const filtered = query
    ? (players || []).filter(p => (p.name || "").toLowerCase().includes(query.toLowerCase()) || (p.team || "").toLowerCase().includes(query.toLowerCase()))
    : [];

  const handleSelectPlayer = (p) => {
    setSel(p);
    setQuery("");
    setShowDrop(false);
    setExp(null);
  };

  const retryPred = (prop) => {
    const key = `${sel.id}_${prop.stat_type}`;
    setPreds(prev => ({ ...prev, [key]: { loading: true, data: null, error: null } }));
    fetchPrediction(sel.id, prop.stat_type, prop.line)
      .then(data => setPreds(prev => ({ ...prev, [key]: { loading: false, data, error: null } })))
      .catch(e   => setPreds(prev => ({ ...prev, [key]: { loading: false, data: null, error: e.message } })));
  };

  const statLabel = (s) => s.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());

  return (
    <div style={{ width: "100vw", minHeight: "100vh", background: "#090909", color: "#DDD8D0", fontFamily: "'DM Sans',sans-serif", position: "relative", overflowX: "hidden" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=DM+Mono:wght@400;500;700&family=Syne:wght@700;800;900&display=swap');
        *{box-sizing:border-box;margin:0;padding:0}
        ::-webkit-scrollbar{width:3px}
        ::-webkit-scrollbar-thumb{background:rgba(255,107,0,0.2);border-radius:2px}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}
        @keyframes fu{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
        @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
        @keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}
        .fu{animation:fu 0.35s ease forwards}
        .card{background:rgba(255,255,255,0.025);border:1px solid rgba(255,255,255,0.07);border-radius:14px}
        .prop{background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:16px 18px;cursor:pointer;transition:all 0.2s}
        .prop:hover{background:rgba(255,107,0,0.04);border-color:rgba(255,107,0,0.18)}
        .prop.open{background:rgba(255,107,0,0.05);border-color:rgba(255,107,0,0.28)}
        .prop.highval{border-color:rgba(0,201,122,0.25)!important;background:rgba(0,201,122,0.03)!important}
        .pchip{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:10px;cursor:pointer;border:1px solid transparent;transition:all 0.15s}
        .pchip:hover{background:rgba(255,107,0,0.06)}
        .pchip.on{background:rgba(255,107,0,0.1);border-color:rgba(255,107,0,0.22)}
        .tbtn{padding:7px 14px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;transition:all 0.15s;color:rgba(255,255,255,0.4);border:none;background:transparent;font-family:'DM Sans',sans-serif}
        .tbtn.on{background:rgba(255,107,0,0.1);color:${ORANGE};border:1px solid rgba(255,107,0,0.22)}
        .srch{width:100%;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.09);border-radius:10px;padding:10px 16px;color:#fff;font-size:14px;font-family:'DM Sans',sans-serif;outline:none;transition:all 0.2s}
        .srch:focus{border-color:rgba(255,107,0,0.45);box-shadow:0 0 0 3px rgba(255,107,0,0.07)}
        .srch::placeholder{color:rgba(255,255,255,0.22)}
        .drop{position:absolute;top:calc(100% + 6px);left:0;right:0;background:#111;border:1px solid rgba(255,107,0,0.2);border-radius:10px;overflow:hidden;z-index:200;box-shadow:0 20px 50px rgba(0,0,0,0.7)}
        .di{padding:11px 16px;cursor:pointer;font-size:13px;transition:background 0.12s}
        .di:hover{background:rgba(255,107,0,0.08)}
        .sbox{flex:1;padding:11px;background:rgba(255,255,255,0.025);border-radius:9px;border:1px solid rgba(255,255,255,0.06);text-align:center}
        .live{animation:blink 1.8s infinite}
        .skel{background:rgba(255,255,255,0.04);border-radius:6px;animation:pulse 1.6s ease-in-out infinite}
      `}</style>

      <div style={{ position: "fixed", width: 700, height: 700, top: -250, right: -200, borderRadius: "50%", background: "rgba(255,107,0,0.04)", filter: "blur(120px)", pointerEvents: "none" }} />

      {/* HEADER */}
      <header style={{ position: "sticky", top: 0, zIndex: 100, background: "rgba(9,9,9,0.94)", backdropFilter: "blur(20px)", borderBottom: "1px solid rgba(255,107,0,0.1)", padding: "12px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <SRLogo size={36} />
          <div>
            <div style={{ fontFamily: "'Syne',sans-serif", fontSize: 21, fontWeight: 900, letterSpacing: "-0.5px", color: "#fff", lineHeight: 1.1 }}>
              Stat<span style={{ color: ORANGE, textShadow: `0 0 18px ${OGLOW}` }}>Rush</span>
            </div>
            <div style={{ fontSize: 9, color: "rgba(255,107,0,0.55)", fontFamily: "'DM Mono',monospace", letterSpacing: "0.14em" }}>AI PROP ANALYTICS</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <div className="live" style={{ width: 6, height: 6, borderRadius: "50%", background: GREEN, boxShadow: `0 0 7px ${GREEN}` }} />
            <span style={{ fontSize: 10, color: "rgba(255,255,255,0.35)", fontFamily: "'DM Mono',monospace" }}>LIVE</span>
          </div>
          <div style={{ padding: "5px 12px", borderRadius: 8, background: "rgba(255,107,0,0.08)", border: "1px solid rgba(255,107,0,0.18)", fontSize: 10, color: "rgba(255,255,255,0.4)", fontFamily: "'DM Mono',monospace" }}>
            ML-FIRST · v4
          </div>
          <div style={{ width: 30, height: 30, borderRadius: 8, background: `linear-gradient(135deg,${ORANGE},#CC4400)`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, color: "#fff", boxShadow: `0 0 14px rgba(255,107,0,0.4)`, cursor: "pointer" }}>S</div>
        </div>
      </header>

      <div style={{ display: "flex", height: "calc(100vh - 65px)", position: "relative", zIndex: 1 }}>

        {/* SIDEBAR — Games */}
        <aside style={{ width: 232, borderRight: "1px solid rgba(255,107,0,0.09)", padding: 0, display: "flex", flexDirection: "column", overflowY: "auto", flexShrink: 0, background: "rgba(0,0,0,0.18)" }}>

          <div style={{ fontSize: 9, fontFamily: "'DM Mono',monospace", color: "rgba(255,107,0,0.45)", letterSpacing: "0.14em", padding: "18px 16px 8px" }}>
            NBA · UPCOMING GAMES
          </div>

          {/* Loading skeletons */}
          {gamesLoading && [0,1,2].map(i => (
            <div key={i} style={{ padding: "12px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
              <div className="skel" style={{ height: 12, width: "60%", marginBottom: 6 }} />
              <div className="skel" style={{ height: 9, width: "40%" }} />
            </div>
          ))}

          {/* Game rows */}
          {games.map(game => (
            <div key={game.game_id}>

              {/* Game header — clickable */}
              <div
                onClick={() => setExpandedGame(expandedGame === game.game_id ? null : game.game_id)}
                style={{
                  padding: "12px 16px",
                  borderBottom: "1px solid rgba(255,255,255,0.04)",
                  cursor: "pointer",
                  background: expandedGame === game.game_id ? "rgba(255,107,0,0.08)" : "transparent",
                  transition: "background 0.15s",
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                }}
              >
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "#fff", marginBottom: 4 }}>
                    {game.players.map(p => p.team).filter((t, i, a) => t && a.indexOf(t) === i).join(" vs ") || "NBA Game"}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <GameCountdown gameTimeUtc={game.game_time_utc} />
                    <span style={{ fontSize: 9, color: "rgba(255,255,255,0.3)", fontFamily: "'DM Mono',monospace" }}>
                      {game.prop_count} props
                    </span>
                  </div>
                </div>
                <span style={{ color: "rgba(255,255,255,0.3)", fontSize: 10, display: "inline-block",
                  transition: "transform 0.2s",
                  transform: expandedGame === game.game_id ? "rotate(180deg)" : "none" }}>▾</span>
              </div>

              {/* Players in game */}
              {expandedGame === game.game_id && (
                <div style={{ background: "rgba(0,0,0,0.2)" }}>
                  {game.players.map(player => {
                    const key  = Object.keys(preds).find(k => k.startsWith(`${player.id}_points`));
                    const pred = preds[key]?.data;
                    const initials = (player.name || "??").split(" ").map(w => w[0]).join("").slice(0, 2);
                    return (
                      <div
                        key={player.id}
                        className={`pchip ${sel?.id === player.id ? "on" : ""}`}
                        style={{ margin: "2px 8px", borderRadius: 8 }}
                        onClick={() => { setSel(player); setExp(null); }}
                      >
                        <div style={{
                          width: 32, height: 32, borderRadius: 9,
                          background: sel?.id === player.id ? "rgba(255,107,0,0.16)" : "rgba(255,255,255,0.05)",
                          border: sel?.id === player.id ? "1px solid rgba(255,107,0,0.28)" : "1px solid transparent",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: 10, fontWeight: 700, fontFamily: "'DM Mono',monospace",
                          color: sel?.id === player.id ? ORANGE : "rgba(255,255,255,0.45)",
                          flexShrink: 0,
                        }}>
                          {initials}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 12, fontWeight: 600,
                            color: sel?.id === player.id ? "#fff" : "rgba(255,255,255,0.65)",
                            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {player.name}
                          </div>
                          <div style={{ fontSize: 10, color: "rgba(255,255,255,0.3)" }}>
                            {player.team} · {player.position || "NBA"}
                          </div>
                        </div>
                        {pred && (
                          <span style={{
                            fontSize: 10, fontFamily: "'DM Mono',monospace", fontWeight: 700,
                            color: pred.edge_pct >= 8 ? GREEN : pred.edge_pct >= 3 ? ORANGE_B : "#666",
                            flexShrink: 0,
                          }}>
                            {pred.edge_pct > 0 ? "+" : ""}{pred.edge_pct?.toFixed(1)}%
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}

          {/* No games fallback */}
          {!gamesLoading && games.length === 0 && (
            <div style={{ padding: "16px", fontSize: 12, color: "rgba(255,255,255,0.3)", textAlign: "center" }}>
              No games scheduled today
            </div>
          )}

          <div style={{ marginTop: "auto", padding: "14px 16px", borderTop: "1px solid rgba(255,107,0,0.08)" }}>
            <div style={{ fontSize: 9, color: "rgba(255,255,255,0.18)", fontFamily: "'DM Mono',monospace", lineHeight: 1.9 }}>
              XGB + LGBM ensemble<br />Explanations via Claude API
            </div>
          </div>
        </aside>

        {/* MAIN */}
        <main style={{ flex: 1, overflowY: "auto", padding: "22px 26px" }}>

          {/* Search */}
          <div style={{ position: "relative", marginBottom: 20 }}>
            <input className="srch" value={query}
              onChange={e => { setQuery(e.target.value); setShowDrop(true); }}
              placeholder="🔍  Search player or team..."
              onBlur={() => setTimeout(() => setShowDrop(false), 180)} />
            {showDrop && filtered.length > 0 && (
              <div className="drop">
                {(filtered || []).map(p => (
                  <div key={p.id} className="di" onClick={() => handleSelectPlayer(p)}>
                    <span style={{ fontWeight: 600, color: "#fff" }}>{p.name}</span>
                    <span style={{ color: "rgba(255,255,255,0.3)", marginLeft: 10, fontSize: 11 }}>{p.team} · {p.position}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Hero — rendered from backend data only */}
          {sel && (
            <div className="card fu" style={{ padding: "20px 22px", marginBottom: 18, display: "flex", alignItems: "center", gap: 18, borderColor: "rgba(255,107,0,0.12)" }}>
              <div style={{ width: 58, height: 58, borderRadius: 15, background: "rgba(255,107,0,0.09)", border: "1.5px solid rgba(255,107,0,0.28)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18, fontWeight: 800, fontFamily: "'DM Mono',monospace", color: ORANGE, flexShrink: 0, boxShadow: "0 0 20px rgba(255,107,0,0.18)" }}>
                {(sel.name || "??").split(" ").map(w => w[0]).join("").slice(0,2)}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6, flexWrap: "wrap" }}>
                  <h1 style={{ fontFamily: "'Syne',sans-serif", fontSize: 22, fontWeight: 800, color: "#fff", letterSpacing: "-0.4px" }}>{sel.name}</h1>
                  {[sel.position, sel.team].map(t => (
                    <span key={t} style={{ fontSize: 10, padding: "2px 8px", borderRadius: 5, background: "rgba(255,255,255,0.05)", color: "rgba(255,255,255,0.45)", border: "1px solid rgba(255,255,255,0.07)" }}>{t}</span>
                  ))}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 11, color: "rgba(255,255,255,0.35)" }}>
                    {propsLoading ? "Loading props..." : `${props.length} props available tonight`}
                  </span>
                  {props[0]?.game_time_utc && <GameCountdown gameTimeUtc={props[0].game_time_utc} />}
                </div>
              </div>
            </div>
          )}

          {/* Live games banner */}
          {props.some(p => {
            if (!p.game_time_utc) return false;
            const diff = new Date(p.game_time_utc) - new Date();
            return diff <= 0 && diff > -7200000;
          }) && (
            <div style={{ marginBottom: 14, padding: "8px 16px", background: "rgba(0,201,122,0.08)",
              border: "1px solid rgba(0,201,122,0.2)", borderRadius: 10,
              display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#00C97A",
                animation: "blink 1.5s infinite" }} />
              <span style={{ fontSize: 12, color: "#00C97A",
                fontFamily: "'DM Mono',monospace", fontWeight: 700 }}>GAMES IN PROGRESS</span>
            </div>
          )}

          {/* Tabs */}
          <div style={{ display: "flex", gap: 5, marginBottom: 16 }}>
            {[["props","🎯 Props"],["stats","📊 ML Signals"]].map(([t, label]) => (
              <button key={t} className={`tbtn ${tab === t ? "on" : ""}`} onClick={() => setTab(t)}>{label}</button>
            ))}
          </div>

          {/* Props error */}
          {propsError && <ErrorBanner message={`Props: ${propsError}`} onRetry={() => { if (sel) { setPropsLoading(true); fetchProps(sel.id).then(d => { setProps(d); setPropsLoading(false); }).catch(e => { setPropsError(e.message); setPropsLoading(false); }); }}} />}

          {/* PROPS TAB — FIX 10: renders backend response fields directly */}
          {tab === "props" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {propsLoading && [0,1,2].map(i => (
                <div key={i} className="prop" style={{ display: "flex", alignItems: "center", gap: 14 }}>
                  <div className="skel" style={{ width: 56, height: 56, borderRadius: "50%" }} />
                  <div style={{ flex: 1 }}>
                    <div className="skel" style={{ height: 14, width: "35%", marginBottom: 8 }} />
                    <div className="skel" style={{ height: 9, width: "55%" }} />
                  </div>
                </div>
              ))}

              {!propsLoading && props.map((prop, i) => {
                const key   = `${sel?.id}_${prop.stat_type}`;
                const state = preds[key];
                const pred  = state?.data;
                const isLoading = !state || state.loading;

                if (isLoading) return (
                  <div key={i} className="prop fu" style={{ display: "flex", alignItems: "center", gap: 14, animationDelay: `${i*50}ms` }}>
                    <Spinner />
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: "#fff", marginBottom: 3 }}>
                        {statLabel(prop.stat_type)}
                        <span style={{ color: "rgba(255,255,255,0.4)", fontFamily: "'DM Mono',monospace", fontSize: 13, marginLeft: 8 }}>{prop.line}</span>
                      </div>
                      <div style={{ fontSize: 10, color: "rgba(255,107,0,0.5)", fontFamily: "'DM Mono',monospace" }}>Computing edge...</div>
                    </div>
                  </div>
                );

                if (state?.error) return (
                  <div key={i} className="prop fu">
                    <ErrorBanner message={`${statLabel(prop.stat_type)}: ${state.error}`} onRetry={() => retryPred(prop)} />
                  </div>
                );

                if (!pred) return null;

                // FIX 10: render ONLY what backend returned
                const lineMov = prop.open_line != null ? prop.line - prop.open_line : 0;

                return (
                  <div key={i} className={`prop ${exp === i ? "open" : ""} ${pred.is_high_value ? "highval" : ""} fu`}
                    style={{ animationDelay: `${i*55}ms` }}
                    onClick={() => setExp(exp === i ? null : i)}>

                    {pred.is_high_value && (
                      <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 6 }}>
                        <div style={{ width: 5, height: 5, borderRadius: "50%", background: GREEN, boxShadow: `0 0 6px ${GREEN}` }} />
                        <span style={{ fontSize: 9, color: GREEN, fontFamily: "'DM Mono',monospace", letterSpacing: "0.1em", fontWeight: 700 }}>HIGH VALUE — +{pred.edge_pct?.toFixed(1)}% EDGE</span>
                      </div>
                    )}

                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <Ring confidence={pred.confidence} />
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
                          <span style={{ fontWeight: 700, fontSize: 15, color: "#fff" }}>{statLabel(prop.stat_type)}</span>
                          <span style={{ fontFamily: "'DM Mono',monospace", fontSize: 14, color: "rgba(255,255,255,0.55)" }}>{prop.line}</span>
                          {prop.bookmaker && (
                            <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 4,
                              background: "rgba(255,107,0,0.1)", color: "#FF8C00",
                              fontFamily: "'DM Mono',monospace", border: "1px solid rgba(255,107,0,0.18)" }}>
                              {prop.bookmaker.toUpperCase()}
                            </span>
                          )}
                          <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 9px", borderRadius: 6, fontFamily: "'DM Mono',monospace",
                            ...(pred.prediction?.toLowerCase() === "over"
                              ? { background: "rgba(255,107,0,0.14)", color: ORANGE_B, border: "1px solid rgba(255,107,0,0.28)" }
                              : { background: "rgba(100,100,100,0.1)", color: "#888", border: "1px solid rgba(100,100,100,0.18)" })
                          }}>{(pred.prediction || "").toUpperCase()}</span>
                          {lineMov !== 0 && (
                            <span style={{ fontSize: 9, padding: "2px 7px", borderRadius: 5, fontFamily: "'DM Mono',monospace",
                              background: lineMov > 0 ? "rgba(255,107,0,0.1)" : "rgba(255,71,87,0.1)",
                              color: lineMov > 0 ? ORANGE_B : RED,
                              border: `1px solid ${lineMov > 0 ? "rgba(255,107,0,0.2)" : "rgba(255,71,87,0.2)"}` }}>
                              {lineMov > 0 ? "▲" : "▼"} {Math.abs(lineMov).toFixed(1)}
                            </span>
                          )}
                        </div>
                        <EdgeBar edge={pred.edge_pct || 0} />
                      </div>
                      <span style={{ color: "rgba(255,255,255,0.22)", fontSize: 11, transition: "transform 0.25s", transform: exp === i ? "rotate(180deg)" : "none", display: "inline-block", marginLeft: 6 }}>▾</span>
                    </div>

                    {/* Expanded — all values from backend */}
                    {exp === i && (
                      <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid rgba(255,107,0,0.1)" }}>

                        {/* AI explanation (from backend LLM layer) */}
                        {pred.summary && (
                          <div style={{ marginBottom: 14, padding: "12px 14px", background: "rgba(255,107,0,0.06)", borderRadius: 10, border: "1px solid rgba(255,107,0,0.14)" }}>
                            <div style={{ fontSize: 9, fontFamily: "'DM Mono',monospace", color: "rgba(255,107,0,0.6)", letterSpacing: "0.1em", marginBottom: 6 }}>
                              ⚡ AI ANALYSIS {!pred.explanation_ready && <span style={{ color: "rgba(255,255,255,0.25)" }}>(loading…)</span>}
                            </div>
                            <div style={{ fontSize: 13, color: "rgba(255,255,255,0.7)", lineHeight: 1.6 }}>{pred.summary}</div>
                          </div>
                        )}

                        {/* Signals */}
                        {pred.signals?.length > 0 && (
                          <>
                            <div style={{ fontSize: 9, fontFamily: "'DM Mono',monospace", color: "rgba(255,107,0,0.55)", letterSpacing: "0.12em", marginBottom: 10 }}>ML SIGNALS</div>
                            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
                              {pred.signals.map((s, j) => (
                                <div key={j} style={{ display: "flex", alignItems: "flex-start", gap: 9 }}>
                                  <div style={{ width: 4, height: 4, borderRadius: "50%", background: ORANGE, marginTop: 7, flexShrink: 0, boxShadow: `0 0 6px ${ORANGE}` }} />
                                  <span style={{ fontSize: 12, color: "rgba(255,255,255,0.55)", lineHeight: 1.5 }}>{s}</span>
                                </div>
                              ))}
                            </div>
                          </>
                        )}

                        {/* Bookmaker comparison table */}
                        {prop.all_books && prop.all_books.length > 1 && (
                          <div style={{ marginBottom: 16 }}>
                            <div style={{ fontSize: 9, fontFamily: "'DM Mono',monospace", color: "rgba(255,107,0,0.55)", letterSpacing: "0.12em", marginBottom: 8 }}>ODDS COMPARISON</div>
                            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                              {prop.all_books.map((b, k) => (
                                <div key={k} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", borderRadius: 7, background: b.is_best ? "rgba(255,107,0,0.07)" : "rgba(255,255,255,0.025)", border: b.is_best ? "1px solid rgba(255,107,0,0.2)" : "1px solid rgba(255,255,255,0.05)" }}>
                                  <span style={{ flex: 1, fontSize: 11, color: b.is_best ? "rgba(255,255,255,0.8)" : "rgba(255,255,255,0.4)", fontFamily: "'DM Mono',monospace" }}>
                                    {(b.bookmaker || "—").toUpperCase()}
                                  </span>
                                  <span style={{ fontSize: 13, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: b.is_best ? ORANGE_B : "rgba(255,255,255,0.5)" }}>{b.line}</span>
                                  {b.over_odds && <span style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", fontFamily: "'DM Mono',monospace" }}>o{b.over_odds > 0 ? "+" : ""}{b.over_odds}</span>}
                                  {b.under_odds && <span style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", fontFamily: "'DM Mono',monospace" }}>u{b.under_odds > 0 ? "+" : ""}{b.under_odds}</span>}
                                  {b.is_best && <span style={{ fontSize: 8, padding: "1px 5px", borderRadius: 3, background: "rgba(255,107,0,0.15)", color: ORANGE, fontFamily: "'DM Mono',monospace", border: "1px solid rgba(255,107,0,0.25)" }}>BEST</span>}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Numbers grid — all from backend */}
                        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
                          {[
                            ["CONFIDENCE", `${pred.confidence}%`,   pred.confidence >= 80 ? ORANGE_B : pred.confidence >= 65 ? "#FFB347" : "#777"],
                            ["MODEL PROB", `${(pred.probability * 100).toFixed(0)}%`, "#fff"],
                            ["IMPLIED",    `${(pred.implied_prob * 100).toFixed(0)}%`, "#888"],
                            ["EDGE",       `${pred.edge_pct > 0 ? "+" : ""}${pred.edge_pct?.toFixed(1)}%`, pred.edge_pct >= 8 ? GREEN : pred.edge_pct >= 3 ? ORANGE_B : "#666"],
                          ].map(([label, val, col]) => (
                            <div key={label} className="sbox">
                              <div style={{ fontSize: 8, color: "rgba(255,255,255,0.28)", fontFamily: "'DM Mono',monospace", letterSpacing: "0.1em", marginBottom: 4 }}>{label}</div>
                              <div style={{ fontSize: 15, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: col }}>{val}</div>
                            </div>
                          ))}
                        </div>

                        {/* Kelly sizing */}
                        {pred.kelly_fraction > 0 && pred.edge_pct > 0 && (
                          <div style={{ padding: "10px 14px", background: "rgba(0,201,122,0.05)", borderRadius: 9, border: "1px solid rgba(0,201,122,0.12)", display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                            <div>
                              <div style={{ fontSize: 9, color: "rgba(0,201,122,0.6)", fontFamily: "'DM Mono',monospace", letterSpacing: "0.1em", marginBottom: 3 }}>KELLY SIZING</div>
                              <div style={{ fontSize: 11, color: "rgba(255,255,255,0.45)" }}>Suggested {(pred.kelly_fraction * 100).toFixed(1)}% of bankroll</div>
                            </div>
                            <div style={{ fontSize: 16, fontFamily: "'DM Mono',monospace", fontWeight: 700, color: GREEN }}>{(pred.kelly_fraction * 100).toFixed(1)}%</div>
                          </div>
                        )}

                        {/* Projection line */}
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <div style={{ flex: 1, height: 1, background: "rgba(255,255,255,0.05)" }} />
                          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.4)" }}>
                            Projected: <span style={{ fontFamily: "'DM Mono',monospace", color: ORANGE_B, fontWeight: 700 }}>{pred.regression}</span>
                            <span style={{ color: "rgba(255,255,255,0.3)", marginLeft: 6 }}>vs line {prop.line}</span>
                          </span>
                          <div style={{ flex: 1, height: 1, background: "rgba(255,255,255,0.05)" }} />
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* ML SIGNALS TAB */}
          {tab === "stats" && sel && (
            <div className="card fu" style={{ padding: 22 }}>
              <div style={{ fontSize: 10, color: "rgba(255,255,255,0.28)", fontFamily: "'DM Mono',monospace", letterSpacing: "0.1em", marginBottom: 18 }}>
                PREDICTION SUMMARY — {(sel.name || "").toUpperCase()}
              </div>
              {props.length === 0 && !propsLoading && (
                <div style={{ color: "rgba(255,255,255,0.35)", fontSize: 13 }}>No props loaded.</div>
              )}
              {(props || []).map((prop, i) => {
                const key  = `${sel.id}_${prop.stat_type}`;
                const pred = preds[key]?.data;
                if (!pred) return null;
                return (
                  <div key={i} style={{ marginBottom: 14, padding: "14px 16px", background: "rgba(255,255,255,0.025)", borderRadius: 11, border: "1px solid rgba(255,255,255,0.06)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                      <span style={{ fontWeight: 700, fontSize: 14, color: "#fff" }}>{statLabel(prop.stat_type)}</span>
                      <span style={{ fontFamily: "'DM Mono',monospace", fontSize: 12,
                        color: pred.prediction?.toLowerCase() === "over" ? ORANGE_B : "#888",
                        fontWeight: 700 }}>{(pred.prediction || "").toUpperCase()} {prop.line}</span>
                    </div>
                    <div style={{ display: "flex", gap: 8 }}>
                      {[
                        ["Confidence",  `${pred.confidence}%`],
                        ["Probability", `${(pred.probability * 100).toFixed(0)}%`],
                        ["Edge",        `${pred.edge_pct > 0 ? "+" : ""}${pred.edge_pct?.toFixed(1)}%`],
                        ["Projection",  `${pred.regression}`],
                      ].map(([k, v]) => (
                        <div key={k} style={{ flex: 1, textAlign: "center" }}>
                          <div style={{ fontSize: 8, color: "rgba(255,255,255,0.3)", fontFamily: "'DM Mono',monospace", marginBottom: 4 }}>{k.toUpperCase()}</div>
                          <div style={{ fontSize: 14, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: ORANGE_B }}>{v}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </main>

        {/* RIGHT RAIL */}
        <aside style={{ width: 206, borderLeft: "1px solid rgba(255,107,0,0.09)", padding: "18px 13px", flexShrink: 0, overflowY: "auto", background: "rgba(0,0,0,0.14)" }}>
          <div style={{ fontSize: 9, fontFamily: "'DM Mono',monospace", color: "rgba(255,107,0,0.45)", letterSpacing: "0.14em", marginBottom: 13 }}>TOP EDGE · TODAY</div>

          {(players || []).map(p => {
            const key  = Object.keys(preds).find(k => k.startsWith(`${p.id}_`));
            const pred = key ? preds[key]?.data : null;
            const statStr = key ? key.split("_").slice(1).join("_") : null;
            const propLine = (props || []).find(pr => pr.stat_type === statStr)?.line;
            return (
              <div key={p.id} style={{ padding: "10px 0", borderBottom: "1px solid rgba(255,255,255,0.05)", cursor: "pointer" }}
                onClick={() => handleSelectPlayer(p)}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: sel?.id === p.id ? ORANGE : "#fff" }}>
                    {(p.name || "").split(" ").pop()}
                  </span>
                  {pred
                    ? <span style={{ fontSize: 10, fontFamily: "'DM Mono',monospace", fontWeight: 700, color: pred.edge_pct >= 8 ? GREEN : pred.edge_pct >= 3 ? ORANGE_B : "#666" }}>
                        {pred.edge_pct > 0 ? "+" : ""}{pred.edge_pct?.toFixed(1)}%
                      </span>
                    : <div style={{ width: 28, height: 8, borderRadius: 4, background: "rgba(255,107,0,0.08)", animation: "pulse 1.6s infinite" }} />
                  }
                </div>
                {pred && statStr && (
                  <div style={{ fontSize: 10, color: "rgba(255,255,255,0.28)", fontFamily: "'DM Mono',monospace" }}>
                    {statLabel(statStr)} {pred.prediction?.toLowerCase() === "over" ? "O" : "U"} {propLine}
                  </div>
                )}
              </div>
            );
          })}

          <div style={{ marginTop: 18, padding: 13, background: "rgba(255,107,0,0.05)", borderRadius: 11, border: "1px solid rgba(255,107,0,0.12)" }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: ORANGE, marginBottom: 9 }}>⚡ Architecture</div>
            {[
              ["Predictions", "POST /v1/predictions"],
              ["Players",     "GET  /v1/players"],
              ["Props",       "GET  /v1/props"],
              ["LLM calls",   "Backend only"],
              ["Mock data",   "None"],
            ].map(([k, v]) => (
              <div key={k} style={{ marginBottom: 7 }}>
                <div style={{ fontSize: 8, color: "rgba(255,255,255,0.28)", fontFamily: "'DM Mono',monospace", letterSpacing: "0.08em" }}>{k}</div>
                <div style={{ fontSize: 9, color: "rgba(255,255,255,0.55)", fontFamily: "'DM Mono',monospace", marginTop: 1 }}>{v}</div>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}
