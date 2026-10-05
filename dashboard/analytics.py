"""Pure dashboard analytics over an existing backtest result.

This module is display-only: it does not change strategy, execution, sizing,
resolver, lifecycle, or accounting behavior.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from backtest.broker_cost_model import calculate_options_trade_costs, fyers_options_profile

IST = ZoneInfo("Asia/Kolkata")


def _ts(value: int | None) -> datetime | None:
    return datetime.fromtimestamp(value, tz=IST) if value is not None else None


def build_trade_dataframe(result: Any, intended_risk: float) -> pd.DataFrame:
    """Flatten result trades into an analysis-ready display table."""
    rows: list[dict[str, Any]] = []

    for trade in result.trades:
        signal_dt = _ts(trade.event.trigger_timestamp)
        entry_dt = _ts(trade.entry.timestamp)
        exit_dt = _ts(trade.exit.timestamp)

        closed = trade.status == "CLOSED" and trade.entry.filled and trade.exit.filled
        costs = None
        net_pnl = None
        strategy_risk = None
        realized_r = None
        net_r = None
        entry_impact = None
        holding_minutes = None

        if closed:
            costs = calculate_options_trade_costs(
                entry_price=trade.entry.price,
                exit_price=trade.exit.price,
                quantity=trade.quantity,
                profile=fyers_options_profile(signal_dt.date()),
                gross_pnl=trade.gross_pnl,
            )
            net_pnl = trade.gross_pnl - costs.total_cost
            strategy_risk = (
                abs(trade.entry.price - trade.stop_price) * trade.quantity
                if trade.stop_price is not None
                else None
            )
            if strategy_risk and strategy_risk > 0:
                realized_r = trade.gross_pnl / strategy_risk
                net_r = net_pnl / strategy_risk
            entry_impact = (
                (trade.entry.price - trade.option_signal_price) * trade.quantity
                if trade.option_signal_price is not None
                else None
            )
            if entry_dt and exit_dt:
                holding_minutes = (exit_dt - entry_dt).total_seconds() / 60.0

        exit_reason = trade.exit.reason if trade.exit else None
        rows.append(
            {
                "Date": signal_dt.date().isoformat() if signal_dt else None,
                "Time": signal_dt.strftime("%H:%M:%S") if signal_dt else None,
                "Contract": trade.contract.symbol,
                "Direction": trade.event.direction,
                "Status": trade.status,
                "Entry": trade.entry.price if trade.entry else None,
                "Exit": trade.exit.price if trade.exit else None,
                "Qty": trade.quantity,
                "Lots": trade.lots,
                "Stop": trade.stop_price,
                "Target": trade.target_price,
                "Final Stop": trade.final_stop_price,
                "Gross P&L": trade.gross_pnl if closed else None,
                "Costs": costs.total_cost if costs else None,
                "Net P&L": net_pnl,
                "Exit Reason": exit_reason,
                "Holding (min)": holding_minutes,
                "Strategy Risk": strategy_risk,
                "Intended Risk": intended_risk if closed else None,
                "Realized R": realized_r,
                "Net R": net_r,
                "Entry Impact": entry_impact,
            }
        )

    return pd.DataFrame(rows)


def closed_trades(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    return df[df["Status"] == "CLOSED"].copy()


def monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    closed = closed_trades(df)
    if closed.empty:
        return pd.DataFrame(
            columns=["Month", "Trades", "Wins", "Losses", "Win Rate %", "Gross P&L", "Costs", "Net P&L", "Avg Net/Trade"]
        )

    work = closed.copy()
    work["Month"] = pd.to_datetime(work["Date"]).dt.to_period("M").astype(str)
    summary = (
        work.groupby("Month", as_index=False)
        .agg(
            Trades=("Net P&L", "count"),
            Wins=("Net P&L", lambda s: int((s > 0).sum())),
            Losses=("Net P&L", lambda s: int((s < 0).sum())),
            **{"Gross P&L": ("Gross P&L", "sum"), "Costs": ("Costs", "sum"), "Net P&L": ("Net P&L", "sum")},
        )
        .sort_values("Month")
    )
    summary["Win Rate %"] = summary["Wins"] / summary["Trades"] * 100.0
    summary["Avg Net/Trade"] = summary["Net P&L"] / summary["Trades"]
    return summary[
        ["Month", "Trades", "Wins", "Losses", "Win Rate %", "Gross P&L", "Costs", "Net P&L", "Avg Net/Trade"]
    ]


def exit_summary(df: pd.DataFrame) -> pd.DataFrame:
    closed = closed_trades(df)
    if closed.empty:
        return pd.DataFrame(columns=["Exit Reason", "Trades", "Win Rate %", "Gross P&L", "Net P&L"])

    work = closed.copy()
    work["Exit Reason"] = work["Exit Reason"].fillna("UNKNOWN")
    summary = (
        work.groupby("Exit Reason", as_index=False)
        .agg(
            Trades=("Net P&L", "count"),
            **{"Gross P&L": ("Gross P&L", "sum"), "Net P&L": ("Net P&L", "sum")},
        )
    )
    wins = work.assign(_win=work["Net P&L"] > 0).groupby("Exit Reason")["_win"].sum()
    summary["Win Rate %"] = summary.apply(
        lambda row: float(wins.get(row["Exit Reason"], 0)) / row["Trades"] * 100.0,
        axis=1,
    )
    return summary[["Exit Reason", "Trades", "Win Rate %", "Gross P&L", "Net P&L"]]


def key_metrics(df: pd.DataFrame) -> dict[str, float]:
    closed = closed_trades(df)
    if closed.empty:
        return {
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "avg_winner": 0.0,
            "avg_loser": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "avg_holding_minutes": 0.0,
            "max_win_streak": 0.0,
            "max_loss_streak": 0.0,
        }

    net = closed["Net P&L"].astype(float)
    gross_wins = float(net[net > 0].sum())
    gross_losses = float(-net[net < 0].sum())
    profit_factor = gross_wins / gross_losses if gross_losses else float("inf")

    streak_win = streak_loss = max_win = max_loss = 0
    for value in net:
        if value > 0:
            streak_win += 1
            streak_loss = 0
        elif value < 0:
            streak_loss += 1
            streak_win = 0
        else:
            streak_win = streak_loss = 0
        max_win = max(max_win, streak_win)
        max_loss = max(max_loss, streak_loss)

    return {
        "profit_factor": profit_factor,
        "expectancy": float(net.mean()),
        "avg_winner": float(net[net > 0].mean()) if (net > 0).any() else 0.0,
        "avg_loser": float(net[net < 0].mean()) if (net < 0).any() else 0.0,
        "best_trade": float(net.max()),
        "worst_trade": float(net.min()),
        "avg_holding_minutes": float(closed["Holding (min)"].dropna().mean()) if closed["Holding (min)"].notna().any() else 0.0,
        "max_win_streak": float(max_win),
        "max_loss_streak": float(max_loss),
    }


__all__ = [
    "build_trade_dataframe",
    "closed_trades",
    "monthly_summary",
    "exit_summary",
    "key_metrics",
]
