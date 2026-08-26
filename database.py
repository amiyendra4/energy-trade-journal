from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine

BASE_DIR = Path(__file__).resolve().parent
LOCAL_DB = BASE_DIR / "data" / "trade_journal.db"
metadata = MetaData()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _database_url() -> str:
    """Use Supabase/PostgreSQL when DATABASE_URL is set, else local SQLite."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        LOCAL_DB.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{LOCAL_DB.as_posix()}"

    # SQLAlchemy 2 + psycopg 3 driver. Supabase may give postgres:// or postgresql://.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _make_engine() -> Engine:
    url = _database_url()
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("sqlite:///"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Supabase transaction pooler does not support prepared statements.
        kwargs["connect_args"] = {"prepare_threshold": None}
        # Helps Streamlit Cloud recover cleanly from stale pooled connections.
        kwargs["pool_recycle"] = 300
    return create_engine(url, **kwargs)


ENGINE = _make_engine()

trades = Table(
    "trades",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("trader_name", String(120), nullable=False),
    Column("product", String(40), nullable=False),
    Column("structure", String(80), nullable=False),
    Column("contract_details", Text),
    Column("direction", String(10), nullable=False),
    Column("entry_date", String(20), nullable=False),
    Column("quantity", Float, nullable=False),
    Column("average_entry", Float, nullable=False),
    Column("expected_tick_move", Float),
    Column("target_price", Float),
    Column("stop_price", Float),
    Column("trade_status", String(10), nullable=False, default="LIVE"),
    Column("trade_idea_source", Text),
    Column("entry_idea", Text),
    Column("exit_idea", Text),
    Column("exit_price", Float),
    Column("exit_date", String(20)),
    Column("ticks_result", Float),
    Column("pnl", Float),
    Column("exit_reason", Text),
    Column("remarks", Text),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    CheckConstraint("direction IN ('Long','Short')", name="ck_trades_direction"),
    CheckConstraint("trade_status IN ('LIVE','CLOSED')", name="ck_trades_status"),
)

entry_fills = Table(
    "entry_fills",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("trade_id", Integer, ForeignKey("trades.id", ondelete="CASCADE"), nullable=False),
    Column("fill_date", String(20), nullable=False),
    Column("price", Float, nullable=False),
    Column("quantity", Float, nullable=False),
    Column("note", Text),
    Column("created_at", String(40), nullable=False),
)

exit_fills = Table(
    "exit_fills",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("trade_id", Integer, ForeignKey("trades.id", ondelete="CASCADE"), nullable=False),
    Column("fill_date", String(20), nullable=False),
    Column("price", Float, nullable=False),
    Column("quantity", Float, nullable=False),
    Column("note", Text),
    Column("created_at", String(40), nullable=False),
)

weekly_notes = Table(
    "weekly_notes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("year", Integer, nullable=False),
    Column("week", Integer, nullable=False),
    Column("notes", Text, nullable=False, default=""),
    Column("updated_at", String(40), nullable=False),
    UniqueConstraint("year", "week", name="uq_weekly_notes_year_week"),
)


def init_db() -> None:
    metadata.create_all(ENGINE)


def _rows(stmt) -> list[dict[str, Any]]:
    with ENGINE.connect() as conn:
        return [dict(row) for row in conn.execute(stmt).mappings().all()]


def get_database_backend() -> str:
    return "PostgreSQL / Supabase" if ENGINE.dialect.name == "postgresql" else "SQLite (local development)"


def get_trades(status: str | None = None) -> list[dict[str, Any]]:
    stmt = select(trades)
    if status:
        stmt = stmt.where(trades.c.trade_status == status)
    stmt = stmt.order_by(trades.c.entry_date.desc(), trades.c.id.desc())
    return _rows(stmt)


def get_trade(trade_id: int) -> dict[str, Any] | None:
    rows = _rows(select(trades).where(trades.c.id == trade_id))
    return rows[0] if rows else None


def get_entry_fills(trade_id: int) -> list[dict[str, Any]]:
    return _rows(
        select(entry_fills)
        .where(entry_fills.c.trade_id == trade_id)
        .order_by(entry_fills.c.fill_date, entry_fills.c.id)
    )


def get_exit_fills(trade_id: int) -> list[dict[str, Any]]:
    return _rows(
        select(exit_fills)
        .where(exit_fills.c.trade_id == trade_id)
        .order_by(exit_fills.c.fill_date, exit_fills.c.id)
    )


def _summary_from_fills(fills: list[dict[str, Any]]) -> tuple[float, float]:
    clean = [x for x in fills if float(x.get("quantity") or 0) > 0]
    total_qty = sum(float(x["quantity"]) for x in clean)
    if total_qty <= 0:
        raise ValueError("Total entry quantity must be greater than zero.")
    avg_entry = sum(float(x["price"]) * float(x["quantity"]) for x in clean) / total_qty
    return total_qty, avg_entry


def create_trade(data: dict[str, Any], fills: list[dict[str, Any]]) -> int:
    total_qty, avg_entry = _summary_from_fills(fills)
    now = _utc_now()
    payload = {
        "trader_name": data.get("trader_name"),
        "product": data.get("product"),
        "structure": data.get("structure"),
        "contract_details": data.get("contract_details"),
        "direction": data.get("direction"),
        "entry_date": data.get("entry_date"),
        "quantity": total_qty,
        "average_entry": avg_entry,
        "expected_tick_move": data.get("expected_tick_move"),
        "target_price": data.get("target_price"),
        "stop_price": data.get("stop_price"),
        "trade_status": "LIVE",
        "trade_idea_source": data.get("trade_idea_source"),
        "entry_idea": data.get("entry_idea"),
        "exit_idea": data.get("exit_idea"),
        "remarks": data.get("remarks"),
        "created_at": now,
        "updated_at": now,
    }
    with ENGINE.begin() as conn:
        result = conn.execute(insert(trades).values(**payload))
        trade_id = int(result.inserted_primary_key[0])
        conn.execute(
            insert(entry_fills),
            [
                {
                    "trade_id": trade_id,
                    "fill_date": x["fill_date"],
                    "price": float(x["price"]),
                    "quantity": float(x["quantity"]),
                    "note": x.get("note", ""),
                    "created_at": now,
                }
                for x in fills
                if float(x.get("quantity") or 0) > 0
            ],
        )
    return trade_id


def update_trade(trade_id: int, fields: dict[str, Any], fills: list[dict[str, Any]] | None = None) -> None:
    allowed = {
        "trader_name", "product", "structure", "contract_details", "direction", "entry_date",
        "expected_tick_move", "target_price", "stop_price", "trade_idea_source", "entry_idea",
        "exit_idea", "exit_price", "exit_date", "ticks_result", "pnl", "exit_reason", "remarks",
    }
    clean = {k: v for k, v in fields.items() if k in allowed}
    now = _utc_now()

    with ENGINE.begin() as conn:
        if fills is not None:
            total_qty, avg_entry = _summary_from_fills(fills)
            clean["quantity"] = total_qty
            clean["average_entry"] = avg_entry
            conn.execute(delete(entry_fills).where(entry_fills.c.trade_id == trade_id))
            conn.execute(
                insert(entry_fills),
                [
                    {
                        "trade_id": trade_id,
                        "fill_date": x["fill_date"],
                        "price": float(x["price"]),
                        "quantity": float(x["quantity"]),
                        "note": x.get("note", ""),
                        "created_at": now,
                    }
                    for x in fills
                    if float(x.get("quantity") or 0) > 0
                ],
            )

        if clean:
            clean["updated_at"] = now
            conn.execute(update(trades).where(trades.c.id == trade_id).values(**clean))

        trade = conn.execute(select(trades).where(trades.c.id == trade_id)).mappings().first()
        if trade and trade["trade_status"] == "CLOSED":
            existing_exit = conn.execute(
                select(exit_fills).where(exit_fills.c.trade_id == trade_id).order_by(exit_fills.c.id).limit(1)
            ).mappings().first()
            exit_date = clean.get("exit_date", trade["exit_date"])
            exit_price = clean.get("exit_price", trade["exit_price"])
            qty = clean.get("quantity", trade["quantity"])
            if exit_date is not None and exit_price is not None:
                if existing_exit:
                    conn.execute(
                        update(exit_fills)
                        .where(exit_fills.c.id == existing_exit["id"])
                        .values(fill_date=exit_date, price=exit_price, quantity=qty)
                    )
                else:
                    conn.execute(
                        insert(exit_fills).values(
                            trade_id=trade_id,
                            fill_date=exit_date,
                            price=exit_price,
                            quantity=qty,
                            note="Edited close",
                            created_at=now,
                        )
                    )


def update_live_trade(trade_id: int, fields: dict[str, Any]) -> None:
    trade = get_trade(trade_id)
    if trade and trade["trade_status"] == "LIVE":
        update_trade(trade_id, fields)


def close_trade(
    trade_id: int,
    exit_date: str,
    exit_price: float,
    exit_idea: str,
    exit_reason: str,
    ticks_result: float | None,
    pnl: float | None,
    note: str = "",
) -> None:
    trade = get_trade(trade_id)
    if not trade:
        raise ValueError("Trade not found.")
    if trade["trade_status"] != "LIVE":
        raise ValueError("Trade is already closed.")
    now = _utc_now()
    qty = float(trade["quantity"])
    with ENGINE.begin() as conn:
        conn.execute(
            update(trades)
            .where(trades.c.id == trade_id)
            .values(
                trade_status="CLOSED",
                exit_date=exit_date,
                exit_price=exit_price,
                exit_idea=exit_idea,
                exit_reason=exit_reason,
                ticks_result=ticks_result,
                pnl=pnl,
                updated_at=now,
            )
        )
        conn.execute(
            insert(exit_fills).values(
                trade_id=trade_id,
                fill_date=exit_date,
                price=exit_price,
                quantity=qty,
                note=note,
                created_at=now,
            )
        )


def delete_trade(trade_id: int) -> None:
    with ENGINE.begin() as conn:
        # Explicit deletes keep behavior consistent even if SQLite FK settings differ.
        conn.execute(delete(exit_fills).where(exit_fills.c.trade_id == trade_id))
        conn.execute(delete(entry_fills).where(entry_fills.c.trade_id == trade_id))
        conn.execute(delete(trades).where(trades.c.id == trade_id))


def get_weekly_note(year: int, week: int) -> str:
    rows = _rows(select(weekly_notes.c.notes).where(weekly_notes.c.year == year, weekly_notes.c.week == week))
    return rows[0]["notes"] if rows else ""


def save_weekly_note(year: int, week: int, notes: str) -> None:
    now = _utc_now()
    with ENGINE.begin() as conn:
        existing = conn.execute(
            select(weekly_notes.c.id).where(weekly_notes.c.year == year, weekly_notes.c.week == week)
        ).first()
        if existing:
            conn.execute(
                update(weekly_notes)
                .where(weekly_notes.c.year == year, weekly_notes.c.week == week)
                .values(notes=notes, updated_at=now)
            )
        else:
            conn.execute(insert(weekly_notes).values(year=year, week=week, notes=notes, updated_at=now))
