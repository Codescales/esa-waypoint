from datetime import datetime
from zoneinfo import ZoneInfo

from src.tiltify_push import (
    classify,
    compute_amount_cents,
    build_reward_request,
    build_poll_request,
    build_target_request,
    names_match,
    amounts_match,
    already_exists,
    collect_actions,
    execute,
    summarize,
    format_action_line,
    format_summary_line,
    PushAction,
    PushSummary,
    _first_line,
    _rest,
    _participant_label,
)
from src.xlsx_reader import IncentiveRow
from src.tiltify import (
    CreateRewardRequest,
    CreatePollRequest,
    CreateTargetRequest,
    ExistingReward,
    StubTiltifyClient,
)

TZ = ZoneInfo("Europe/Stockholm")


def _make_row(**overrides) -> IncentiveRow:
    defaults = dict(
        scheduled=datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ),
        game="Super Mario 64",
        category="Any%",
        stream="stream1",
        runner_display="Runner1",
        runner_twitch="runner1",
        runner_discord="",
        incentive_text="Race to the end",
        incentive_category="Reward",
        valid_for_game="Yes",
        incentive_estimate="10",
        needs_approval="No",
        status="Approved",
        submission_id="123",
        uuid="uuid-1",
        participants=[],
    )
    defaults.update(overrides)
    return IncentiveRow(**defaults)


class TestClassify:
    def test_reward(self):
        kind, reason = classify(_make_row(incentive_category="Reward"))
        assert kind == "reward"

    def test_poll(self):
        kind, reason = classify(_make_row(incentive_category="Poll-Bid War"))
        assert kind == "poll"

    def test_target(self):
        kind, reason = classify(_make_row(incentive_category="Target"))
        assert kind == "target"

    def test_skip_not_approved(self):
        kind, reason = classify(_make_row(status="To-Do"))
        assert kind == "skip"

    def test_skip_invalid_valid_for_game(self):
        kind, reason = classify(_make_row(valid_for_game="No"))
        assert kind == "skip"

    def test_needs_info_empty_category(self):
        kind, reason = classify(_make_row(incentive_category=""))
        assert kind == "needs-info"

    def test_needs_info_unknown_category(self):
        kind, reason = classify(_make_row(incentive_category="Unknown"))
        assert kind == "needs-info"


class TestComputeAmountCents:
    def test_from_estimate_string(self):
        row = _make_row(incentive_estimate="5")
        assert compute_amount_cents(row) == 2500  # 5 * 5.0 * 100

    def test_from_text_parsing(self):
        row = _make_row(incentive_estimate="adds 10 minutes")
        assert compute_amount_cents(row) == 5000

    def test_none_when_empty(self):
        row = _make_row(incentive_estimate="")
        assert compute_amount_cents(row) is None

    def test_custom_dollar_per_minute(self):
        row = _make_row(incentive_estimate="5")
        assert compute_amount_cents(row, dollar_per_minute=10.0) == 5000


class TestBuildRewardRequest:
    def test_basic(self):
        row = _make_row(incentive_text="Race to the end", details="Extra details")
        req = build_reward_request(row)
        assert req.name == "Race to the end"
        assert "Extra details" in req.description
        assert req.amount_cents == 5000

    def test_no_body(self):
        row = _make_row(incentive_text="Just a name", details="")
        req = build_reward_request(row)
        assert req.name == "Just a name"
        assert "Suggested by" in req.description


class TestBuildPollRequest:
    def test_with_options(self):
        row = _make_row(incentive_text="Pick a character", details="Mario\nLuigi\nPeach")
        req = build_poll_request(row)
        assert req.name == "Pick a character"
        assert req.options == ["Mario", "Luigi", "Peach"]

    def test_no_options_falls_back(self):
        row = _make_row(incentive_text="Just a name", details="")
        req = build_poll_request(row)
        assert req.name == "Just a name"
        assert req.options == ["Just a name"]


class TestBuildTargetRequest:
    def test_basic(self):
        row = _make_row(incentive_text="Raise $500", incentive_estimate="100")
        req = build_target_request(row)
        assert req.name == "Raise $500"
        assert req.amount_cents == 50000


class TestNamesMatch:
    def test_exact(self):
        assert names_match("Hello", "Hello")

    def test_casefold(self):
        assert names_match("Hello", "hello")

    def test_strip(self):
        assert names_match("  Hello  ", "hello")

    def test_different(self):
        assert not names_match("Hello", "World")


class TestAmountsMatch:
    def test_exact(self):
        assert amounts_match(1000, 1000)

    def test_within_tolerance(self):
        assert amounts_match(1000, 1050, tol=100)

    def test_outside_tolerance(self):
        assert not amounts_match(1000, 1200, tol=100)

    def test_both_none(self):
        assert amounts_match(None, None)

    def test_one_none(self):
        assert not amounts_match(1000, None)


class TestAlreadyExists:
    def test_reward_match(self):
        req = CreateRewardRequest(name="Test", amount_cents=1000, description="")
        existing = [ExistingReward(reward_id="r1", name="test", amount_cents=1000)]
        result = already_exists(req, existing)
        assert result is not None
        assert result.reward_id == "r1"

    def test_poll_match(self):
        req = CreatePollRequest(name="Test", options=["A", "B"])
        existing = [ExistingReward(reward_id="r1", name="test", amount_cents=None)]
        result = already_exists(req, existing)
        assert result is not None

    def test_no_match(self):
        req = CreateRewardRequest(name="Unique", amount_cents=1000, description="")
        existing = [ExistingReward(reward_id="r1", name="other", amount_cents=1000)]
        assert already_exists(req, existing) is None


class TestCollectActions:
    def test_approved_reward_creates_action(self):
        row = _make_row()
        actions = collect_actions([row], [])
        assert len(actions) == 1
        assert actions[0].status == "would-create"
        assert actions[0].resource_kind == "reward"

    def test_skip_not_approved(self):
        row = _make_row(status="To-Do")
        actions = collect_actions([row], [])
        assert actions[0].status == "skip"

    def test_skipped_existing(self):
        row = _make_row(incentive_text="Existing", incentive_estimate="5")
        existing = [ExistingReward(reward_id="r1", name="existing", amount_cents=2500)]
        actions = collect_actions([row], existing)
        assert actions[0].status == "skipped-existing"

    def test_needs_info_no_amount(self):
        row = _make_row(incentive_estimate="")
        actions = collect_actions([row], [])
        assert actions[0].status == "needs-info"

    def test_poll_creates_action(self):
        row = _make_row(incentive_category="Poll-Bid War", incentive_text="Vote\nA\nB")
        actions = collect_actions([row], [])
        assert actions[0].status == "would-create"
        assert actions[0].resource_kind == "poll"

    def test_target_creates_action(self):
        row = _make_row(incentive_category="Target", incentive_estimate="10")
        actions = collect_actions([row], [])
        assert actions[0].status == "would-create"
        assert actions[0].resource_kind == "target"


class TestExecute:
    def test_dry_run_does_not_create(self):
        row = _make_row()
        actions = collect_actions([row], [])
        client = StubTiltifyClient()
        summary = execute(actions, client, dry_run=True)
        assert summary.would_create == 1
        assert summary.created == 0

    def test_create_reward(self):
        row = _make_row()
        actions = collect_actions([row], [])
        client = StubTiltifyClient()
        summary = execute(actions, client, dry_run=False)
        assert summary.created == 1

    def test_create_poll(self):
        row = _make_row(incentive_category="Poll-Bid War", incentive_text="Vote\nA\nB")
        actions = collect_actions([row], [])
        client = StubTiltifyClient()
        summary = execute(actions, client, dry_run=False)
        assert summary.created == 1

    def test_create_target(self):
        row = _make_row(incentive_category="Target", incentive_estimate="10")
        actions = collect_actions([row], [])
        client = StubTiltifyClient()
        summary = execute(actions, client, dry_run=False)
        assert summary.created == 1

    def test_keep_going_on_failure(self):
        class FailingClient:
            def create_reward(self, req):
                raise RuntimeError("fail")
            def create_poll(self, req):
                raise RuntimeError("fail")
            def create_target(self, req):
                raise RuntimeError("fail")

        rows = [_make_row(), _make_row(incentive_text="Second")]
        actions = collect_actions(rows, [])
        client = FailingClient()
        summary = execute(actions, client, dry_run=False, keep_going=True)
        assert summary.failed == 2


class TestSummarize:
    def test_counts(self):
        actions = [
            PushAction(row=_make_row(), status="skip"),
            PushAction(row=_make_row(), status="created"),
            PushAction(row=_make_row(), status="failed"),
            PushAction(row=_make_row(), status="would-create"),
            PushAction(row=_make_row(), status="skipped-existing"),
            PushAction(row=_make_row(), status="needs-info"),
        ]
        s = summarize(actions)
        assert s.total == 6
        assert s.skipped == 1
        assert s.created == 1
        assert s.failed == 1
        assert s.would_create == 1
        assert s.skipped_existing == 1
        assert s.needs_info == 1


class TestFormatActionLine:
    def test_basic(self):
        action = PushAction(
            row=_make_row(),
            resource_kind="reward",
            status="would-create",
            amount_cents=5000,
        )
        line = format_action_line(action)
        assert "[W]" in line
        assert "reward" in line
        assert "Super Mario 64" in line

    def test_with_tiltify_id(self):
        action = PushAction(
            row=_make_row(),
            resource_kind="reward",
            status="created",
            tiltify_id="r123",
        )
        line = format_action_line(action)
        assert "id=r123" in line


class TestFormatSummaryLine:
    def test_basic(self):
        s = PushSummary(total=10, created=5, skipped=2)
        line = format_summary_line(s)
        assert "total=10" in line
        assert "created=5" in line
        assert "skipped=2" in line


class TestFirstLine:
    def test_single_line(self):
        assert _first_line("Hello") == "Hello"

    def test_multi_line(self):
        assert _first_line("Hello\nWorld") == "Hello"

    def test_empty(self):
        assert _first_line("") == ""


class TestRest:
    def test_has_rest(self):
        assert _rest("Hello\nWorld") == "World"

    def test_no_rest(self):
        assert _rest("Hello") == ""


class TestParticipantLabel:
    def test_single_runner(self):
        row = _make_row(runner_display="Runner1")
        assert _participant_label(row) == "Runner1"

    def test_multiple_participants(self):
        row = _make_row(participants=[{"display": "A"}, {"display": "B"}])
        assert _participant_label(row) == "A vs B"

    def test_no_participants_fallback(self):
        row = _make_row(runner_display="Runner1", participants=[])
        assert _participant_label(row) == "Runner1"
