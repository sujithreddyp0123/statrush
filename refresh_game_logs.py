"""
Steps 4-6: Fetch real game logs via NBA Stats API, retrain, test predictions.
Run from project root with venv activated.
"""
import asyncio
import os
import sys
import httpx
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, and_
from models.orm import Player, GameLog, PropLine, StatType

DB_URL         = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./statrush.db")
_engine        = create_async_engine(DB_URL, echo=False)
SessionFactory = async_sessionmaker(_engine, expire_on_commit=False)

TARGET = [
    "LeBron James", "Stephen Curry", "Kevin Durant", "Nikola Jokic",
    "Joel Embiid", "Devin Booker", "Damian Lillard", "Tyrese Haliburton",
    "Donovan Mitchell", "Anthony Davis", "Karl-Anthony Towns",
    "Bam Adebayo", "Jimmy Butler", "Kawhi Leonard",
]


# ── STEP 4: fetch & insert game logs ─────────────────────────────────────────
async def step4_fetch_logs():
    print("\n=== STEP 4: Fetching real game logs via NBA Stats API ===\n")
    from services.ingestion import fetch_nba_stats_logs, seed_live_data

    async with SessionFactory() as db:
        # Get existing log counts per player so we can diff after
        pre = {}
        for row in (await db.execute(
            select(GameLog.player_id, Player.name)
            .join(Player, Player.id == GameLog.player_id)
        )).all():
            pre[row[1]] = pre.get(row[1], 0) + 1

        # Only target the specified players
        from sqlalchemy import select as _sel
        result = await db.execute(
            _sel(Player).where(Player.active == True)
        )
        all_players = result.scalars().all()
        target_set  = {n.lower() for n in TARGET}
        players     = [p for p in all_players if p.name.lower() in target_set]

        print(f"  Target players found in DB: {len(players)}")

        # Pre-load existing keys
        existing_keys = set()
        for row in (await db.execute(select(GameLog.player_id, GameLog.game_date))).all():
            existing_keys.add((row[0], str(row[1])))

        from datetime import date as _date

        total_inserted = 0
        for player in players:
            print(f"\n  {player.name}:")
            try:
                logs = await fetch_nba_stats_logs(player.name)
                if not logs:
                    print(f"    [SKIP] No data returned from NBA Stats API")
                    continue

                source   = "NBA Stats API"
                inserted = 0
                for lg in logs:
                    gd = lg.get("game_date")
                    if hasattr(gd, "date"):
                        gd = gd.date()
                    elif isinstance(gd, str):
                        try:
                            gd = _date.fromisoformat(gd)
                        except Exception:
                            continue

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
                total_inserted += inserted
                print(f"    source  : {source}")
                print(f"    fetched : {len(logs)} game log rows from API")
                print(f"    inserted: {inserted} new rows (duplicates skipped)")

            except Exception as e:
                print(f"    [ERROR] {e}")

        print(f"\n  Total new game logs inserted: {total_inserted}")
        return total_inserted


# ── STEP 5: retrain ───────────────────────────────────────────────────────────
async def step5_retrain():
    print("\n=== STEP 5: Retraining ML models ===\n")
    async with httpx.AsyncClient(follow_redirects=True) as http:
        try:
            r = await http.post(
                "http://127.0.0.1:8001/v1/analytics/train",
                timeout=120,
            )
            r.raise_for_status()
            data    = r.json()
            results = data.get("results", {})
            print(f"  Status: {data.get('status')}")
            for stat, info in results.items():
                if isinstance(info, dict):
                    print(f"    {stat}: n_train={info.get('n_train')}  n_val={info.get('n_val')}")
        except Exception as e:
            print(f"  [ERROR] {e}")


# ── STEP 6: test predictions ──────────────────────────────────────────────────
async def step6_predictions():
    print("\n=== STEP 6: Testing predictions ===\n")
    test_players = [
        ("Stephen Curry",  "Curry",  "points"),
        ("LeBron James",   "James",  "points"),
        ("Nikola Jokic",   "Jokic",  "points"),
    ]

    async with SessionFactory() as db:
        async with httpx.AsyncClient(follow_redirects=True) as http:
            probs = []
            for full_name, frag, stat in test_players:
                result = await db.execute(
                    select(Player).where(Player.name.ilike(f"%{frag}%"))
                )
                player = result.scalars().first()
                if player is None:
                    print(f"  [SKIP] {full_name} not in DB")
                    continue

                # Find a prop line
                res2 = await db.execute(
                    select(PropLine)
                    .where(and_(
                        PropLine.player_id == player.id,
                        PropLine.stat_type == StatType.points,
                    ))
                    .order_by(PropLine.game_date.desc())
                    .limit(1)
                )
                prop     = res2.scalars().first()
                line     = prop.line if prop else 25.5
                line_src = "REAL" if prop else "FALLBACK"

                try:
                    r = await http.post(
                        "http://127.0.0.1:8001/v1/predictions/",
                        json={"player_id": player.id, "stat_type": stat, "line": line},
                        timeout=30,
                    )
                    r.raise_for_status()
                    pred = r.json()
                    prob = pred.get("probability", 0)
                    probs.append(prob)
                    print(
                        f"  {player.name:<28}  line={line} ({line_src})"
                        f"  -> {pred.get('prediction','?').upper():<6}"
                        f"  prob={prob:.3f}"
                        f"  conf={pred.get('confidence','?')}%"
                        f"  edge={pred.get('edge_pct', 0):+.1f}%"
                    )
                except Exception as e:
                    print(f"  [ERROR] {full_name}: {e}")

            if len(probs) >= 2:
                diverse = len({round(p, 2) for p in probs}) > 1
                print(f"\n  Probabilities differ across players: {'YES' if diverse else 'NO — all identical'}")
            else:
                print("\n  Not enough predictions to compare")


async def main():
    inserted = await step4_fetch_logs()
    await step5_retrain()
    await step6_predictions()
    print("\n=== Done ===")


if __name__ == "__main__":
    asyncio.run(main())
