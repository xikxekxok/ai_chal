"""Unit-тесты контролируемых переходов TikTok FSM."""

from __future__ import annotations

from pathlib import Path

import pytest
from task_state import (
    Stage,
    TaskStateStore,
    apply_fsm_event,
    can_transition,
)


@pytest.fixture
def store(tmp_path: Path) -> TaskStateStore:
    ts = TaskStateStore(tmp_path / "tiktok_shoot.json")
    ts.init_case("Тофик", "ролик: шар + погоня хозяина")
    return ts


def test_denied_skip_publish() -> None:
    ok, msg = can_transition(Stage.PITCH, Stage.PUBLISH)
    assert not ok
    assert "запрещён" in msg
    assert "welfare_check" in msg


def test_allowed_pitch_to_welfare() -> None:
    ok, msg = can_transition(Stage.PITCH, Stage.WELFARE_CHECK)
    assert ok
    assert msg == ""


def test_advance_without_stage_data(store: TaskStateStore) -> None:
    ok, detail = store.request_advance(None)
    assert not ok
    assert "не хватает" in detail


def test_complete_stage_with_data(store: TaskStateStore) -> None:
    store.update_step(
        stage_data={
            "story": "Тофик на шаре",
            "participants": "Тофик и Саша",
            "duration": "15 сек",
        }
    )
    ok, detail = store.request_advance(None)
    assert ok
    assert detail == "pitch → welfare_check"
    assert store.state is not None
    assert store.state.stage == Stage.WELFARE_CHECK
    assert store.state.stage_data == {}


def test_denied_explicit_target(store: TaskStateStore) -> None:
    ok, detail = store.request_advance(Stage.PUBLISH)
    assert not ok
    assert "запрещён" in detail


def test_complete_stage_denied_missing_fields(store: TaskStateStore) -> None:
    store.update_step(stage_data={"story": "шар + погоня"})
    fsm = {"event": "complete_stage"}
    applied = apply_fsm_event(store, fsm, "sasha")
    assert any("denied complete" in line for line in applied)
    assert store.state is not None
    assert store.state.stage == Stage.PITCH


def test_complete_stage_advances(store: TaskStateStore) -> None:
    store.update_step(
        stage_data={
            "story": "Тофик на шаре, погоня",
            "participants": "Тофик и Саша",
            "duration": "15 сек",
        }
    )
    fsm = {"event": "complete_stage"}
    applied = apply_fsm_event(store, fsm, "sasha")
    assert any(line.startswith("allowed pitch → welfare_check") for line in applied)
    assert store.state is not None
    assert store.state.stage == Stage.WELFARE_CHECK


def test_complete_stage_with_inline_data(store: TaskStateStore) -> None:
    fsm = {
        "event": "complete_stage",
        "stage_data": {
            "story": "Тофик на шаре",
            "participants": "Тофик и Саша",
            "duration": "15 сек",
        },
    }
    applied = apply_fsm_event(store, fsm, "sasha")
    assert any("stage_data +" in line for line in applied)
    assert any(line.startswith("allowed pitch → welfare_check") for line in applied)
    assert store.state is not None
    assert store.state.stage == Stage.WELFARE_CHECK


def test_update_step_then_complete(store: TaskStateStore) -> None:
    fsm_update = {
        "event": "update_step",
        "stage_data": {
            "story": "шар",
            "participants": "Тофик",
            "duration": "10 сек",
        },
    }
    applied = apply_fsm_event(store, fsm_update, "sasha")
    assert "update_step" in applied
    fsm_complete = {"event": "complete_stage"}
    applied2 = apply_fsm_event(store, fsm_complete, "sasha")
    assert any("allowed pitch → welfare_check" in line for line in applied2)
