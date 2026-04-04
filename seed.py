"""
Seed the database with mock players, prop lines, game logs, and actual outcomes.
Runs automatically on startup if the players table is empty.
"""
import logging
import random as _rng
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.orm import Player, PropLine, GameLog, StatType
from services.ingestion import MOCK_PLAYERS, MOCK_PROP_LINES

log = logging.getLogger("statrush.seed")

_STAT_MAP = {
    "points":   StatType.points,
    "assists":  StatType.assists,
    "rebounds": StatType.rebounds,
    "three_pm": StatType.three_pm,
    "steals":   StatType.steals,
    "blocks":   StatType.blocks,
}

# Full game log data for all 5 players (recent games, Mar 2025)
FULL_GAME_LOGS = {
    "sr:player:001": [
        {"game_date":"2025-03-28","opponent":"LAL","home_away":"home","is_b2b":False,"rest_days":2,"minutes":36,"points":38,"assists":10,"rebounds":9,"three_pm":3,"usage_rate":37.2,"team_pace":101.4,"opp_pace":99.8,"opp_pts_allowed_rank":28,"fg_pct":0.51},
        {"game_date":"2025-03-25","opponent":"GSW","home_away":"away","is_b2b":False,"rest_days":3,"minutes":34,"points":29,"assists":8,"rebounds":7,"three_pm":2,"usage_rate":36.8,"team_pace":100.2,"opp_pace":104.1,"opp_pts_allowed_rank":18,"fg_pct":0.44},
        {"game_date":"2025-03-23","opponent":"PHX","home_away":"home","is_b2b":True, "rest_days":1,"minutes":32,"points":33,"assists":11,"rebounds":8,"three_pm":4,"usage_rate":38.1,"team_pace":102.0,"opp_pace":103.2,"opp_pts_allowed_rank":22,"fg_pct":0.48},
        {"game_date":"2025-03-21","opponent":"SAC","home_away":"away","is_b2b":False,"rest_days":2,"minutes":35,"points":41,"assists":9, "rebounds":10,"three_pm":5,"usage_rate":39.0,"team_pace":103.5,"opp_pace":106.0,"opp_pts_allowed_rank":25,"fg_pct":0.55},
        {"game_date":"2025-03-18","opponent":"DEN","home_away":"home","is_b2b":False,"rest_days":2,"minutes":37,"points":28,"assists":7, "rebounds":8, "three_pm":1,"usage_rate":35.5,"team_pace":99.8,"opp_pace":98.7,"opp_pts_allowed_rank":11,"fg_pct":0.42},
        {"game_date":"2025-03-15","opponent":"MEM","home_away":"home","is_b2b":False,"rest_days":2,"minutes":36,"points":32,"assists":8, "rebounds":9, "three_pm":2,"usage_rate":36.1,"team_pace":101.0,"opp_pace":100.2,"opp_pts_allowed_rank":20,"fg_pct":0.46},
        {"game_date":"2025-03-12","opponent":"HOU","home_away":"away","is_b2b":False,"rest_days":3,"minutes":35,"points":36,"assists":12,"rebounds":7, "three_pm":3,"usage_rate":37.8,"team_pace":102.1,"opp_pace":103.0,"opp_pts_allowed_rank":16,"fg_pct":0.50},
        {"game_date":"2025-03-09","opponent":"NOP","home_away":"home","is_b2b":True, "rest_days":1,"minutes":33,"points":27,"assists":9, "rebounds":8, "three_pm":1,"usage_rate":35.2,"team_pace":100.5,"opp_pace":99.8,"opp_pts_allowed_rank":24,"fg_pct":0.41},
    ],
    "sr:player:002": [
        {"game_date":"2025-03-28","opponent":"MIA","home_away":"home","is_b2b":False,"rest_days":2,"minutes":35,"points":31,"assists":5,"rebounds":9, "three_pm":3,"usage_rate":30.8,"team_pace":99.5,"opp_pace":98.7,"opp_pts_allowed_rank":14,"fg_pct":0.47},
        {"game_date":"2025-03-25","opponent":"ORL","home_away":"away","is_b2b":False,"rest_days":3,"minutes":34,"points":24,"assists":4,"rebounds":7, "three_pm":2,"usage_rate":29.5,"team_pace":98.2,"opp_pace":97.5,"opp_pts_allowed_rank":8, "fg_pct":0.42},
        {"game_date":"2025-03-23","opponent":"CLE","home_away":"home","is_b2b":False,"rest_days":2,"minutes":36,"points":33,"assists":6,"rebounds":10,"three_pm":4,"usage_rate":32.1,"team_pace":100.1,"opp_pace":99.2,"opp_pts_allowed_rank":12,"fg_pct":0.51},
        {"game_date":"2025-03-21","opponent":"CHI","home_away":"home","is_b2b":False,"rest_days":2,"minutes":33,"points":27,"assists":5,"rebounds":8, "three_pm":2,"usage_rate":30.2,"team_pace":99.0,"opp_pace":98.5,"opp_pts_allowed_rank":22,"fg_pct":0.44},
        {"game_date":"2025-03-18","opponent":"DET","home_away":"away","is_b2b":False,"rest_days":2,"minutes":35,"points":29,"assists":4,"rebounds":9, "three_pm":3,"usage_rate":31.0,"team_pace":100.5,"opp_pace":101.2,"opp_pts_allowed_rank":27,"fg_pct":0.46},
        {"game_date":"2025-03-15","opponent":"NYK","home_away":"home","is_b2b":False,"rest_days":3,"minutes":36,"points":34,"assists":7,"rebounds":8, "three_pm":3,"usage_rate":32.5,"team_pace":101.2,"opp_pace":100.0,"opp_pts_allowed_rank":10,"fg_pct":0.50},
        {"game_date":"2025-03-12","opponent":"PHI","home_away":"away","is_b2b":True, "rest_days":1,"minutes":32,"points":22,"assists":3,"rebounds":7, "three_pm":1,"usage_rate":28.8,"team_pace":98.5,"opp_pace":97.8,"opp_pts_allowed_rank":18,"fg_pct":0.39},
        {"game_date":"2025-03-09","opponent":"ATL","home_away":"home","is_b2b":False,"rest_days":2,"minutes":34,"points":28,"assists":5,"rebounds":8, "three_pm":2,"usage_rate":30.5,"team_pace":99.8,"opp_pace":103.5,"opp_pts_allowed_rank":25,"fg_pct":0.45},
    ],
    "sr:player:003": [
        {"game_date":"2025-03-28","opponent":"PHX","home_away":"away","is_b2b":False,"rest_days":2,"minutes":34,"points":35,"assists":6,"rebounds":5,"three_pm":2,"usage_rate":33.8,"team_pace":100.5,"opp_pace":102.1,"opp_pts_allowed_rank":24,"fg_pct":0.52},
        {"game_date":"2025-03-25","opponent":"UTA","home_away":"home","is_b2b":False,"rest_days":3,"minutes":33,"points":29,"assists":7,"rebounds":4,"three_pm":1,"usage_rate":32.5,"team_pace":101.2,"opp_pace":103.5,"opp_pts_allowed_rank":29,"fg_pct":0.46},
        {"game_date":"2025-03-23","opponent":"POR","home_away":"home","is_b2b":False,"rest_days":2,"minutes":32,"points":38,"assists":5,"rebounds":6,"three_pm":3,"usage_rate":35.1,"team_pace":102.0,"opp_pace":104.2,"opp_pts_allowed_rank":28,"fg_pct":0.56},
        {"game_date":"2025-03-21","opponent":"SAC","home_away":"away","is_b2b":True, "rest_days":1,"minutes":31,"points":27,"assists":8,"rebounds":4,"three_pm":1,"usage_rate":31.8,"team_pace":99.8,"opp_pace":105.0,"opp_pts_allowed_rank":26,"fg_pct":0.43},
        {"game_date":"2025-03-18","opponent":"GSW","home_away":"home","is_b2b":False,"rest_days":2,"minutes":35,"points":33,"assists":6,"rebounds":5,"three_pm":2,"usage_rate":34.2,"team_pace":100.8,"opp_pace":103.8,"opp_pts_allowed_rank":20,"fg_pct":0.49},
        {"game_date":"2025-03-15","opponent":"LAL","home_away":"away","is_b2b":False,"rest_days":3,"minutes":34,"points":31,"assists":7,"rebounds":5,"three_pm":2,"usage_rate":33.0,"team_pace":101.5,"opp_pace":100.2,"opp_pts_allowed_rank":15,"fg_pct":0.47},
        {"game_date":"2025-03-12","opponent":"MEM","home_away":"home","is_b2b":False,"rest_days":2,"minutes":33,"points":36,"assists":5,"rebounds":6,"three_pm":3,"usage_rate":34.8,"team_pace":102.2,"opp_pace":101.5,"opp_pts_allowed_rank":22,"fg_pct":0.53},
        {"game_date":"2025-03-09","opponent":"NOP","home_away":"home","is_b2b":False,"rest_days":2,"minutes":34,"points":32,"assists":6,"rebounds":4,"three_pm":2,"usage_rate":33.5,"team_pace":100.0,"opp_pace":99.5,"opp_pts_allowed_rank":19,"fg_pct":0.48},
    ],
    "sr:player:004": [
        {"game_date":"2025-03-28","opponent":"DEN","home_away":"home","is_b2b":True, "rest_days":1,"minutes":34,"points":22,"assists":5,"rebounds":5,"three_pm":2,"usage_rate":29.5,"team_pace":100.2,"opp_pace":101.5,"opp_pts_allowed_rank":9, "fg_pct":0.40},
        {"game_date":"2025-03-25","opponent":"LAC","home_away":"away","is_b2b":False,"rest_days":2,"minutes":35,"points":28,"assists":4,"rebounds":6,"three_pm":3,"usage_rate":30.8,"team_pace":101.0,"opp_pace":100.5,"opp_pts_allowed_rank":13,"fg_pct":0.46},
        {"game_date":"2025-03-23","opponent":"PHX","home_away":"home","is_b2b":False,"rest_days":3,"minutes":36,"points":31,"assists":6,"rebounds":5,"three_pm":4,"usage_rate":32.1,"team_pace":102.5,"opp_pace":103.2,"opp_pts_allowed_rank":22,"fg_pct":0.50},
        {"game_date":"2025-03-21","opponent":"HOU","home_away":"away","is_b2b":False,"rest_days":2,"minutes":33,"points":24,"assists":5,"rebounds":4,"three_pm":2,"usage_rate":28.9,"team_pace":99.5,"opp_pace":100.8,"opp_pts_allowed_rank":16,"fg_pct":0.42},
        {"game_date":"2025-03-18","opponent":"OKC","home_away":"home","is_b2b":False,"rest_days":2,"minutes":35,"points":26,"assists":4,"rebounds":6,"three_pm":3,"usage_rate":30.2,"team_pace":100.8,"opp_pace":99.5,"opp_pts_allowed_rank":11,"fg_pct":0.44},
        {"game_date":"2025-03-15","opponent":"GSW","home_away":"away","is_b2b":False,"rest_days":3,"minutes":34,"points":29,"assists":5,"rebounds":5,"three_pm":3,"usage_rate":31.5,"team_pace":103.2,"opp_pace":104.5,"opp_pts_allowed_rank":19,"fg_pct":0.47},
        {"game_date":"2025-03-12","opponent":"SAC","home_away":"home","is_b2b":False,"rest_days":2,"minutes":36,"points":33,"assists":7,"rebounds":6,"three_pm":4,"usage_rate":33.0,"team_pace":104.0,"opp_pace":105.2,"opp_pts_allowed_rank":26,"fg_pct":0.52},
        {"game_date":"2025-03-09","opponent":"POR","home_away":"home","is_b2b":False,"rest_days":2,"minutes":33,"points":27,"assists":4,"rebounds":5,"three_pm":2,"usage_rate":29.8,"team_pace":101.5,"opp_pace":104.0,"opp_pts_allowed_rank":28,"fg_pct":0.45},
    ],
    "sr:player:005": [
        {"game_date":"2025-03-28","opponent":"CHI","home_away":"away","is_b2b":False,"rest_days":2,"minutes":33,"points":31,"assists":6,"rebounds":13,"three_pm":0,"usage_rate":33.2,"team_pace":100.8,"opp_pace":101.2,"opp_pts_allowed_rank":22,"fg_pct":0.58},
        {"game_date":"2025-03-25","opponent":"IND","home_away":"home","is_b2b":False,"rest_days":3,"minutes":32,"points":26,"assists":5,"rebounds":11,"three_pm":0,"usage_rate":31.5,"team_pace":102.5,"opp_pace":106.8,"opp_pts_allowed_rank":27,"fg_pct":0.52},
        {"game_date":"2025-03-23","opponent":"CLE","home_away":"away","is_b2b":False,"rest_days":2,"minutes":34,"points":34,"assists":7,"rebounds":14,"three_pm":0,"usage_rate":34.8,"team_pace":99.5,"opp_pace":98.2,"opp_pts_allowed_rank":7, "fg_pct":0.61},
        {"game_date":"2025-03-21","opponent":"NYK","home_away":"home","is_b2b":True, "rest_days":1,"minutes":31,"points":27,"assists":4,"rebounds":10,"three_pm":0,"usage_rate":30.8,"team_pace":100.2,"opp_pace":99.5,"opp_pts_allowed_rank":10,"fg_pct":0.54},
        {"game_date":"2025-03-18","opponent":"BKN","home_away":"home","is_b2b":False,"rest_days":2,"minutes":33,"points":35,"assists":6,"rebounds":13,"three_pm":0,"usage_rate":34.1,"team_pace":101.5,"opp_pace":103.8,"opp_pts_allowed_rank":25,"fg_pct":0.60},
        {"game_date":"2025-03-15","opponent":"PHI","home_away":"away","is_b2b":False,"rest_days":3,"minutes":32,"points":29,"assists":5,"rebounds":12,"three_pm":0,"usage_rate":32.5,"team_pace":100.0,"opp_pace":99.2,"opp_pts_allowed_rank":15,"fg_pct":0.55},
        {"game_date":"2025-03-12","opponent":"TOR","home_away":"home","is_b2b":False,"rest_days":2,"minutes":31,"points":32,"assists":7,"rebounds":12,"three_pm":0,"usage_rate":33.8,"team_pace":101.2,"opp_pace":104.5,"opp_pts_allowed_rank":23,"fg_pct":0.57},
        {"game_date":"2025-03-09","opponent":"WAS","home_away":"home","is_b2b":False,"rest_days":2,"minutes":30,"points":28,"assists":5,"rebounds":11,"three_pm":0,"usage_rate":31.2,"team_pace":100.5,"opp_pace":105.2,"opp_pts_allowed_rank":30,"fg_pct":0.53},
    ],
}

# actual_value for today's prop lines: (external_id, stat_type_str, line) -> actual_value
PROP_ACTUALS = {
    # points
    ("sr:player:001", "points",   32.5): 38.0,
    ("sr:player:002", "points",   26.5): 31.0,
    ("sr:player:003", "points",   30.5): 35.0,
    ("sr:player:004", "points",   25.5): 22.0,
    ("sr:player:005", "points",   28.5): 31.0,
    # assists
    ("sr:player:001", "assists",   8.5): 10.0,
    ("sr:player:002", "assists",   4.5):  5.0,
    ("sr:player:003", "assists",   6.5):  6.0,
    ("sr:player:004", "assists",   4.5):  5.0,
    ("sr:player:005", "assists",   5.5):  6.0,
    # rebounds
    ("sr:player:001", "rebounds",  9.5):  9.0,
    ("sr:player:002", "rebounds",  7.5):  9.0,
    ("sr:player:003", "rebounds",  5.0):  5.0,
    ("sr:player:004", "rebounds",  5.5):  5.0,
    ("sr:player:005", "rebounds", 11.5): 13.0,
    # three_pm
    ("sr:player:002", "three_pm",  2.5):  3.0,
    ("sr:player:003", "three_pm",  1.5):  2.0,
    ("sr:player:004", "three_pm",  2.5):  4.0,
    ("sr:player:005", "three_pm",  0.5):  0.0,
}


# ── Historical data: 25 prop records × 4 stats × 5 players ──────────────────

def _build_historical_data():
    """
    Generate ~65 game logs per player (Sep 30 2024 – Mar 5 2025) and
    25 labeled prop lines per player per stat type across the same window.
    All values are deterministic (fixed seeds).
    """
    rng = _rng.Random(42)

    # ~3 games/week schedule from Sep 30, 2024 through Mar 5, 2025
    game_dates = []
    d = date(2024, 9, 30)
    while d <= date(2025, 3, 5):
        game_dates.append(d)
        d += timedelta(days=rng.choice([2, 2, 2, 3, 3]))

    # One prop line per stat per player per date — 25 dates, every 5 days
    prop_dates = [date(2024, 10, 20) + timedelta(days=5 * i) for i in range(25)]

    _opps = [
        "LAL", "GSW", "PHX", "DEN", "MEM", "HOU", "NOP", "SAC", "LAC", "UTA",
        "POR", "CLE", "MIA", "BOS", "NYK", "CHI", "PHI", "ATL", "IND", "ORL",
    ]

    # (pts_avg, pts_std, ast_avg, ast_std, reb_avg, reb_std,
    #  tpm_avg, tpm_std, min_avg, usg_avg, pace_avg)
    _game_cfg = {
        "sr:player:001": (34.0, 5.0,  9.0, 2.0,  8.5, 2.0,  3.0, 1.2, 35.0, 37.0, 101.5),
        "sr:player:002": (27.0, 4.0,  5.0, 1.5,  8.5, 2.0,  2.5, 1.0, 35.0, 30.5,  99.5),
        "sr:player:003": (32.0, 4.0,  6.0, 1.5,  5.0, 1.5,  1.8, 0.8, 34.0, 33.5, 101.0),
        "sr:player:004": (27.0, 4.0,  5.0, 1.5,  5.5, 1.5,  2.8, 1.0, 34.0, 30.5, 101.0),
        "sr:player:005": (30.0, 4.0,  6.0, 2.0, 12.0, 2.0,  0.2, 0.4, 32.0, 33.0, 100.5),
    }

    # (line, actual_avg, actual_std, over_odds)
    _prop_cfg = {
        "sr:player:001": {
            "points":   (32.5, 34.0, 5.0,  -115),
            "assists":  ( 8.5,  9.0, 2.0,  -110),
            "rebounds": ( 9.5,  8.5, 2.0,  -108),
            "three_pm": ( 2.5,  3.0, 1.2,  -115),
        },
        "sr:player:002": {
            "points":   (26.5, 27.5, 4.0,  -112),
            "assists":  ( 4.5,  5.0, 1.5,  -110),
            "rebounds": ( 7.5,  8.5, 2.0,  -110),
            "three_pm": ( 2.5,  2.5, 1.0,  -118),
        },
        "sr:player:003": {
            "points":   (30.5, 32.0, 4.0,  -110),
            "assists":  ( 6.5,  6.0, 1.5,  -115),
            "rebounds": ( 5.0,  5.0, 1.5,  -110),
            "three_pm": ( 1.5,  1.8, 0.8,  -110),
        },
        "sr:player:004": {
            "points":   (25.5, 27.0, 4.0,  -105),
            "assists":  ( 4.5,  5.0, 1.5,  -110),
            "rebounds": ( 5.5,  5.5, 1.5,  -110),
            "three_pm": ( 2.5,  2.8, 1.0,  -110),
        },
        "sr:player:005": {
            "points":   (28.5, 30.0, 4.0,  -110),
            "assists":  ( 5.5,  6.0, 2.0,  -110),
            "rebounds": (11.5, 12.0, 2.0,  -115),
            "three_pm": ( 0.5,  0.2, 0.4,  -110),
        },
    }

    hist_logs = {}
    for ext_id, (pa, ps, aa, as_, ra, rs, ta, ts, mn, usg, pace) in _game_cfg.items():
        logs = []
        for gd in game_dates:
            home  = rng.choice([True, False])
            rest  = rng.choice([1, 2, 2, 2, 3, 3])
            logs.append({
                "game_date":            gd.isoformat(),
                "opponent":             rng.choice(_opps),
                "home_away":            "home" if home else "away",
                "is_b2b":               rest == 1,
                "rest_days":            rest,
                "minutes":              round(max(20.0, rng.gauss(mn, 2.0)), 1),
                "points":               max(0, round(rng.gauss(pa, ps))),
                "assists":              max(0, round(rng.gauss(aa, as_))),
                "rebounds":             max(0, round(rng.gauss(ra, rs))),
                "three_pm":             max(0, round(rng.gauss(ta, ts))),
                "usage_rate":           round(max(15.0, rng.gauss(usg, 1.5)), 1),
                "team_pace":            round(rng.gauss(pace, 1.5), 1),
                "opp_pace":             round(rng.gauss(100.5, 2.5), 1),
                "opp_pts_allowed_rank": rng.randint(1, 30),
            })
        hist_logs[ext_id] = logs

    hist_props = {}
    for ext_id, stat_cfgs in _prop_cfg.items():
        # Independent RNG per player so each player's actuals vary independently
        prop_rng = _rng.Random(int(ext_id[-3:]) * 7)
        props = []
        for stat_type, (line, avg, std, odds) in stat_cfgs.items():
            for pd in prop_dates:
                raw = prop_rng.gauss(avg, std)
                if stat_type == "three_pm":
                    actual = float(max(0, round(raw)))
                else:
                    actual = round(max(0.0, raw), 1)
                props.append({
                    "game_date":    pd.isoformat(),
                    "stat_type":    stat_type,
                    "line":         line,
                    "over_odds":    odds,
                    "actual_value": actual,
                })
        hist_props[ext_id] = props

    return hist_logs, hist_props


HIST_GAME_LOGS, HIST_PROPS = _build_historical_data()


async def seed_if_empty(db: AsyncSession):
    result = await db.execute(select(Player).limit(1))
    if result.scalar_one_or_none() is not None:
        return  # Already seeded

    log.info("Seeding database with mock players, prop lines, and game logs...")

    # ── Insert players ────────────────────────────────────────────────────────
    ext_id_to_player: dict[str, Player] = {}
    for p in MOCK_PLAYERS:
        player = Player(
            name=p["full_name"],
            team=p["team"],
            position=p["position"],
            sport="nba",
            active=True,
        )
        db.add(player)
        ext_id_to_player[p["external_id"]] = player

    await db.flush()

    # ── Insert today's prop lines (with actual_values from PROP_ACTUALS) ─────
    today = date.today()
    for ext_id, props in MOCK_PROP_LINES.items():
        player = ext_id_to_player.get(ext_id)
        if not player:
            continue
        for prop in props:
            stat_enum = _STAT_MAP.get(prop["stat_type"])
            if not stat_enum:
                continue
            actual = PROP_ACTUALS.get((ext_id, prop["stat_type"], prop["line"]))
            db.add(PropLine(
                player_id   = player.id,
                game_date   = today,
                stat_type   = stat_enum,
                line        = prop["line"],
                over_odds   = prop.get("over_juice"),
                under_odds  = None,
                actual_value= actual,
            ))

    # ── Insert historical prop lines (labeled training data) ─────────────────
    hist_props_count = 0
    for ext_id, props in HIST_PROPS.items():
        player = ext_id_to_player.get(ext_id)
        if not player:
            continue
        for p in props:
            stat_enum = _STAT_MAP.get(p["stat_type"])
            if not stat_enum:
                continue
            db.add(PropLine(
                player_id   = player.id,
                game_date   = date.fromisoformat(p["game_date"]),
                stat_type   = stat_enum,
                line        = p["line"],
                over_odds   = p["over_odds"],
                under_odds  = None,
                actual_value= p["actual_value"],
            ))
            hist_props_count += 1

    # ── Insert recent game logs (FULL_GAME_LOGS, Mar 2025) ───────────────────
    recent_logs_count = 0
    for ext_id, game_logs in FULL_GAME_LOGS.items():
        player = ext_id_to_player.get(ext_id)
        if not player:
            continue
        seen_dates: set = set()
        for g in game_logs:
            gdate = date.fromisoformat(g["game_date"])
            if gdate in seen_dates:
                continue
            seen_dates.add(gdate)
            db.add(GameLog(
                player_id            = player.id,
                game_date            = gdate,
                opponent             = g.get("opponent"),
                home                 = g.get("home_away") == "home",
                minutes              = g.get("minutes"),
                points               = g.get("points"),
                assists              = g.get("assists"),
                rebounds             = g.get("rebounds"),
                three_pm             = g.get("three_pm"),
                rest_days            = g.get("rest_days"),
                is_b2b               = g.get("is_b2b"),
                usage_rate           = g.get("usage_rate"),
                opp_pts_allowed_rank = g.get("opp_pts_allowed_rank"),
                team_pace            = g.get("team_pace"),
                opp_pace             = g.get("opp_pace"),
            ))
            recent_logs_count += 1

    # ── Insert historical game logs (Oct 2024 – Mar 2025) ────────────────────
    hist_logs_count = 0
    for ext_id, game_logs in HIST_GAME_LOGS.items():
        player = ext_id_to_player.get(ext_id)
        if not player:
            continue
        seen_hist: set = set()
        for g in game_logs:
            gdate = date.fromisoformat(g["game_date"])
            if gdate in seen_hist:
                continue
            seen_hist.add(gdate)
            db.add(GameLog(
                player_id            = player.id,
                game_date            = gdate,
                opponent             = g.get("opponent"),
                home                 = g.get("home_away") == "home",
                minutes              = g.get("minutes"),
                points               = g.get("points"),
                assists              = g.get("assists"),
                rebounds             = g.get("rebounds"),
                three_pm             = g.get("three_pm"),
                rest_days            = g.get("rest_days"),
                is_b2b               = g.get("is_b2b"),
                usage_rate           = g.get("usage_rate"),
                opp_pts_allowed_rank = g.get("opp_pts_allowed_rank"),
                team_pace            = g.get("team_pace"),
                opp_pace             = g.get("opp_pace"),
            ))
            hist_logs_count += 1

    await db.commit()
    total_logs = recent_logs_count + hist_logs_count
    log.info(
        f"Seeded {len(MOCK_PLAYERS)} players, {hist_props_count} historical props, "
        f"{total_logs} game logs ({hist_logs_count} historical + {recent_logs_count} recent)"
    )


def MOCK_PLAYERS_PROP_MAP(players):
    """Return {external_id: props} by reading MOCK_PROP_LINES."""
    from services.ingestion import MOCK_PROP_LINES
    return MOCK_PROP_LINES


async def generate_historical_props(db: AsyncSession) -> dict[str, int]:
    """
    For every active player that has real game logs, generate labeled PropLine
    records (actual_value set) so the ML models can train on real 2024-25 data.

    Strategy per game log:
      - line = rolling average of prior games for that stat ± uniform(-1.5, 1.5),
               rounded to nearest 0.5, minimum 0.5
      - actual_value = the real stat value from that game log
      - over_odds = under_odds = -110 (standard vig)

    Only creates records that do not already exist.
    Returns {stat_name: count_inserted}.
    """
    import random as _random
    from sqlalchemy import and_

    rng   = _random.Random(42)          # deterministic so reruns are idempotent
    # (stat_enum, stat_col, noise_range) — three_pm uses tighter ±0.5 noise
    # because it's a small integer stat (0–5 typical) so ±1.5 produces bad lines
    stats = [
        (StatType.points,   "points",   1.5),
        (StatType.assists,  "assists",  1.5),
        (StatType.rebounds, "rebounds", 1.5),
        (StatType.three_pm, "three_pm", 0.5),
    ]

    # Pre-load all existing (player_id, game_date, stat_type) keys
    existing: set[tuple[int, str, str]] = set()
    for row in (await db.execute(
        select(PropLine.player_id, PropLine.game_date, PropLine.stat_type)
    )).all():
        existing.add((row[0], str(row[1]), str(row[2])))

    counts: dict[str, int] = {col: 0 for _, col, _ in stats}

    players = (await db.execute(
        select(Player).where(Player.active == True)
    )).scalars().all()

    for player in players:
        # Fetch all game logs for this player in chronological order
        logs = (await db.execute(
            select(GameLog)
            .where(GameLog.player_id == player.id)
            .order_by(GameLog.game_date.asc())
        )).scalars().all()

        if not logs:
            continue

        for stat_enum, stat_col, noise_range in stats:
            history: list[float] = []   # rolling values seen so far

            for gl in logs:
                actual_raw = getattr(gl, stat_col, None)

                # Always track the actual value so rolling avg stays accurate
                actual = float(actual_raw) if actual_raw is not None else None

                key = (player.id, str(gl.game_date), str(stat_enum.value))
                already_exists = key in existing

                if not already_exists and actual is not None:
                    # Use last-5 rolling average for three_pm (more stable)
                    if history:
                        window   = history[-5:] if stat_col == "three_pm" else history
                        rolling_avg = sum(window) / len(window)
                    else:
                        # First game: anchor line to actual so it's plausible
                        rolling_avg = actual

                    noise    = rng.uniform(-noise_range, noise_range)
                    raw_line = rolling_avg + noise
                    line     = max(0.5, round(raw_line * 2) / 2)  # nearest 0.5

                    db.add(PropLine(
                        player_id    = player.id,
                        game_date    = gl.game_date,
                        stat_type    = stat_enum,
                        line         = line,
                        over_odds    = -110.0,
                        under_odds   = -110.0,
                        actual_value = actual,
                    ))
                    existing.add(key)
                    counts[stat_col] += 1

                if actual is not None:
                    history.append(actual)

        await db.commit()
        log.info(f"[generate_historical_props] {player.name}: props committed")

    log.info(f"[generate_historical_props] Total inserted: {counts}")
    return counts
