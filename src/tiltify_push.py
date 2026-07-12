"""Tiltify push orchestrator — pure-python classifier + idempotency.

This module contains *no* browser automation. It reads spreadsheet rows
loaded by `xlsx_reader` and produces `PushAction` records that
`pipeline.py` then sends to a `TiltifyClient`.

Two phases, separated for testability:

  collect_actions(incentives, existing_rewards, dollar_per_minute) -> list[PushAction]
      Pure. Classifies each row, filters out non-approved/non-valid rows,
      builds a CreateRewardRequest / CreatePollRequest / CreateTargetRequest,
      and checks idempotency against the existing Tiltify rewards list.
      Sets status to one of: 'skip', 'needs-info', 'skipped-existing',
      'would-create'.

  execute(actions, client, dry_run=False, keep_going=False) -> None
      Mutates actions in place. Sends 'would-create' rows to the client.
      Updates status to 'created' or 'failed'. Stops on first failure
      unless `keep_going=True`. Pure no-op if `dry_run=True`.

Mapping from spreadsheet -> Tiltify resource
--------------------------------------------

  incentive_category == "Reward"        -> CreateRewardRequest
  incentive_category == "Poll-Bid War"  -> CreatePollRequest
                                         options = lines after the first line
                                         of incentive_text
  incentive_category == "Target"        -> CreateTargetRequest

Filter criteria for pushing
----------------------------

  row.status == "Approved"
  row.valid_for_game in {"Yes", "Needs Review"}

  Anything else is classified as 'skip' or 'needs-info' and never
  reaches the TiltifyClient.

Idempotency
-----------

Match by (name, amount) per-resource:

  Reward:  name_casefold == existing.name_casefold,
           |amount - existing.amount_cents| <= 100 cents
  Poll:    name_casefold == existing.name_casefold   (polls have no amount)
  Target:  name_casefold == existing.name_casefold,
           |amount - existing.amount_cents| <= 100 cents

The 100-cent tolerance avoids re-creating rewards when the dollar/minute
conversion rounding differs by a cent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from .xlsx_reader import IncentiveRow
from .incentives import extract_estimate_minutes
from .tiltify import (
    CreateRewardRequest,
    CreatePollRequest,
    CreateTargetRequest,
    ExistingReward,
    TiltifyClient,
)

AMOUNT_TOLERANCE_CENTS = 100
DEFAULT_DOLLAR_PER_MINUTE = 5.0
RESOURCE_KINDS = ("reward", "poll", "target")


@dataclass
class PushAction:
    row: IncentiveRow
    resource_kind: Optional[str] = None
    """
    One of: 'skip' | 'needs-info' | 'skipped-existing' | 'would-create'
    | 'created' | 'failed'.  'would-create' is also used during dry-run.
    """
    status: str = "skip"
    reason: str = ""
    amount_cents: Optional[int] = None
    tiltify_id: Optional[str] = None
    request: Optional[Union[CreateRewardRequest, CreatePollRequest, CreateTargetRequest]] = None


@dataclass
class PushSummary:
    total: int = 0
    created: int = 0
    skipped_existing: int = 0
    would_create: int = 0
    failed: int = 0
    needs_info: int = 0
    skipped: int = 0

    @property
    def exit_code(self) -> int:
        return 0 if self.failed == 0 else 1


def classify(row: IncentiveRow) -> tuple[str, str]:
    """Return (resource_kind, reason).

    resource_kind is one of: 'reward', 'poll', 'target', 'skip', 'needs-info'.
    The push code translates 'skip' and 'needs-info' into terminal action
    statuses; the others into create requests.
    """
    status = (row.status or "").strip().lower()
    if status != "approved":
        return "skip", f"status={row.status!r} (only 'Approved' is pushed)"
    valid = (row.valid_for_game or "").strip().lower()
    if valid not in {"yes", "needs review"}:
        return "skip", f"valid_for_game={row.valid_for_game!r}"
    cat = (row.incentive_category or "").strip().lower()
    if cat == "reward":
        return "reward", ""
    if cat in {"poll-bid war", "poll-bid-war", "poll"}:
        return "poll", ""
    if cat == "target":
        return "target", ""
    if not cat:
        return "needs-info", "incentive_category is empty"
    return "needs-info", f"unknown incentive_category={row.incentive_category!r}"


def compute_amount_cents(row: IncentiveRow, dollar_per_minute: float = DEFAULT_DOLLAR_PER_MINUTE) -> Optional[int]:
    """Convert incentive_estimate (a minutes string) into a cents integer.

    The Incentives Detail sheet stores the minutes column as a bare integer
    string (`"5"`, `"10"`) for human-edited rows, but the raw runner-submitted
    text (`"adds about 5 minutes"`) is also possible. Try plain integer first,
    fall back to text parsing, then return None if neither works.
    """
    raw = (row.incentive_estimate or "").strip()
    mins: Optional[int] = None
    if raw and raw.isdigit():
        mins = int(raw)
    if mins is None:
        mins = extract_estimate_minutes(raw) if raw else None
    if mins is None or mins <= 0:
        return None
    dollars = int(mins) * float(dollar_per_minute)
    return int(round(dollars * 100))


def _first_line(text: str) -> str:
    return (text.split("\n", 1)[0] or "").strip()


def _rest(text: str) -> str:
    parts = text.split("\n", 1)
    return parts[1].strip() if len(parts) > 1 else ""


def _participant_label(row: IncentiveRow) -> str:
    """Return a display label for the runner(s) on an incentive row.

    Single runner → that runner's display name.
    Multiple runners → "A vs B vs C" (capped at 3 for description length).
    Falls back to `row.runner_display` for legacy rows without participants.
    """
    participants = getattr(row, "participants", None) or []
    if not participants:
        return row.runner_display or "unknown"
    names = [p.get("display") or p.get("name") or "" for p in participants if p]
    names = [n for n in names if n][:3]
    if not names:
        return row.runner_display or "unknown"
    return " vs ".join(names)


def build_reward_request(row: IncentiveRow, dollar_per_minute: float = DEFAULT_DOLLAR_PER_MINUTE) -> CreateRewardRequest:
    name = row.incentive_text.strip()
    body = row.details or ""
    label = _participant_label(row)
    if body:
        description = f"[{label} · {row.game}] {body}"
    else:
        description = f"Suggested by {label} for {row.game} ({row.category})"
    amount = compute_amount_cents(row, dollar_per_minute) or 0
    return CreateRewardRequest(
        name=name,
        amount_cents=amount,
        description=description,
    )


def build_poll_request(row: IncentiveRow) -> CreatePollRequest:
    name = row.incentive_text.strip()
    body = row.details or ""
    options = [line.strip() for line in body.splitlines() if line.strip()]
    if not options:
        options = [name]
    return CreatePollRequest(name=name, options=options)


def build_target_request(row: IncentiveRow, dollar_per_minute: float = DEFAULT_DOLLAR_PER_MINUTE) -> CreateTargetRequest:
    name = row.incentive_text.strip()
    amount = compute_amount_cents(row, dollar_per_minute) or 0
    return CreateTargetRequest(name=name, amount_cents=amount)


def names_match(a: str, b: str) -> bool:
    return (a or "").casefold().strip() == (b or "").casefold().strip()


def amounts_match(a: Optional[int], b: Optional[int], tol: int = AMOUNT_TOLERANCE_CENTS) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def already_exists(req, existing: list[ExistingReward]) -> Optional[ExistingReward]:
    """Return the ExistingReward that req would collide with, if any."""
    for r in existing:
        if isinstance(req, CreateRewardRequest):
            if names_match(req.name, r.name) and amounts_match(req.amount_cents, r.amount_cents):
                return r
        elif isinstance(req, CreatePollRequest):
            if names_match(req.name, r.name):
                return r
        elif isinstance(req, CreateTargetRequest):
            if names_match(req.name, r.name) and amounts_match(req.amount_cents, r.amount_cents):
                return r
    return None


def collect_actions(
    incentives: list[IncentiveRow],
    existing_rewards: list[ExistingReward],
    dollar_per_minute: float = DEFAULT_DOLLAR_PER_MINUTE,
) -> list[PushAction]:
    """Phase 1: classify + build requests + idempotency check. Pure, no IO."""
    actions: list[PushAction] = []
    for row in incentives:
        kind, reason = classify(row)
        if kind == "skip":
            actions.append(PushAction(row=row, status="skip", reason=reason))
            continue
        if kind == "needs-info":
            actions.append(PushAction(row=row, status="needs-info", reason=reason))
            continue

        if kind == "reward":
            req: Union[CreateRewardRequest, CreatePollRequest, CreateTargetRequest] = (
                build_reward_request(row, dollar_per_minute)
            )
        elif kind == "poll":
            req = build_poll_request(row)
        elif kind == "target":
            req = build_target_request(row, dollar_per_minute)
        else:
            actions.append(PushAction(row=row, status="skip", reason=f"unknown kind {kind!r}"))
            continue

        match = already_exists(req, existing_rewards)
        if match is not None:
            match_desc = match.name or match.reward_id or "<unknown>"
            actions.append(PushAction(
                row=row,
                resource_kind=kind,
                status="skipped-existing",
                reason=f"matches existing Tiltify reward '{match_desc}'",
                tiltify_id=match.reward_id,
                request=req,
            ))
            continue

        amount_cents = getattr(req, "amount_cents", None)
        if kind in {"reward", "target"} and (amount_cents is None or amount_cents == 0):
            actions.append(PushAction(
                row=row,
                resource_kind=kind,
                status="needs-info",
                reason="incentive_estimate is empty / unparseable; cannot compute amount",
                request=req,
                amount_cents=amount_cents,
            ))
            continue

        actions.append(PushAction(
            row=row,
            resource_kind=kind,
            status="would-create",
            request=req,
            amount_cents=amount_cents,
        ))
    return actions


def execute(
    actions: list[PushAction],
    client: TiltifyClient,
    dry_run: bool = False,
    keep_going: bool = False,
) -> PushSummary:
    """Phase 2: send create requests to the client. Mutates `actions`.

    In `dry_run=True` no client calls are made; 'would-create' actions
    remain in 'would-create' status. The summary distinguishes created
    from would_create counts.
    """
    summary = PushSummary(total=len(actions))
    for action in actions:
        if action.status == "skip":
            summary.skipped += 1
        elif action.status == "needs-info":
            summary.needs_info += 1
        elif action.status == "skipped-existing":
            summary.skipped_existing += 1
        elif action.status == "would-create":
            if dry_run:
                summary.would_create += 1
                continue
            try:
                if action.resource_kind == "reward":
                    action.tiltify_id = client.create_reward(action.request)
                elif action.resource_kind == "poll":
                    action.tiltify_id = client.create_poll(action.request)
                elif action.resource_kind == "target":
                    action.tiltify_id = client.create_target(action.request)
                else:
                    action.status = "failed"
                    action.reason = f"unknown resource_kind {action.resource_kind!r}"
                    summary.failed += 1
                    if not keep_going:
                        break
                    continue
                action.status = "created"
                summary.created += 1
            except Exception as e:
                action.status = "failed"
                action.reason = f"{type(e).__name__}: {e}"
                summary.failed += 1
                if not keep_going:
                    break
        else:
            pass
    return summary


def summarize(actions: list[PushAction]) -> PushSummary:
    """Compute a summary without executing. Useful for tests."""
    summary = PushSummary(total=len(actions))
    for a in actions:
        if a.status == "skip":
            summary.skipped += 1
        elif a.status == "needs-info":
            summary.needs_info += 1
        elif a.status == "skipped-existing":
            summary.skipped_existing += 1
        elif a.status == "would-create":
            summary.would_create += 1
        elif a.status == "created":
            summary.created += 1
        elif a.status == "failed":
            summary.failed += 1
    return summary


def format_action_line(action: PushAction) -> str:
    """One-line human-readable status, for the CLI's per-row report."""
    kind = action.resource_kind or "-"
    status_code = action.status[0].upper() if action.status else "?"
    game = action.row.game
    incentive = _first_line(action.row.incentive_text)
    amount_str = (
        f"${action.amount_cents / 100:.2f}"
        if action.amount_cents is not None
        else ""
    )
    tail = action.reason or ""
    if action.tiltify_id:
        tail = f"id={action.tiltify_id}" + (f"; {tail}" if tail else "")
    parts = [
        f"[{status_code}] {kind:<6} {game:<30} {incentive:<40}",
    ]
    if amount_str:
        parts[0] += f"  {amount_str}"
    if tail:
        parts.append(f"  -- {tail}")
    return "".join(parts)


def format_summary_line(summary: PushSummary) -> str:
    return (
        f"Summary: total={summary.total} "
        f"created={summary.created} "
        f"skipped_existing={summary.skipped_existing} "
        f"would_create={summary.would_create} "
        f"failed={summary.failed} "
        f"needs_info={summary.needs_info} "
        f"skipped={summary.skipped}"
    )