"""
FIX 3 — SportsRadar integration with structured mock fallback.
If SPORTRADAR_KEY is empty, the mock layer returns realistic structured
data so development works without a paid API key.
The mock layer mirrors the exact same schema as the real API response,
ensuring zero code changes needed when switching to production.
"""
import httpx, logging
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.orm import Player, GameLog, PropLine, StatType
from core.config import get_settings

cfg = get_settings()
log = logging.getLogger("statrush.ingestion")


# ── Mock data (matches SportsRadar schema exactly) ────────────────────
MOCK_PLAYERS = [
    {"external_id": "sr:player:001", "full_name": "Luka Dončić",            "team": "DAL", "position": "PG"},
    {"external_id": "sr:player:002", "full_name": "Jayson Tatum",            "team": "BOS", "position": "SF"},
    {"external_id": "sr:player:003", "full_name": "Shai Gilgeous-Alexander", "team": "OKC", "position": "PG"},
    {"external_id": "sr:player:004", "full_name": "Anthony Edwards",         "team": "MIN", "position": "SG"},
    {"external_id": "sr:player:005", "full_name": "Giannis Antetokounmpo",   "team": "MIL", "position": "PF"},
]

MOCK_GAME_LOGS = {
    "sr:player:001": [
        {"game_date":"2025-03-28","opponent":"LAL","home_away":"home","is_b2b":False,"rest_days":2,
         "minutes":36,"points":38,"assists":10,"rebounds":9,"three_pm":3,"usage_rate":37.2,
         "team_pace":101.4,"opp_pace":99.8,"opp_pts_allowed_rank":28,"fg_pct":0.51},
        {"game_date":"2025-03-25","opponent":"GSW","home_away":"away","is_b2b":False,"rest_days":3,
         "minutes":34,"points":29,"assists":8,"rebounds":7,"three_pm":2,"usage_rate":36.8,
         "team_pace":100.2,"opp_pace":104.1,"opp_pts_allowed_rank":18,"fg_pct":0.44},
        {"game_date":"2025-03-23","opponent":"PHX","home_away":"home","is_b2b":True,"rest_days":1,
         "minutes":32,"points":33,"assists":11,"rebounds":8,"three_pm":4,"usage_rate":38.1,
         "team_pace":102.0,"opp_pace":103.2,"opp_pts_allowed_rank":22,"fg_pct":0.48},
        {"game_date":"2025-03-21","opponent":"SAC","home_away":"away","is_b2b":False,"rest_days":2,
         "minutes":35,"points":41,"assists":9,"rebounds":10,"three_pm":5,"usage_rate":39.0,
         "team_pace":103.5,"opp_pace":106.0,"opp_pts_allowed_rank":25,"fg_pct":0.55},
        {"game_date":"2025-03-18","opponent":"DEN","home_away":"home","is_b2b":False,"rest_days":2,
         "minutes":37,"points":28,"assists":7,"rebounds":8,"three_pm":1,"usage_rate":35.5,
         "team_pace":99.8,"opp_pace":98.7,"opp_pts_allowed_rank":11,"fg_pct":0.42},
    ],
}

MOCK_PROP_LINES = {
    "sr:player:001": [
        {"stat_type":"points",  "line":32.5,"over_juice":-115,"open_line":32.0,"sportsbook":"DraftKings"},
        {"stat_type":"assists", "line":8.5, "over_juice":-110,"open_line":8.5, "sportsbook":"DraftKings"},
        {"stat_type":"rebounds","line":9.5, "over_juice":-108,"open_line":10.0,"sportsbook":"DraftKings"},
    ],
    "sr:player:002": [
        {"stat_type":"points",   "line":26.5,"over_juice":-112,"open_line":26.0,"sportsbook":"DraftKings"},
        {"stat_type":"assists",  "line":4.5, "over_juice":-110,"open_line":4.5, "sportsbook":"DraftKings"},
        {"stat_type":"rebounds", "line":7.5, "over_juice":-110,"open_line":7.5, "sportsbook":"DraftKings"},
        {"stat_type":"three_pm", "line":2.5, "over_juice":-118,"open_line":2.5, "sportsbook":"DraftKings"},
    ],
    "sr:player:003": [
        {"stat_type":"points",   "line":30.5,"over_juice":-110,"open_line":30.0,"sportsbook":"DraftKings"},
        {"stat_type":"assists",  "line":6.5, "over_juice":-115,"open_line":6.5, "sportsbook":"DraftKings"},
        {"stat_type":"rebounds", "line":5.0, "over_juice":-110,"open_line":5.0, "sportsbook":"DraftKings"},
        {"stat_type":"three_pm", "line":1.5, "over_juice":-110,"open_line":1.5, "sportsbook":"DraftKings"},
    ],
    "sr:player:004": [
        {"stat_type":"points",   "line":25.5,"over_juice":-105,"open_line":26.0,"sportsbook":"DraftKings"},
        {"stat_type":"assists",  "line":4.5, "over_juice":-110,"open_line":4.5, "sportsbook":"DraftKings"},
        {"stat_type":"rebounds", "line":5.5, "over_juice":-110,"open_line":5.5, "sportsbook":"DraftKings"},
        {"stat_type":"three_pm", "line":2.5, "over_juice":-110,"open_line":2.5, "sportsbook":"DraftKings"},
    ],
    "sr:player:005": [
        {"stat_type":"points",   "line":28.5,"over_juice":-110,"open_line":28.5,"sportsbook":"DraftKings"},
        {"stat_type":"assists",  "line":5.5, "over_juice":-110,"open_line":5.5, "sportsbook":"DraftKings"},
        {"stat_type":"rebounds", "line":11.5,"over_juice":-115,"open_line":11.0,"sportsbook":"DraftKings"},
        {"stat_type":"three_pm", "line":0.5, "over_juice":-110,"open_line":0.5, "sportsbook":"DraftKings"},
    ],
}


async def _sportradar_get(path: str) -> dict | None:
    """Call SportsRadar API. Returns None on failure."""
    url = f"{cfg.SPORTRADAR_BASE}/{path}?api_key={cfg.SPORTRADAR_KEY}"
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log.warning(f"SportsRadar call failed: {e}")
        return None


async def fetch_players_list() -> list[dict]:
    """FIX 3: Returns player list from SportsRadar or mock."""
    if cfg.SPORTRADAR_KEY:
        data = await _sportradar_get("league/hierarchy.json")
        if data:
            players = []
            for team in data.get("conferences", [{}])[0].get("divisions", [{}])[0].get("teams", []):
                for p in team.get("players", []):
                    players.append({
                        "external_id": p["id"],
                        "full_name":   p["full_name"],
                        "team":        team["alias"],
                        "position":    p.get("primary_position", ""),
                    })
            return players

    log.info("Using mock player data (no SPORTRADAR_KEY set)")
    return MOCK_PLAYERS


async def fetch_game_logs(external_id: str) -> list[dict]:
    """Returns game logs from SportsRadar or mock."""
    if cfg.SPORTRADAR_KEY:
        data = await _sportradar_get(f"players/{external_id}/profile.json")
        if data:
            return _parse_sportradar_logs(data)

    return MOCK_GAME_LOGS.get(external_id, [])


async def fetch_prop_lines(external_id: str) -> list[dict]:
    """Returns today's prop lines. In prod: scrape from odds API."""
    return MOCK_PROP_LINES.get(external_id, [])


def _parse_sportradar_logs(data: dict) -> list[dict]:
    """Normalize SportsRadar player profile into our GameLog schema."""
    logs = []
    for season in data.get("seasons", [])[-1:]:
        for game in season.get("totals", {}).get("statistics", []):
            logs.append({
                "game_date":            game.get("date", ""),
                "opponent":             game.get("opponent", {}).get("alias", ""),
                "home_away":            game.get("home_away", "home"),
                "is_b2b":               False,
                "rest_days":            1,
                "minutes":              float(game.get("minutes", 0) or 0),
                "points":               float(game.get("points", 0) or 0),
                "assists":              float(game.get("assists", 0) or 0),
                "rebounds":             float(game.get("rebounds", 0) or 0),
                "three_pm":             float(game.get("three_points_made", 0) or 0),
                "usage_rate":           float(game.get("usage_rate", 25) or 25),
                "team_pace":            float(game.get("pace", 100) or 100),
                "opp_pace":             float(game.get("opp_pace", 100) or 100),
                "opp_pts_allowed_rank": int(game.get("opp_def_rank", 15) or 15),
                "fg_pct":               float(game.get("field_goals_pct", 0.45) or 0.45),
            })
    return logs


def _map_balldontlie_logs(data: list) -> list[dict]:
    """Convert BallDontLie /v1/stats response rows into our GameLog dict schema."""
    result = []
    for stat in data:
        game      = stat.get("game") or {}
        raw_date  = (game.get("date") or "")[:10]
        if not raw_date:
            continue
        team_id   = (stat.get("team") or {}).get("id")
        home      = game.get("home_team_id") == team_id
        opp       = (game.get("visitor_team_abbreviation") if home
                     else game.get("home_team_abbreviation"))
        min_str   = str(stat.get("min") or "0")
        try:
            mins = (float(min_str.split(":")[0]) + float(min_str.split(":")[1]) / 60
                    if ":" in min_str else float(min_str))
        except Exception:
            mins = 0.0
        if mins < 5:
            continue
        result.append({
            "game_date":            raw_date,
            "opponent":             opp,
            "home_away":            "home" if home else "away",
            "is_b2b":               False,
            "rest_days":            2,
            "minutes":              mins,
            "points":               float(stat.get("pts") or 0),
            "assists":              float(stat.get("ast") or 0),
            "rebounds":             float(stat.get("reb") or 0),
            "three_pm":             float(stat.get("fg3m") or 0),
            "usage_rate":           28.0,
            "team_pace":            100.0,
            "opp_pace":             100.0,
            "opp_pts_allowed_rank": 15,
        })
    return result


def _fetch_nba_stats_logs_sync(player_name: str) -> list | None:
    """Synchronous implementation using nba_api (handles Cloudflare headers internally)."""
    import time
    from datetime import datetime as _dt
    from nba_api.stats.static import players as nba_players
    from nba_api.stats.endpoints import playergamelog

    matches = nba_players.find_players_by_full_name(player_name)
    if not matches:
        log.warning(f"[nba_stats] Player not found: {player_name}")
        return None

    player_id = matches[0]["id"]
    time.sleep(1)  # be polite between requests

    gl  = playergamelog.PlayerGameLog(
        player_id        = player_id,
        season           = "2024-25",
        season_type_all_star = "Regular Season",
    )
    df  = gl.get_data_frames()[0]
    if df.empty:
        return None

    result = []
    for _, row in df.iterrows():
        date_str = str(row["GAME_DATE"])
        try:
            game_date = _dt.strptime(date_str, "%b %d, %Y")
        except Exception:
            try:
                game_date = _dt.strptime(date_str, "%Y-%m-%d")
            except Exception:
                continue

        matchup   = str(row["MATCHUP"])
        home_away = "home" if "vs." in matchup else "away"
        opponent  = matchup.split(" ")[-1]

        min_str = str(row["MIN"] or "0")
        try:
            minutes = float(min_str.split(":")[0]) if ":" in min_str else float(min_str)
        except Exception:
            minutes = 0.0

        result.append({
            "game_date":            game_date,
            "opponent":             opponent,
            "home_away":            home_away,
            "is_b2b":               False,
            "rest_days":            2,
            "minutes":              minutes,
            "points":               float(row["PTS"]    or 0),
            "assists":              float(row["AST"]    or 0),
            "rebounds":             float(row["REB"]    or 0),
            "three_pm":             float(row["FG3M"]   or 0),
            "usage_rate":           28.0,
            "team_pace":            100.0,
            "opp_pace":             100.0,
            "opp_pts_allowed_rank": 15,
            "fg_pct":               float(row["FG_PCT"] or 0),
        })

    log.info(f"[nba_stats] Fetched {len(result)} game logs for {player_name}")
    return result if result else None


async def fetch_nba_stats_logs(player_name: str) -> list | None:
    """Async wrapper — runs the sync nba_api call in a thread pool."""
    import asyncio as _aio
    try:
        return await _aio.to_thread(_fetch_nba_stats_logs_sync, player_name)
    except Exception as e:
        log.warning(f"[nba_stats] Failed for {player_name}: {e}")
        return None


async def fetch_live_game_logs(external_id: str, player_name: str = None) -> list | None:
    # Try BallDontLie first
    if cfg.BALLDONTLIE_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    "https://api.balldontlie.io/v1/stats",
                    headers={"Authorization": cfg.BALLDONTLIE_API_KEY},
                    params={"player_ids[]": external_id, "seasons[]": 2024, "per_page": 100}
                )
                if r.status_code == 200:
                    data = r.json()
                    if data.get("data"):
                        log.info(f"[ingestion] BallDontLie game logs fetched for {external_id}")
                        return _map_balldontlie_logs(data["data"])
        except Exception as e:
            log.warning(f"[ingestion] BallDontLie failed: {e}")

    # Fall back to NBA Stats API
    if player_name:
        log.info(f"[ingestion] Falling back to NBA Stats API for {player_name}")
        return await fetch_nba_stats_logs(player_name)

    return None


async def seed_live_data(db: AsyncSession) -> list[dict]:
    """
    Fetch and insert real game logs for all active NBA players in the DB.
    Returns a list of per-player result dicts: {name, inserted, source, error}.
    """
    from datetime import date as _date

    result_rows = await db.execute(select(Player).where(Player.active == True))
    players = result_rows.scalars().all()

    # Pre-load existing (player_id, game_date) to skip duplicates
    existing_keys: set[tuple[int, str]] = set()
    for row in (await db.execute(select(GameLog.player_id, GameLog.game_date))).all():
        existing_keys.add((row[0], str(row[1])))

    report: list[dict] = []
    for player in players:
        source = "none"
        try:
            # Determine source label before calling
            if cfg.BALLDONTLIE_API_KEY:
                source = "BallDontLie→NBA Stats (fallback)"
            else:
                source = "NBA Stats API"

            logs = await fetch_live_game_logs(None, player_name=player.name)
            if not logs:
                report.append({"name": player.name, "inserted": 0, "source": source, "error": "no data returned"})
                continue

            # Detect actual source from log content (NBA Stats returns datetime objects)
            first_gd = logs[0].get("game_date")
            if hasattr(first_gd, "year"):
                source = "NBA Stats API"
            else:
                source = "BallDontLie"

            inserted = 0
            for lg in logs:
                gd = lg.get("game_date")
                if isinstance(gd, str):
                    try:
                        gd = _date.fromisoformat(gd)
                    except Exception:
                        continue
                elif hasattr(gd, "date"):
                    gd = gd.date()

                key = (player.id, str(gd))
                if key in existing_keys:
                    continue

                mins = float(lg.get("minutes") or 0)
                if mins < 5:
                    continue

                db.add(GameLog(
                    player_id            = player.id,
                    game_date            = gd,
                    opponent             = lg.get("opponent"),
                    home                 = (lg.get("home_away", "home") == "home"),
                    minutes              = mins,
                    points               = lg.get("points"),
                    assists              = lg.get("assists"),
                    rebounds             = lg.get("rebounds"),
                    three_pm             = lg.get("three_pm"),
                    usage_rate           = lg.get("usage_rate"),
                    team_pace            = lg.get("team_pace"),
                    opp_pace             = lg.get("opp_pace"),
                    opp_pts_allowed_rank = lg.get("opp_pts_allowed_rank"),
                ))
                existing_keys.add(key)
                inserted += 1

            await db.commit()
            log.info(f"[seed_live_data] {player.name}: {inserted} logs from {source}")
            report.append({"name": player.name, "inserted": inserted, "source": source, "error": None})

        except Exception as e:
            log.error(f"[seed_live_data] {player.name} failed: {e}", exc_info=True)
            report.append({"name": player.name, "inserted": 0, "source": source, "error": str(e)})

    return report


async def ingest_player(external_id: str, db: AsyncSession):
    """Upsert player + game logs into DB."""
    player_data = next((p for p in MOCK_PLAYERS if p["external_id"] == external_id), None)
    if not player_data and cfg.SPORTRADAR_KEY:
        raw = await _sportradar_get(f"players/{external_id}/profile.json")
        if raw:
            player_data = {
                "external_id": external_id,
                "full_name":   raw.get("full_name", "Unknown"),
                "team":        raw.get("team", {}).get("alias", ""),
                "position":    raw.get("primary_position", ""),
            }

    if not player_data:
        log.warning(f"No player data for {external_id}")
        return

    result = await db.execute(select(Player).where(Player.external_id == external_id))
    player = result.scalar_one_or_none()
    if not player:
        player = Player(**player_data)
        db.add(player)
        await db.flush()
    else:
        player.team     = player_data["team"]
        player.position = player_data["position"]

    logs = await fetch_game_logs(external_id)
    for log_data in logs:
        game_date = datetime.strptime(log_data["game_date"], "%Y-%m-%d") if isinstance(log_data["game_date"], str) else log_data["game_date"]
        exists = await db.execute(
            select(GameLog).where(GameLog.player_id == player.id, GameLog.game_date == game_date)
        )
        if exists.scalar_one_or_none():
            continue
        gl = GameLog(player_id=player.id, game_date=game_date, **{
            k: v for k, v in log_data.items() if k not in ("game_date",)
        })
        db.add(gl)

    await db.commit()
    log.info(f"Ingested player {player.full_name} ({len(logs)} logs)")


async def ingest_batch(external_ids: list[str], db: AsyncSession):
    for eid in external_ids:
        try:
            await ingest_player(eid, db)
        except Exception as e:
            log.error(f"Ingest failed for {eid}: {e}", exc_info=True)
