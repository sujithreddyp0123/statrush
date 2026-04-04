import enum
from datetime import date, datetime
from typing import Optional
from sqlalchemy import String, Integer, Float, Boolean, Date, DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base


class StatType(str, enum.Enum):
    points   = "points"
    assists  = "assists"
    rebounds = "rebounds"
    three_pm = "three_pm"
    steals   = "steals"
    blocks   = "blocks"


class Player(Base):
    __tablename__ = "players"
    id:         Mapped[int]           = mapped_column(Integer, primary_key=True)
    name:       Mapped[str]           = mapped_column(String(120))
    team:       Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    position:   Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    sport:      Mapped[str]           = mapped_column(String(20), default="nba")
    active:     Mapped[bool]          = mapped_column(Boolean, default=True)
    game_logs:  Mapped[list["GameLog"]]  = relationship(back_populates="player")
    prop_lines: Mapped[list["PropLine"]] = relationship(back_populates="player")


class GameLog(Base):
    __tablename__ = "game_logs"
    id:                  Mapped[int]            = mapped_column(Integer, primary_key=True)
    player_id:           Mapped[int]            = mapped_column(ForeignKey("players.id"))
    game_date:           Mapped[date]           = mapped_column(Date)
    opponent:            Mapped[Optional[str]]  = mapped_column(String(60), nullable=True)
    home:                Mapped[bool]           = mapped_column(Boolean, default=True)
    minutes:             Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    points:              Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    assists:             Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rebounds:            Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    three_pm:            Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    steals:              Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    blocks:              Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rest_days:           Mapped[Optional[int]]   = mapped_column(Integer, nullable=True)
    is_b2b:              Mapped[Optional[bool]]  = mapped_column(Boolean, nullable=True)
    usage_rate:          Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    opp_pts_allowed_rank: Mapped[Optional[int]]  = mapped_column(Integer, nullable=True)
    team_pace:           Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    opp_pace:            Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    player:              Mapped["Player"] = relationship(back_populates="game_logs")

    @property
    def home_away(self) -> str:
        return "home" if self.home else "away"


class PropLine(Base):
    __tablename__ = "prop_lines"
    id:           Mapped[int]             = mapped_column(Integer, primary_key=True)
    player_id:    Mapped[int]             = mapped_column(ForeignKey("players.id"))
    game_date:    Mapped[date]            = mapped_column(Date)
    stat_type:    Mapped[StatType]        = mapped_column(Enum(StatType))
    line:         Mapped[float]           = mapped_column(Float)
    over_odds:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    under_odds:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    player:       Mapped["Player"] = relationship(back_populates="prop_lines")


class Prediction(Base):
    __tablename__ = "predictions"
    id:            Mapped[int]            = mapped_column(Integer, primary_key=True)
    player_id:     Mapped[int]            = mapped_column(ForeignKey("players.id"))
    stat_type:     Mapped[StatType]       = mapped_column(Enum(StatType))
    line:          Mapped[float]          = mapped_column(Float)
    prediction:    Mapped[str]            = mapped_column(String(10))
    probability:   Mapped[float]          = mapped_column(Float)
    edge_pct:      Mapped[float]          = mapped_column(Float)
    model_version: Mapped[str]            = mapped_column(String(20))
    explanation:   Mapped[Optional[str]]  = mapped_column(String(2000), nullable=True)
    created_at:    Mapped[datetime]       = mapped_column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id:    Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
