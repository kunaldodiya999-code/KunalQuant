from execution.opening_breakout_v2_execution import V2ExecutionPolicy
from research.opening_breakout_1m_v2 import V2Config
from dashboard.optimizer import apply_parameter, rank_sweep, sweep_values


def test_sweep_values_is_bounded_and_deterministic():
    assert sweep_values(10, 20, 5) == [10.0, 15.0, 20.0]


def test_apply_parameter_changes_only_selected_layer():
    config = V2Config(custom_sl_points=20.0)
    policy = V2ExecutionPolicy()
    changed_config, changed_policy = apply_parameter(
        config, policy, "custom_sl_points", 30.0
    )
    assert changed_config.custom_sl_points == 30.0
    assert config.custom_sl_points == 20.0
    assert changed_policy == policy


def test_apply_execution_parameter_preserves_config():
    config = V2Config()
    policy = V2ExecutionPolicy()
    changed_config, changed_policy = apply_parameter(
        config, policy, "exit_buffer_points", 3.0
    )
    assert changed_config == config
    assert changed_policy.exit_buffer_points == 3.0
    assert policy.exit_buffer_points == 2.0


def test_rank_sweep_max_dd_is_minimized():
    ranked = rank_sweep(
        [
            {"Value": 1, "Max DD": 100.0},
            {"Value": 2, "Max DD": 50.0},
        ],
        "Max DD",
    )
    assert ranked.iloc[0]["Value"] == 2
