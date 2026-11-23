"""Players and tick rate from console output, auto-restart policy and LAN address (M3-BE-04, M3-BE-05, M3-GUI-05)."""

from __future__ import annotations

import pytest

from mcserver.application.auto_restart import AutoRestartPolicy
from mcserver.application.ports import OutputStream, ServerOutputLine
from mcserver.application.server_activity import ServerActivity
from mcserver.application.server_address import ServerAddress, ServerAddressLookup
from mcserver.application.server_coordinator import FailureKind, ServerFailure
from mcserver.domain.diagnostics import diagnose
from mcserver.domain.server_activity import ActivityKind, parse_activity_line

_sequence = 0


def line(text: str, server_id: str = "survival", stream: OutputStream = OutputStream.STDOUT) -> ServerOutputLine:
    global _sequence
    _sequence += 1
    return ServerOutputLine(_sequence, server_id, stream, text)


@pytest.mark.parametrize(
    ("text", "kind", "value"),
    [
        ("[12:00:00] [Server thread/INFO]: Steve joined the game", ActivityKind.JOINED, "Steve"),
        ("[12:00:00 INFO]: Alex_2 left the game", ActivityKind.LEFT, "Alex_2"),
        ("[12:00:00 INFO]: .BedrockGuy joined the game", ActivityKind.JOINED, ".BedrockGuy"),
        ("\x1b[33m[12:00:00 INFO]: §eSteve joined the game\x1b[0m", ActivityKind.JOINED, "Steve"),
        ("[12:00:00] [Server thread/INFO]: Starting minecraft server version 1.21.11", ActivityKind.STARTING, ""),
    ],
)
def test_join_leave_and_start_lines_are_recognised(text: str, kind: ActivityKind, value: str) -> None:
    event = parse_activity_line(text)
    assert event is not None and event.kind is kind and event.name == value


def test_list_answers_of_vanilla_and_paper() -> None:
    vanilla = parse_activity_line("[12:00:10] [Server thread/INFO]: There are 2 of a max of 20 players online: A, B")
    assert vanilla is not None and (vanilla.count, vanilla.maximum, vanilla.names) == (2, 20, ("A", "B"))
    empty = parse_activity_line("[12:00:10] [Server thread/INFO]: There are 0 of a max of 10 players online: ")
    assert empty is not None and empty.names == ()
    paper = parse_activity_line("[12:00:10 INFO]: There are 3 out of maximum 50 players online.")
    assert paper is not None and (paper.count, paper.maximum, paper.names) == (3, 50, None)


def test_tps_line_is_capped_at_20() -> None:
    event = parse_activity_line("[12:00:11 INFO]: TPS from last 1m, 5m, 15m: *20.01, 19.98, 20.0")
    assert event is not None and event.tps == 20.0
    slow = parse_activity_line("[12:00:11 INFO]: TPS from last 1m, 5m, 15m: 14.5, 18.0, 19.9")
    assert slow is not None and slow.tps == 14.5


@pytest.mark.parametrize(
    "text",
    [
        "[12:00:00] [Server thread/INFO]: <Steve> Steve joined the game",  # chat that quotes the message
        '[12:00:00] [Server thread/INFO]: Done (3.2s)! For help, type "help"',
        "random text",
    ],
)
def test_other_lines_are_ignored(text: str) -> None:
    assert parse_activity_line(text) is None


def test_activity_tracks_players_per_run_and_server() -> None:
    activity = ServerActivity(max_players=lambda _server_id: 20)
    activity.on_line(line("[12:00:00] [Server thread/INFO]: Starting minecraft server version 1.21.11"))
    activity.on_line(line("[12:00:01] [Server thread/INFO]: Steve joined the game"))
    activity.on_line(line("[12:00:02] [Server thread/INFO]: alex joined the game"))
    activity.on_line(line("[12:00:03] [Server thread/INFO]: Other joined the game", server_id="creative"))
    activity.on_line(line("Steve joined the game", stream=OutputStream.COMMAND))  # an echoed command never counts

    snapshot = activity.snapshot("survival")
    assert snapshot.players == ("alex", "Steve") and snapshot.player_count == 2 and snapshot.max_players == 20
    assert snapshot.tps is None

    activity.on_line(line("[12:00:04] [Server thread/INFO]: Steve left the game"))
    activity.on_line(line("[12:00:05 INFO]: TPS from last 1m, 5m, 15m: 19.5, 20.0, 20.0"))
    snapshot = activity.snapshot("survival")
    assert snapshot.players == ("alex",) and snapshot.tps == 19.5

    activity.on_line(line("[12:10:00] [Server thread/INFO]: Starting minecraft server version 1.21.11"))
    assert activity.snapshot("survival").players == ()
    assert activity.snapshot("creative").players == ("Other",)


def test_list_answer_corrects_the_count_and_maximum() -> None:
    activity = ServerActivity()
    activity.on_line(line("[12:00:01] [Server thread/INFO]: Steve joined the game"))
    activity.on_line(line("[12:00:10 INFO]: There are 4 out of maximum 30 players online."))
    snapshot = activity.snapshot("survival")
    assert snapshot.player_count == 4 and snapshot.max_players == 30 and snapshot.players == ("Steve",)
    activity.on_line(line("[12:00:11] [Server thread/INFO]: There are 1 of a max of 30 players online: Alex"))
    assert activity.snapshot("survival").players == ("Alex",)


def test_unreadable_max_players_is_unknown() -> None:
    def broken(_server_id: str) -> int | None:
        raise OSError("gone")

    assert ServerActivity(max_players=broken).snapshot("survival").max_players is None


# --- auto-restart policy -------------------------------------------------------------------------


def failure(kind: FailureKind = FailureKind.UNEXPECTED_EXIT, server_id: str = "survival") -> ServerFailure:
    return ServerFailure(server_id, kind, 1, (), diagnose(()))


def test_auto_restart_is_off_unless_enabled() -> None:
    assert AutoRestartPolicy(lambda: False).decide(failure()).restart is False


def test_auto_restart_never_restarts_a_start_timeout() -> None:
    assert AutoRestartPolicy(lambda: True).decide(failure(FailureKind.START_TIMEOUT)).restart is False


def test_auto_restart_gives_up_after_the_limit_and_recovers_after_the_window() -> None:
    now = [0.0]
    policy = AutoRestartPolicy(lambda: True, max_restarts=3, window_seconds=600, clock=lambda: now[0])
    attempts = [policy.decide(failure()) for _ in range(3)]
    assert [decision.attempt for decision in attempts] == [1, 2, 3] and all(d.restart for d in attempts)
    fourth = policy.decide(failure())
    assert fourth.restart is False and fourth.gave_up is True
    assert policy.decide(failure(server_id="creative")).restart is True  # counted per server
    now[0] = 601.0
    assert policy.decide(failure()).attempt == 1


def test_reset_forgets_earlier_restarts() -> None:
    policy = AutoRestartPolicy(lambda: True, max_restarts=1)
    assert policy.decide(failure()).restart
    assert not policy.decide(failure()).restart
    policy.reset("survival")
    assert policy.decide(failure()).restart


# --- LAN address ---------------------------------------------------------------------------------


class Properties:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def load(self, server_id: str):  # type: ignore[no-untyped-def]
        from mcserver.application.server_properties import ServerPropertiesView

        return ServerPropertiesView(server_id, self.values, True, False)


@pytest.mark.parametrize(
    ("values", "lan", "expected"),
    [
        ({}, "192.168.1.5", "192.168.1.5"),
        ({"server-port": "25570"}, "192.168.1.5", "192.168.1.5:25570"),
        ({"server-port": "nope"}, "10.0.0.2", "10.0.0.2"),
        ({"server-ip": "10.1.1.1", "server-port": "25566"}, "192.168.1.5", "10.1.1.1:25566"),
    ],
)
def test_address_combines_port_and_lan_host(values: dict[str, str], lan: str, expected: str) -> None:
    lookup = ServerAddressLookup(Properties(values), lambda: lan)  # type: ignore[arg-type]
    assert str(lookup.address("survival")) == expected


def test_address_is_unknown_without_a_network() -> None:
    lookup = ServerAddressLookup(Properties({}), lambda: None)  # type: ignore[arg-type]
    assert lookup.address("survival") is None
    assert str(ServerAddress("h", 25565)) == "h"
