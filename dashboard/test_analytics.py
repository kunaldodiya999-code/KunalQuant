from types import SimpleNamespace

from dashboard.analytics import build_trade_dataframe
import pandas as pd

from dashboard.analytics import exit_summary, key_metrics, monthly_summary


def sample_df():
    return pd.DataFrame(
        [
            {"Date": "2025-01-02", "Status": "CLOSED", "Net P&L": 100.0, "Gross P&L": 120.0, "Costs": 20.0, "Exit Reason": "TARGET", "Holding (min)": 10.0},
            {"Date": "2025-01-03", "Status": "CLOSED", "Net P&L": -60.0, "Gross P&L": -40.0, "Costs": 20.0, "Exit Reason": "STOP_LOSS", "Holding (min)": 20.0},
            {"Date": "2025-02-04", "Status": "CLOSED", "Net P&L": 40.0, "Gross P&L": 60.0, "Costs": 20.0, "Exit Reason": "TARGET", "Holding (min)": 30.0},
            {"Date": "2025-02-05", "Status": "INVALID_STOP", "Net P&L": None, "Gross P&L": None, "Costs": None, "Exit Reason": "NO_EXIT", "Holding (min)": None},
        ]
    )


def test_monthly_summary_excludes_rejected_trades():
    summary = monthly_summary(sample_df())
    assert list(summary["Month"]) == ["2025-01", "2025-02"]
    assert list(summary["Trades"]) == [2, 1]
    assert list(summary["Net P&L"]) == [40.0, 40.0]


def test_exit_summary_groups_closed_trade_exit_reasons():
    summary = exit_summary(sample_df()).set_index("Exit Reason")
    assert int(summary.loc["TARGET", "Trades"]) == 2
    assert float(summary.loc["TARGET", "Net P&L"]) == 140.0
    assert int(summary.loc["STOP_LOSS", "Trades"]) == 1


def test_key_metrics_calculates_profit_factor_expectancy_and_streaks():
    metrics = key_metrics(sample_df())
    assert round(metrics["profit_factor"], 6) == round(140.0 / 60.0, 6)
    assert metrics["expectancy"] == 80.0 / 3.0
    assert metrics["avg_winner"] == 70.0
    assert metrics["avg_loser"] == -60.0
    assert metrics["best_trade"] == 100.0
    assert metrics["worst_trade"] == -60.0
    assert metrics["avg_holding_minutes"] == 20.0
    assert metrics["max_win_streak"] == 1.0
    assert metrics["max_loss_streak"] == 1.0


def test_build_trade_dataframe_includes_risk_holding_and_exit_reason():
    trade = SimpleNamespace(
        event=SimpleNamespace(
            trigger_timestamp=1735810200,
            direction="LONG",
        ),
        contract=SimpleNamespace(symbol="NSE:NIFTYTESTCE"),
        signal_underlying_price=100.0,
        option_signal_price=50.0,
        quantity=75,
        lots=1,
        entry=SimpleNamespace(filled=True, timestamp=1735810260, price=51.0, reason="FILLED"),
        exit=SimpleNamespace(filled=True, timestamp=1735810860, price=71.0, reason="TARGET"),
        stop_price=31.0,
        target_price=91.0,
        final_stop_price=31.0,
        gross_pnl=1500.0,
        status="CLOSED",
    )
    result = SimpleNamespace(trades=(trade,))
    df = build_trade_dataframe(result, intended_risk=2000.0)

    row = df.iloc[0]
    assert row["Exit Reason"] == "TARGET"
    assert row["Strategy Risk"] == 1500.0
    assert row["Intended Risk"] == 2000.0
    assert row["Realized R"] == 1.0
    assert row["Holding (min)"] == 10.0
