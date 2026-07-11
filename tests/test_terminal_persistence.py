"""Persistent terminal sessions survive callers and remain controllable."""

from __future__ import annotations

from pathlib import Path
import asyncio


def _isolated_terminal(monkeypatch, tmp_path):
    import infrastructure.tools.builtin.terminal.background as background

    monkeypatch.setenv("TERMINAL_STATE_DB", str(tmp_path / "sessions.sqlite3"))
    monkeypatch.setenv("TERMINAL_FILESYSTEM_MODE", "host")
    log_dir = tmp_path / "logs"
    control_dir = tmp_path / "control"
    monkeypatch.setattr(background, "ensure_log_dir", lambda: _mkdir(log_dir))
    monkeypatch.setattr(background, "ensure_control_dir", lambda: _mkdir(control_dir))
    return background


def _mkdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_id(text: str) -> str:
    return next(line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("Session:"))


def test_detached_session_completes_after_launching_caller_returns(monkeypatch, tmp_path):
    background = _isolated_terminal(monkeypatch, tmp_path)
    started = background.run_background(
        "sleep 0.2; echo durable-output",
        tmp_path,
        user_id=7,
        conversation_id=11,
    )
    session_id = _session_id(started)

    result = background.wait_background_job(
        session_id,
        5,
        user_id=7,
        conversation_id=11,
    )

    assert "Status: completed" in result
    assert "durable-output" in result


def test_pty_session_accepts_input_from_a_new_controller(monkeypatch, tmp_path):
    background = _isolated_terminal(monkeypatch, tmp_path)
    started = background.run_background(
        "read line; echo received:$line",
        tmp_path,
        user_id=7,
        conversation_id=12,
        pty=True,
    )
    session_id = _session_id(started)

    accepted = background.write_background_job(
        session_id,
        "hello",
        submit=True,
        user_id=7,
        conversation_id=12,
    )
    result = background.wait_background_job(
        session_id,
        5,
        user_id=7,
        conversation_id=12,
    )

    assert "accepted" in accepted
    assert "received:hello" in result


def test_terminal_session_scope_blocks_other_users(monkeypatch, tmp_path):
    background = _isolated_terminal(monkeypatch, tmp_path)
    started = background.run_background(
        "sleep 5",
        tmp_path,
        user_id=7,
        conversation_id=13,
    )
    session_id = _session_id(started)
    try:
        assert "not found" in background.check_background_job(
            session_id,
            user_id=8,
            conversation_id=13,
        ).lower()
    finally:
        background.kill_background_job(session_id, user_id=7, conversation_id=13)
        background.wait_background_job(session_id, 5, user_id=7, conversation_id=13)


def test_active_sessions_are_projected_into_next_agent_turn(monkeypatch, tmp_path):
    background = _isolated_terminal(monkeypatch, tmp_path)
    started = background.run_background(
        "sleep 5",
        tmp_path,
        user_id=9,
        conversation_id=21,
    )
    session_id = _session_id(started)
    try:
        prompt = background.active_session_prompt(user_id=9, conversation_id=21)
        assert session_id in prompt
        assert "terminal_process" in prompt
        assert background.active_session_prompt(user_id=9, conversation_id=22) == ""
    finally:
        background.kill_background_job(session_id, user_id=9, conversation_id=21)
        background.wait_background_job(session_id, 5, user_id=9, conversation_id=21)


def test_completion_event_state_survives_claim_and_delivery(monkeypatch, tmp_path):
    background = _isolated_terminal(monkeypatch, tmp_path)
    from infrastructure.tools.builtin.terminal.store import (
        claim_completion_events,
        claim_ready_completion_events,
        get_session,
        mark_completion_delivered,
        save_completion_response,
    )

    started = background.run_background(
        "echo complete",
        tmp_path,
        user_id=10,
        chat_id=20,
        conversation_id=30,
        notify_on_exit=True,
    )
    session_id = _session_id(started)
    background.wait_background_job(session_id, 5, user_id=10, conversation_id=30)

    claimed = claim_completion_events()
    assert [row["session_id"] for row in claimed] == [session_id]
    assert get_session(session_id)["delivery_status"] == "processing"

    save_completion_response(session_id, "agent continued")
    assert [row["session_id"] for row in claim_ready_completion_events()] == [session_id]
    mark_completion_delivered(session_id)
    assert get_session(session_id)["delivery_status"] == "delivered"
    assert claim_completion_events() == []


def test_manual_poll_dismisses_automatic_completion(monkeypatch, tmp_path):
    background = _isolated_terminal(monkeypatch, tmp_path)
    from infrastructure.tools.builtin.terminal.store import claim_completion_events

    started = background.run_background(
        "echo complete",
        tmp_path,
        user_id=10,
        chat_id=20,
        conversation_id=31,
        notify_on_exit=True,
    )
    session_id = _session_id(started)
    background.wait_background_job(session_id, 5, user_id=10, conversation_id=31)
    background.acknowledge_background_completion(session_id)

    assert claim_completion_events() == []


def test_claimed_event_generates_once_then_delivers(monkeypatch, tmp_path):
    background = _isolated_terminal(monkeypatch, tmp_path)
    from infrastructure.tools.builtin.terminal.store import claim_completion_events, get_session
    import adapters.telegram.terminal_completion as completion

    started = background.run_background(
        "echo complete",
        tmp_path,
        user_id=10,
        chat_id=20,
        conversation_id=32,
        notify_on_exit=True,
    )
    session_id = _session_id(started)
    background.wait_background_job(session_id, 5, user_id=10, conversation_id=32)
    job = claim_completion_events()[0]
    generated_calls = []
    delivered = []
    persisted = []

    async def fake_generate(claimed):
        generated_calls.append(claimed["session_id"])
        return "continued result", {"messages": [], "total_prompt_tokens": 0, "total_completion_tokens": 0}

    async def fake_send(_bot, claimed, text):
        delivered.append((claimed["session_id"], text))

    monkeypatch.setattr(completion, "_generate_continuation", fake_generate)
    monkeypatch.setattr(completion, "_send_result", fake_send)
    monkeypatch.setattr(completion, "_record_usage", lambda *_args: None)
    monkeypatch.setattr(completion, "add_assistant_message", lambda sid, text: persisted.append((sid, text)))

    asyncio.run(completion._process_claimed(object(), job))

    assert generated_calls == [session_id]
    assert delivered == [(session_id, "continued result")]
    assert persisted == [(32, "continued result")]
    assert get_session(session_id)["delivery_status"] == "delivered"


def test_delivery_retry_reuses_saved_agent_response(monkeypatch, tmp_path):
    background = _isolated_terminal(monkeypatch, tmp_path)
    from infrastructure.tools.builtin.terminal.store import (
        claim_completion_events,
        claim_ready_completion_events,
        get_session,
    )
    import adapters.telegram.terminal_completion as completion

    started = background.run_background(
        "echo complete",
        tmp_path,
        user_id=10,
        chat_id=20,
        conversation_id=33,
        notify_on_exit=True,
    )
    session_id = _session_id(started)
    background.wait_background_job(session_id, 5, user_id=10, conversation_id=33)
    job = claim_completion_events()[0]
    generated_calls = []
    send_attempts = []

    async def fake_generate(claimed):
        generated_calls.append(claimed["session_id"])
        return "saved response", {}

    async def flaky_send(_bot, claimed, text):
        send_attempts.append((claimed["session_id"], text))
        if len(send_attempts) == 1:
            raise RuntimeError("temporary Telegram failure")

    monkeypatch.setattr(completion, "_generate_continuation", fake_generate)
    monkeypatch.setattr(completion, "_send_result", flaky_send)
    monkeypatch.setattr(completion, "_record_usage", lambda *_args: None)
    monkeypatch.setattr(completion, "add_assistant_message", lambda *_args: None)

    asyncio.run(completion._process_claimed(object(), job))
    assert get_session(session_id)["delivery_status"] == "ready"

    ready = claim_ready_completion_events()[0]
    asyncio.run(completion._deliver_ready(object(), ready))

    assert generated_calls == [session_id]
    assert send_attempts == [
        (session_id, "saved response"),
        (session_id, "saved response"),
    ]
    assert get_session(session_id)["delivery_status"] == "delivered"
