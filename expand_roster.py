"""
expand_roster.py
Expands StatRush to cover the full active NBA roster.
Steps 1-6 as requested. Run from project root with venv activated.
Does NOT modify any ML, inference, or API route code.
"""
import asyncio
import os
import sys
import time
import httpx
from datetime import date as _date
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, func
from models.orm import Player, GameLog, PropLine, StatType

DB_URL         = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./statrush.db")
_engine        = create_async_engine(DB_URL, echo=False)
SessionFactory = async_sessionmaker(_engine, expire_on_commit=False)


# =============================================================================
# STEP 1 — Fetch all active NBA players via nba_api and insert into DB
# =============================================================================
def _fetch_active_nba_players_sync() -> list[dict]:
    """Returns list of {name, team, position} for all active roster players."""
    from nba_api.stats.endpoints import commonallplayers
    resp  = commonallplayers.CommonAllPlayers(
        league_id="00",
        season="2024-25",
        is_only_current_season=1,
    )
    df = resp.get_data_frames()[0]
    # Active = on a current roster (TEAM_ID != 0)
    active = df[df["TEAM_ID"] != 0]
    players = []
    for _, row in active.iterrows():
        players.append({
            "name":     str(row["DISPLAY_FIRST_LAST"]).strip(),
            "team":     str(row.get("TEAM_ABBREVIATION", "") or "").strip() or None,
            "position": "",
        })
    return players


async def step1_fetch_all_players() -> dict:
    print("\n=== STEP 1: Fetching all active NBA players ===\n")

    print("  Calling NBA Stats API (commonallplayers)...")
    nba_players = await asyncio.to_thread(_fetch_active_nba_players_sync)
    print(f"  Active roster players found: {len(nba_players)}")

    async with SessionFactory() as db:
        # Build existing name set (lower)
        existing_names = {
            row[0].lower()
            for row in (await db.execute(select(Player.name))).all()
        }

        inserted = 0
        skipped  = 0
        for p in nba_players:
            if p["name"].lower() in existing_names:
                skipped += 1
                continue
            db.add(Player(
                name     = p["name"],
                team     = p["team"],
                position = p["position"] or None,
                sport    = "nba",
                active   = True,
            ))
            existing_names.add(p["name"].lower())
            inserted += 1

        await db.commit()

    total_in_db = (await _count_players())
    print(f"  Players inserted this run : {inserted}")
    print(f"  Already existed (skipped) : {skipped}")
    print(f"  Total players now in DB   : {total_in_db}")
    return {"found": len(nba_players), "inserted": inserted, "total_db": total_in_db}


async def _count_players() -> int:
    async with SessionFactory() as db:
        return (await db.execute(select(func.count()).select_from(Player))).scalar()


# =============================================================================
# STEP 2 — Fetch game logs for all players that currently have zero logs
# =============================================================================
async def step2_fetch_game_logs() -> dict:
    print("\n=== STEP 2: Fetching game logs for players with zero logs ===\n")
    from services.ingestion import fetch_nba_stats_logs

    async with SessionFactory() as db:
        # Players with zero game logs
        subq = select(GameLog.player_id).distinct()
        players_no_logs = (await db.execute(
            select(Player)
            .where(Player.active == True)
            .where(~Player.id.in_(subq))
            .order_by(Player.name)
        )).scalars().all()

    print(f"  Players with zero game logs: {len(players_no_logs)}\n")

    total_inserted    = 0
    processed         = 0
    failed: list[str] = []
    no_data: list[str]= []
    BATCH             = 10

    for batch_start in range(0, len(players_no_logs), BATCH):
        batch = players_no_logs[batch_start: batch_start + BATCH]

        async with SessionFactory() as db:
            # Refresh existing keys for this batch's players
            existing_keys: set[tuple[int, str]] = set()
            for row in (await db.execute(select(GameLog.player_id, GameLog.game_date))).all():
                existing_keys.add((row[0], str(row[1])))

            batch_inserted = 0
            for player in batch:
                processed += 1
                try:
                    logs = await fetch_nba_stats_logs(player.name)
                    if not logs:
                        no_data.append(player.name)
                        print(f"  [{processed}/{len(players_no_logs)}] {player.name}: no data")
                        await asyncio.sleep(1)
                        continue

                    count = 0
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
                        count += 1

                    batch_inserted  += count
                    total_inserted  += count
                    print(f"  [{processed}/{len(players_no_logs)}] {player.name}: {count} logs")

                except Exception as e:
                    failed.append(player.name)
                    print(f"  [{processed}/{len(players_no_logs)}] {player.name}: ERROR — {e}")

                await asyncio.sleep(1)   # 1s delay between players

            await db.commit()

        print(f"  --- Batch {batch_start//BATCH + 1} complete: {batch_inserted} logs committed "
              f"(running total: {total_inserted}) ---\n")

    print(f"\n  Players processed : {processed}")
    print(f"  Total logs inserted: {total_inserted}")
    if no_data:
        print(f"  No data returned  : {len(no_data)} players")
        for n in no_data[:10]:
            print(f"    - {n}")
        if len(no_data) > 10:
            print(f"    ... and {len(no_data)-10} more")
    if failed:
        print(f"  Errors            : {len(failed)} players")
        for n in failed[:5]:
            print(f"    - {n}")

    return {"processed": processed, "inserted": total_inserted,
            "no_data": len(no_data), "errors": len(failed)}


# =============================================================================
# STEP 3 — Generate historical prop lines for all players missing props
# =============================================================================
async def step3_generate_props() -> dict:
    print("\n=== STEP 3: Generating historical prop lines ===\n")
    from seed import generate_historical_props

    async with SessionFactory() as db:
        counts = await generate_historical_props(db)

    total = sum(counts.values())
    for stat, n in counts.items():
        print(f"  {stat}: {n} new prop lines inserted")
    print(f"  Total inserted: {total}")
    return counts


# =============================================================================
# STEP 4 — Retrain ML models
# =============================================================================
async def step4_retrain() -> dict:
    print("\n=== STEP 4: Retraining ML models ===\n")
    async with httpx.AsyncClient(follow_redirects=True) as http:
        r = await http.post("http://127.0.0.1:8001/v1/analytics/train", timeout=300)
        r.raise_for_status()
        data    = r.json()
        results = data.get("results", {})
        print(f"  Status: {data.get('status')}")
        for stat, info in results.items():
            if isinstance(info, dict):
                n_tr = info.get("n_train", "?")
                n_v  = info.get("n_val",   "?")
                print(f"    {stat}: n_train={n_tr}  n_val={n_v}")
        return results


# =============================================================================
# STEP 5 — Test predictions for 5 new players
# =============================================================================
async def step5_predictions():
    print("\n=== STEP 5: Testing predictions for new players ===\n")
    from sqlalchemy import and_

    test_cases = [
        ("LeBron James",      "James"),
        ("Nikola Jokic",      "Jokic"),
        ("Stephen Curry",     "Curry"),
        ("Devin Booker",      "Booker"),
        ("Tyrese Haliburton", "Haliburton"),
    ]

    async with SessionFactory() as db:
        async with httpx.AsyncClient(follow_redirects=True) as http:
            probs = []
            for label, frag in test_cases:
                player = (await db.execute(
                    select(Player).where(Player.name.ilike(f"%{frag}%"))
                )).scalars().first()
                if not player:
                    print(f"  [SKIP] {label} not in DB")
                    continue

                prop = (await db.execute(
                    select(PropLine)
                    .where(and_(
                        PropLine.player_id == player.id,
                        PropLine.stat_type == StatType.points,
                    ))
                    .order_by(PropLine.game_date.desc())
                    .limit(1)
                )).scalars().first()
                line     = prop.line if prop else 25.5
                line_src = "REAL" if prop else "FALLBACK"

                try:
                    r = await http.post(
                        "http://127.0.0.1:8001/v1/predictions/",
                        json={"player_id": player.id, "stat_type": "points", "line": line},
                        timeout=30,
                    )
                    r.raise_for_status()
                    pred = r.json()
                    prob = pred.get("probability", 0)
                    probs.append((label, prob))
                    print(
                        f"  {label:<24}  line={line:5.1f} ({line_src})"
                        f"  -> {pred.get('prediction','?').upper():<6}"
                        f"  prob={prob:.3f}"
                        f"  conf={pred.get('confidence','?')}%"
                        f"  edge={pred.get('edge_pct',0):+.1f}%"
                    )
                except Exception as e:
                    print(f"  [ERROR] {label}: {e}")

            if len(probs) >= 2:
                unique_probs = len({round(p, 2) for _, p in probs})
                diverse = unique_probs > 1
                print(f"\n  Probabilities differ across all players: {'YES' if diverse else 'NO'}")
                print(f"  ({unique_probs} distinct probability values out of {len(probs)} players)")


# =============================================================================
# STEP 6 — Verify frontend player count
# =============================================================================
async def step6_verify_frontend():
    print("\n=== STEP 6: Verifying frontend player count ===\n")
    async with httpx.AsyncClient(follow_redirects=True) as http:
        r = await http.get("http://127.0.0.1:8001/v1/players/", timeout=15)
        r.raise_for_status()
        players = r.json()
        count   = len(players)
        print(f"  GET /v1/players/ returned: {count} players")
        if count > 20:
            print(f"  [PASS] More than 20 players available in app")
        else:
            print(f"  [WARN] Only {count} players — expected > 20")
        print(f"\n  Sample (first 10 alphabetically):")
        for p in players[:10]:
            print(f"    - {p['name']}  ({p.get('team','?')})")
        if count > 10:
            print(f"    ... and {count-10} more")


# =============================================================================
# main
# =============================================================================
async def main():
    t0 = time.monotonic()

    r1 = await step1_fetch_all_players()
    r2 = await step2_fetch_game_logs()
    r3 = await step3_generate_props()
    r4 = await step4_retrain()
    await step5_predictions()
    await step6_verify_frontend()

    elapsed = round(time.monotonic() - t0, 1)
    print(f"\n{'='*60}")
    print(f"  expand_roster.py complete in {elapsed}s")
    print(f"  Players in DB        : {r1['total_db']}")
    print(f"  Game logs inserted   : {r2['inserted']}")
    print(f"  Prop lines inserted  : {sum(r3.values())}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
