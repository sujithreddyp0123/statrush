"""
Live data seeder for StatRush.
Fetches real NBA players, game logs, and prop lines from BallDontLie + The Odds API.
Run from the project root with the venv activated.
"""
import asyncio
import os
import sys
import httpx
from datetime import date
from dotenv import load_dotenv

load_dotenv()

BALLDONTLIE_API_KEY = os.getenv("BALLDONTLIE_API_KEY", "")
ODDS_API_KEY        = os.getenv("ODDS_API_KEY", "")
BDL_BASE            = "https://api.balldontlie.io/v1"
ODDS_BASE           = "https://api.the-odds-api.com/v4"
BDL_HEADERS         = {"Authorization": BALLDONTLIE_API_KEY}

TARGET_PLAYERS = [
    ("LeBron James",           "James"),
    ("Stephen Curry",          "Curry"),
    ("Kevin Durant",           "Durant"),
    ("Nikola Jokic",           "Jokic"),
    ("Joel Embiid",            "Embiid"),
    ("Jayson Tatum",           "Tatum"),
    ("Luka Doncic",            "Doncic"),
    ("Shai Gilgeous-Alexander","Gilgeous-Alexander"),
    ("Giannis Antetokounmpo",  "Antetokounmpo"),
    ("Anthony Edwards",        "Edwards"),
    ("Devin Booker",           "Booker"),
    ("Damian Lillard",         "Lillard"),
    ("Tyrese Haliburton",      "Haliburton"),
    ("Donovan Mitchell",       "Mitchell"),
    ("Anthony Davis",          "Davis"),
    ("Karl-Anthony Towns",     "Towns"),
    ("Bam Adebayo",            "Adebayo"),
    ("Jimmy Butler",           "Butler"),
    ("Kawhi Leonard",          "Leonard"),
    ("Paul George",            "George"),
]

# SQLAlchemy async (same DB as the server)
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, and_
from models.orm import Player, GameLog, PropLine, StatType

DB_URL         = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./statrush.db")
_engine        = create_async_engine(DB_URL, echo=False)
SessionFactory = async_sessionmaker(_engine, expire_on_commit=False)

STAT_MAP = {
    "player_points":   StatType.points,
    "player_assists":  StatType.assists,
    "player_rebounds": StatType.rebounds,
}


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
async def bdl_get(client: httpx.AsyncClient, path: str, params: dict,
                  retries: int = 5) -> dict | None:
    """GET a BallDontLie endpoint with retry/backoff on 429."""
    url = f"{BDL_BASE}{path}"
    for attempt in range(retries):
        try:
            r = await client.get(url, headers=BDL_HEADERS, params=params, timeout=20)
            if r.status_code == 429:
                wait = 2 ** attempt + 1   # 2, 3, 5, 9, 17 seconds
                print(f"    [429] rate-limited, waiting {wait}s ...")
                await asyncio.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait = 2 ** attempt + 1
                print(f"    [429] rate-limited, waiting {wait}s ...")
                await asyncio.sleep(wait)
                continue
            print(f"    [HTTP error] {e}")
            return None
        except Exception as e:
            print(f"    [error] {e}")
            return None
    print(f"    [FAIL] exhausted retries for {path}")
    return None


def normalize(name: str) -> str:
    return (
        name.lower()
        .replace("\u0107", "c").replace("\u010d", "c").replace("\u0161", "s")
        .replace(".", "").replace("-", " ").replace("'", "")
        .strip()
    )


def parse_minutes(min_str) -> float | None:
    if not min_str:
        return None
    try:
        s = str(min_str)
        if ":" in s:
            parts = s.split(":")
            return float(parts[0]) + float(parts[1]) / 60
        return float(s)
    except Exception:
        return None


# -----------------------------------------------------------------------------
# STEP 2 — fetch & insert players
# -----------------------------------------------------------------------------
async def search_player(client: httpx.AsyncClient, full_name: str, last_name: str) -> dict | None:
    """Search BDL for a player. Falls back to last-name search if full name returns nothing."""
    for search_term in [full_name, last_name]:
        resp = await bdl_get(client, "/players", {"search": search_term, "per_page": 10})
        await asyncio.sleep(1.2)   # stay under rate limit
        if resp is None:
            continue
        data = resp.get("data", [])
        if not data:
            continue
        # Try exact full-name match first
        norm_full = normalize(full_name)
        for p in data:
            api_full = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
            if normalize(api_full) == norm_full:
                return p
        # Partial match — last name present and first-name initial matches
        first_initial = full_name.split()[0][0].lower()
        for p in data:
            api_last  = p.get("last_name", "").lower()
            api_first = p.get("first_name", "")[:1].lower()
            if normalize(last_name) in api_last and api_first == first_initial:
                return p
        # Fallback: return first result if last name matches
        for p in data:
            if normalize(last_name) in normalize(p.get("last_name", "")):
                return p
    return None


async def seed_players(db: AsyncSession, client: httpx.AsyncClient) -> dict[str, int]:
    """
    Fetch 20 target players from BDL and upsert into Player table.
    Returns {bdl_id_str -> db_player_id}.
    """
    print("\n--- STEP 2: Fetching real NBA players from BallDontLie ---")
    bdl_to_db: dict[str, int] = {}
    inserted = 0
    skipped  = 0

    for full_name, last_name in TARGET_PLAYERS:
        bdl = await search_player(client, full_name, last_name)
        if bdl is None:
            print(f"  [SKIP] {full_name} — not found in BallDontLie")
            continue

        bdl_id    = str(bdl["id"])
        api_name  = f"{bdl.get('first_name', '')} {bdl.get('last_name', '')}".strip()
        team      = (bdl.get("team") or {}).get("abbreviation") or None
        pos       = bdl.get("position") or None

        # Check DB by canonical name
        result = await db.execute(
            select(Player).where(Player.name.ilike(f"%{last_name}%"))
        )
        existing_rows = result.scalars().all()
        existing = None
        for row in existing_rows:
            if normalize(last_name) in normalize(row.name):
                # Check first name initial too
                if row.name.split()[0][0].lower() == full_name.split()[0][0].lower():
                    existing = row
                    break

        if existing:
            print(f"  [EXIST] {existing.name} (db_id={existing.id})")
            bdl_to_db[bdl_id] = existing.id
            skipped += 1
        else:
            player = Player(name=api_name, team=team, position=pos, sport="nba", active=True)
            db.add(player)
            await db.flush()
            bdl_to_db[bdl_id] = player.id
            print(f"  [INSERT] {api_name}  team={team}  pos={pos}  db_id={player.id}")
            inserted += 1

    await db.commit()
    print(f"\n  Players inserted: {inserted}  |  already existed: {skipped}  |  "
          f"total mapped: {len(bdl_to_db)}")
    return bdl_to_db


# -----------------------------------------------------------------------------
# STEP 3 — fetch & insert game logs
# -----------------------------------------------------------------------------
async def seed_game_logs(
    db: AsyncSession,
    client: httpx.AsyncClient,
    bdl_to_db: dict[str, int],
) -> dict[str, int]:
    print("\n--- STEP 3: Fetching game logs from BallDontLie (2024 season) ---")
    if not bdl_to_db:
        print("  [SKIP] No players mapped — skipping game logs")
        return {}

    counts: dict[int, int] = {}
    bdl_ids = list(bdl_to_db.keys())

    # Pre-load existing (player_id, game_date) to skip duplicates
    existing_keys: set[tuple[int, str]] = set()
    for row in (await db.execute(select(GameLog.player_id, GameLog.game_date))).all():
        existing_keys.add((row[0], str(row[1])))

    all_stats: list[dict] = []
    BATCH = 5   # keep per-request player_ids small to avoid URL-length issues
    for i in range(0, len(bdl_ids), BATCH):
        batch = bdl_ids[i: i + BATCH]
        cursor = None
        pages  = 0
        while True:
            flat: list[tuple[str, str]] = [
                ("per_page", "100"),
                ("seasons[]", "2024"),
            ]
            for bid in batch:
                flat.append(("player_ids[]", bid))
            if cursor is not None:
                flat.append(("cursor", str(cursor)))

            try:
                r = await client.get(
                    f"{BDL_BASE}/stats",
                    headers=BDL_HEADERS,
                    params=flat,
                    timeout=30,
                )
                if r.status_code == 429:
                    print("    [429] stats rate-limit, waiting 5s ...")
                    await asyncio.sleep(5)
                    continue
                r.raise_for_status()
                resp = r.json()
            except Exception as e:
                print(f"    [WARN] stats fetch error: {e}")
                break

            rows = resp.get("data", [])
            all_stats.extend(rows)
            pages += 1
            nxt = resp.get("meta", {}).get("next_cursor")
            if not nxt or not rows:
                break
            cursor = nxt
            await asyncio.sleep(1.0)

    print(f"  Raw stat rows fetched: {len(all_stats)}")

    for stat in all_stats:
        bdl_pid = str((stat.get("player") or {}).get("id", ""))
        db_pid  = bdl_to_db.get(bdl_pid)
        if db_pid is None:
            continue

        game = stat.get("game") or {}
        raw_date = game.get("date", "")
        game_date_str = raw_date[:10] if raw_date else ""
        if not game_date_str:
            continue

        key = (db_pid, game_date_str)
        if key in existing_keys:
            continue

        mins = parse_minutes(stat.get("min"))
        if mins is not None and mins < 5:
            continue   # skip garbage-time appearances

        gd   = date.fromisoformat(game_date_str)
        home = game.get("home_team_id") == (stat.get("team") or {}).get("id")
        opp  = (
            game.get("visitor_team_abbreviation") if home
            else game.get("home_team_abbreviation")
        )

        db.add(GameLog(
            player_id = db_pid,
            game_date = gd,
            opponent  = opp,
            home      = home,
            minutes   = mins,
            points    = stat.get("pts"),
            assists   = stat.get("ast"),
            rebounds  = stat.get("reb"),
            three_pm  = stat.get("fg3m"),
            steals    = stat.get("stl"),
            blocks    = stat.get("blk"),
        ))
        existing_keys.add(key)
        counts[db_pid] = counts.get(db_pid, 0) + 1

    await db.commit()

    res = await db.execute(
        select(Player.id, Player.name).where(Player.id.in_(list(bdl_to_db.values())))
    )
    id_to_name = {row[0]: row[1] for row in res.all()}
    report: dict[str, int] = {}
    for db_pid, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        name = id_to_name.get(db_pid, str(db_pid))
        report[name] = cnt
        print(f"  {name}: {cnt} game logs inserted")
    total = sum(counts.values())
    print(f"\n  Total game logs inserted: {total}")
    return report


# -----------------------------------------------------------------------------
# STEP 4 — fetch & insert prop lines from The Odds API
# -----------------------------------------------------------------------------
async def seed_prop_lines(db: AsyncSession, client: httpx.AsyncClient) -> int:
    print("\n--- STEP 4: Fetching prop lines from The Odds API ---")

    res = await db.execute(select(Player).where(Player.active == True))
    players = res.scalars().all()
    name_map: dict[str, Player] = {normalize(p.name): p for p in players}

    try:
        r = await client.get(
            f"{ODDS_BASE}/sports/basketball_nba/events",
            params={"apiKey": ODDS_API_KEY},
            timeout=20,
        )
        r.raise_for_status()
        events = r.json()
    except Exception as e:
        print(f"  [ERROR] Could not fetch NBA events: {e}")
        return 0

    print(f"  Found {len(events)} upcoming NBA events")
    if not events:
        print("  [INFO] No upcoming games right now (off-season or no live events)")
        return 0

    today = date.today()
    total_inserted = 0

    existing_props: set[tuple[int, str, str]] = set()
    for row in (await db.execute(
        select(PropLine.player_id, PropLine.game_date, PropLine.stat_type)
    )).all():
        existing_props.add((row[0], str(row[1]), str(row[2])))

    for event in events[:20]:
        event_id      = event.get("id")
        raw_dt        = event.get("commence_time", "")
        try:
            game_date = date.fromisoformat(raw_dt[:10]) if raw_dt else today
        except ValueError:
            game_date = today

        try:
            r2 = await client.get(
                f"{ODDS_BASE}/sports/basketball_nba/events/{event_id}/odds",
                params={
                    "apiKey":     ODDS_API_KEY,
                    "markets":    "player_points,player_assists,player_rebounds",
                    "bookmakers": "draftkings",
                    "oddsFormat": "american",
                },
                timeout=20,
            )
            r2.raise_for_status()
            odds_data = r2.json()
        except Exception as e:
            print(f"  [WARN] Odds fetch failed for event {event_id}: {e}")
            await asyncio.sleep(0.5)
            continue

        for bm in odds_data.get("bookmakers", []):
            if bm.get("key") != "draftkings":
                continue
            for market in bm.get("markets", []):
                mkt_key   = market.get("key")
                stat_type = STAT_MAP.get(mkt_key)
                if stat_type is None:
                    continue

                # Aggregate outcomes by player name
                by_player: dict[str, dict] = {}
                for oc in market.get("outcomes", []):
                    pname = oc.get("description") or oc.get("name", "")
                    side  = oc.get("name", "")     # "Over" | "Under"
                    price = oc.get("price")
                    point = oc.get("point")
                    if not pname or point is None:
                        continue
                    pnorm = normalize(pname)
                    if pnorm not in by_player:
                        by_player[pnorm] = {"raw_name": pname, "line": point}
                    if side == "Over":
                        by_player[pnorm]["over_odds"] = price
                    elif side == "Under":
                        by_player[pnorm]["under_odds"] = price

                for pnorm, info in by_player.items():
                    player = name_map.get(pnorm)
                    if player is None:
                        # Try substring match
                        for key, p in name_map.items():
                            if pnorm in key or key in pnorm:
                                player = p
                                break
                    if player is None:
                        continue

                    prop_key = (player.id, str(game_date), str(stat_type.value))
                    if prop_key in existing_props:
                        continue

                    db.add(PropLine(
                        player_id  = player.id,
                        game_date  = game_date,
                        stat_type  = stat_type,
                        line       = float(info["line"]),
                        over_odds  = info.get("over_odds"),
                        under_odds = info.get("under_odds"),
                    ))
                    existing_props.add(prop_key)
                    total_inserted += 1
                    print(f"    PropLine: {info['raw_name']} | {mkt_key} {info['line']} "
                          f"O{info.get('over_odds')} / U{info.get('under_odds')}")

        await asyncio.sleep(0.4)

    await db.commit()
    print(f"\n  Total prop lines inserted: {total_inserted}")
    return total_inserted


# -----------------------------------------------------------------------------
# STEP 5 — trigger ML training
# -----------------------------------------------------------------------------
async def trigger_training(client: httpx.AsyncClient) -> dict:
    print("\n--- STEP 5: Triggering ML model retraining ---")
    try:
        r = await client.post(
            "http://127.0.0.1:8001/v1/analytics/train",
            timeout=120,
            follow_redirects=True,
        )
        r.raise_for_status()
        result = r.json()
        results = result.get("results", {})
        print(f"  Status: {result.get('status')}")
        for stat, info in results.items():
            if isinstance(info, dict):
                n_train = info.get("n_train", "?")
                n_val   = info.get("n_val", "?")
                print(f"    {stat}: n_train={n_train}  n_val={n_val}")
        return result
    except Exception as e:
        print(f"  [ERROR] Training failed: {e}")
        return {}


# -----------------------------------------------------------------------------
# STEP 6 — test predictions
# -----------------------------------------------------------------------------
async def test_predictions(client: httpx.AsyncClient, db: AsyncSession):
    print("\n--- STEP 6: Testing predictions ---")

    test_cases = [
        ("Luka",    "points"),
        ("Curry",   "points"),
        ("Jokic",   "points"),
    ]

    seen_probs = []
    for search_frag, stat in test_cases:
        res = await db.execute(
            select(Player).where(Player.name.ilike(f"%{search_frag}%"))
        )
        player = res.scalars().first()
        if player is None:
            print(f"  [SKIP] '{search_frag}' not found in DB")
            continue

        # Look for a real prop line first
        res2 = await db.execute(
            select(PropLine)
            .where(and_(
                PropLine.player_id == player.id,
                PropLine.stat_type == StatType.points,
            ))
            .order_by(PropLine.game_date.desc())
            .limit(1)
        )
        prop = res2.scalars().first()
        line = prop.line if prop else 25.5
        line_src = "REAL" if prop else "FALLBACK"

        try:
            r = await client.post(
                "http://127.0.0.1:8001/v1/predictions/",
                json={"player_id": player.id, "stat_type": stat, "line": line},
                timeout=30,
                follow_redirects=True,
            )
            r.raise_for_status()
            pred = r.json()
            prob = pred.get("probability", 0)
            seen_probs.append(prob)
            print(
                f"  {player.name:<30} line={line} ({line_src})"
                f"  -> {pred.get('prediction','?').upper():<6}"
                f"  prob={prob:.3f}"
                f"  edge={pred.get('edge_pct', 0):.1f}%"
            )
        except Exception as e:
            print(f"  [ERROR] {player.name}: {e}")

    if len(seen_probs) >= 2:
        diverse = len(set(round(p, 2) for p in seen_probs)) > 1
        print(f"\n  Probabilities differ across players: {'YES' if diverse else 'NO (all same!)'}")


# -----------------------------------------------------------------------------
# STEP 7 — verify frontend (via API)
# -----------------------------------------------------------------------------
async def test_frontend_data(client: httpx.AsyncClient, db: AsyncSession):
    print("\n--- STEP 7: Verifying data for frontend ---")
    try:
        r = await client.get("http://127.0.0.1:8001/v1/players", timeout=10)
        r.raise_for_status()
        data = r.json()
        players = data if isinstance(data, list) else data.get("players", data.get("data", []))
        print(f"  Players returned by API: {len(players)}")
        if len(players) > 5:
            print("  [PASS] More than 5 players in sidebar")
        else:
            print(f"  [WARN] Only {len(players)} players — frontend sidebar may be sparse")
        for p in players[:8]:
            name = p.get("name") if isinstance(p, dict) else str(p)
            print(f"    - {name}")
        if len(players) > 8:
            print(f"    ... and {len(players)-8} more")
    except Exception as e:
        print(f"  [ERROR] Could not fetch players: {e}")

    try:
        res = await db.execute(select(PropLine).limit(3))
        sample = res.scalars().all()
        if sample:
            print(f"\n  Sample prop lines in DB:")
            for pl in sample:
                pres = await db.execute(select(Player).where(Player.id == pl.player_id))
                pname = (pres.scalars().first() or Player(name="?")).name
                print(f"    {pname} | {pl.stat_type.value} {pl.line}  "
                      f"O{pl.over_odds} / U{pl.under_odds}  ({pl.game_date})")
    except Exception as e:
        print(f"  [ERROR] Prop line check: {e}")


# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------
async def main():
    if not BALLDONTLIE_API_KEY:
        print("[FATAL] BALLDONTLIE_API_KEY not set in .env")
        sys.exit(1)
    if not ODDS_API_KEY:
        print("[FATAL] ODDS_API_KEY not set in .env")
        sys.exit(1)

    print(f"BallDontLie key: {BALLDONTLIE_API_KEY[:8]}...")
    print(f"Odds API key:    {ODDS_API_KEY[:8]}...")

    # Quick connectivity test
    async with httpx.AsyncClient(follow_redirects=True) as http:
        print("\n-- API connectivity check --")
        try:
            r = await http.get(
                f"{BDL_BASE}/players",
                headers=BDL_HEADERS,
                params={"per_page": 1},
                timeout=10,
            )
            print(f"  BallDontLie /players: HTTP {r.status_code}  "
                  f"(data len={len(r.json().get('data', []))})")
        except Exception as e:
            print(f"  BallDontLie connectivity FAILED: {e}")

        try:
            r2 = await http.get(
                f"{ODDS_BASE}/sports/basketball_nba/events",
                params={"apiKey": ODDS_API_KEY},
                timeout=10,
            )
            print(f"  OddsAPI events: HTTP {r2.status_code}  "
                  f"(events={len(r2.json())})")
        except Exception as e:
            print(f"  OddsAPI connectivity FAILED: {e}")

    async with httpx.AsyncClient(follow_redirects=True) as http:
        async with SessionFactory() as db:
            bdl_to_db  = await seed_players(db, http)
            log_counts = await seed_game_logs(db, http, bdl_to_db)
            props_ins  = await seed_prop_lines(db, http)

        train_result = await trigger_training(http)

        async with SessionFactory() as db:
            await test_predictions(http, db)
            await test_frontend_data(http, db)

    print("\n=== Live seed complete ===")
    print(f"  Players seeded:    {len(bdl_to_db)}")
    print(f"  Game logs seeded:  {sum(log_counts.values()) if log_counts else 0}")
    print(f"  Prop lines seeded: {props_ins}")


if __name__ == "__main__":
    asyncio.run(main())
