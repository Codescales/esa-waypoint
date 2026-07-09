"""Oengus marathon submission data fetcher.

Oengus API endpoints:
  Marathon info:  https://oengus.io/api/v1/marathons/{id}
  Submissions:    https://oengus.io/api/v1/marathons/{id}/submissions

Public API returns empty answers for custom questions. Moderator access
(via session cookie) is needed to see submission answers with incentive data.
"""

import requests
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

_session: Optional[requests.Session] = None


def set_auth_token(token: str) -> None:
    """Set an Oengus Bearer token for authenticated requests.

    Pass the JWT from the Authorization: Bearer header in browser DevTools > Network.
    """
    global _session
    _session = requests.Session()
    _session.headers.update({
        "Authorization": f"Bearer {token}",
        "oengus-version": "1",
    })


def login(username: str, password: str, two_factor_code: str = None) -> str:
    """Log into Oengus and return a JWT token.

    Calls POST /v2/auth/login with username and password.
    If the account has 2FA enabled, returns "MFA_REQUIRED" status.
    Call again with two_factor_code to complete login.
    Returns the token string, or raises ValueError on failure.
    """
    body = {"username": username, "password": password}
    if two_factor_code:
        body["twoFactorCode"] = two_factor_code

    resp = requests.post(
        "https://oengus.io/api/v2/auth/login",
        json=body,
        timeout=30,
    )
    data = resp.json()
    status = data.get("status", "")
    if status == "LOGIN_SUCCESS":
        token = data["token"]
        set_auth_token(token)
        return token
    if status == "MFA_REQUIRED":
        raise MfaRequired()
    raise ValueError(f"Login failed: {status}")


def refresh_token() -> str:
    """Refresh the current JWT token, extending its expiry by 7 days.

    Calls POST /v2/auth/refresh-token. Requires an active session (valid token).
    Returns the new token string, or raises ValueError on failure.
    """
    if not _session:
        raise ValueError("No active session to refresh. Set a token first.")
    resp = _session.post("https://oengus.io/api/v2/auth/refresh-token", timeout=30)
    data = resp.json()
    status = data.get("status", "")
    if status == "LOGIN_SUCCESS":
        token = data["token"]
        set_auth_token(token)
        return token
    raise ValueError(f"Token refresh failed: {status}")


class MfaRequired(Exception):
    """Raised when login requires a 2FA code."""
    pass


def set_session_cookie(cookie: str) -> None:
    """Set an Oengus session cookie for authenticated requests.

    Pass the full cookie string from your browser (e.g. from DevTools > Application > Cookies).
    """
    global _session
    _session = requests.Session()
    _session.headers.update({"Cookie": cookie})


def _session_active() -> bool:
    return _session is not None


def _clear_session() -> None:
    """Clear the authenticated session (e.g. when token is expired)."""
    global _session
    _session = None


def _get(url: str, params: dict = None) -> requests.Response:
    if _session:
        return _session.get(url, timeout=30, params=params)
    return requests.get(url, timeout=30, params=params)


@dataclass
class OengusCategory:
    id: int
    name: str
    description: str
    estimate: str
    video: Optional[str]
    game_id: int
    submission_id: int


@dataclass
class OengusGame:
    id: int
    name: str
    console: str
    description: str
    emulated: bool
    submission_id: int
    categories: list[OengusCategory] = field(default_factory=list)


@dataclass
class OengusUser:
    id: int
    username: str
    display_name: str
    twitch: Optional[str]
    discord: Optional[str]
    twitter: Optional[str]


@dataclass
class OengusSubmission:
    id: int
    user: OengusUser
    games: list[OengusGame] = field(default_factory=list)
    availabilities: list[dict] = field(default_factory=list)
    answers: list[dict] = field(default_factory=list)

    def get_answer(self, label: str) -> Optional[str]:
        """Get a custom question answer by label."""
        for a in self.answers:
            if a.get("label", "").lower() == label.lower():
                return a.get("answer")
        return None


@dataclass
class OengusMarathon:
    id: str
    name: str
    start_date: datetime
    end_date: datetime
    submissions_end_date: Optional[datetime]
    questions: list[dict] = field(default_factory=list)
    submissions: list[OengusSubmission] = field(default_factory=list)


def _parse_user(user_data: dict) -> OengusUser:
    twitch = None
    discord = None
    twitter = None
    for conn in user_data.get("connections", []):
        platform = conn.get("platform", "").upper()
        username = conn.get("username")
        if platform == "TWITCH":
            twitch = username
        elif platform == "DISCORD":
            discord = username
        elif platform == "TWITTER":
            twitter = username
    return OengusUser(
        id=user_data["id"],
        username=user_data["username"],
        display_name=user_data.get("displayName", user_data["username"]),
        twitch=twitch,
        discord=discord,
        twitter=twitter,
    )


def _parse_category(cat_data: dict) -> OengusCategory:
    return OengusCategory(
        id=cat_data["id"],
        name=cat_data["name"],
        description=cat_data.get("description", ""),
        estimate=cat_data.get("estimate", ""),
        video=cat_data.get("video"),
        game_id=cat_data.get("gameId", 0),
        submission_id=cat_data.get("submissionId", 0),
    )


def _parse_game(game_data: dict) -> OengusGame:
    return OengusGame(
        id=game_data["id"],
        name=game_data["name"],
        console=game_data.get("console", ""),
        description=game_data.get("description", ""),
        emulated=game_data.get("emulated", False),
        submission_id=game_data.get("submissionId", 0),
        categories=[_parse_category(c) for c in game_data.get("categories", [])],
    )


def _parse_submission(sub_data: dict) -> OengusSubmission:
    return OengusSubmission(
        id=sub_data["id"],
        user=_parse_user(sub_data["user"]),
        games=[_parse_game(g) for g in sub_data.get("games", [])],
        availabilities=sub_data.get("availabilities", []),
        answers=sub_data.get("answers", []),
    )


def fetch_marathon(marathon_id: str) -> OengusMarathon:
    """Fetch marathon info and all submissions from Oengus (all pages).

    When authenticated (session cookie set), also fetches answers from the
    moderator-only /answers endpoint and merges them into submissions.
    """
    info_url = f"https://oengus.io/api/v1/marathons/{marathon_id}"

    info_resp = _get(info_url)
    info_resp.raise_for_status()
    info = info_resp.json()

    questions = info.get("questions", [])
    question_by_id = {q["id"]: q for q in questions}

    submissions = []
    page = 0
    while True:
        subs_url = f"https://oengus.io/api/v1/marathons/{marathon_id}/submissions?page={page}"
        subs_resp = _get(subs_url)
        subs_resp.raise_for_status()
        subs_data = subs_resp.json()
        content = subs_data.get("content", subs_data.get("data", []))
        if not content:
            break
        submissions.extend(_parse_submission(s) for s in content)
        if subs_data.get("last", False):
            break
        page += 1

    if _session:
        _merge_answers(marathon_id, submissions, question_by_id)

    return OengusMarathon(
        id=info["id"],
        name=info["name"],
        start_date=datetime.fromisoformat(info["startDate"].replace("Z", "+00:00")),
        end_date=datetime.fromisoformat(info["endDate"].replace("Z", "+00:00")),
        submissions_end_date=(
            datetime.fromisoformat(info["submissionsEndDate"].replace("Z", "+00:00"))
            if info.get("submissionsEndDate") else None
        ),
        questions=questions,
        submissions=submissions,
    )


def _merge_answers(marathon_id: str, submissions: list[OengusSubmission], question_by_id: dict) -> None:
    """Fetch answers from the moderator-only endpoint and merge into submissions."""
    answers_url = f"https://oengus.io/api/v1/marathons/{marathon_id}/submissions/answers"
    resp = _get(answers_url)
    if resp.status_code != 200:
        print(f"  Warning: answers endpoint returned {resp.status_code} (moderator access required)")
        return

    answers_data = resp.json()
    sub_by_id = {s.id: s for s in submissions}

    for a in answers_data:
        sub_id = a.get("submissionId")
        question_id = a.get("questionId")
        answer_text = a.get("answer", "")
        if sub_id and sub_id in sub_by_id and answer_text:
            question = question_by_id.get(question_id, {})
            label = question.get("label", f"question_{question_id}")
            sub_by_id[sub_id].answers.append({"label": label, "answer": answer_text})


def _submission_twitch(sub: "OengusSubmission") -> str:
    """Lowercased twitch handle from an OengusUser's TWITCH connection."""
    return (sub.user.twitch or "").strip().lower()


def _submission_username(sub: "OengusSubmission") -> str:
    """Lowercased OengusUser.username (NOT displayName — they diverge)."""
    return (sub.user.username or "").strip().lower()


def _submission_matches_game_category(sub: "OengusSubmission", game: str, category: str) -> bool:
    """True if submission has a game/category match by name (case-insensitive).

    Used for defense-in-depth race detection: a schedule item whose `players`
    markdown has typos can still pick up a co-runner's submission if both
    submitted the same game+category. Match by name only — `category_id`
    can differ across race submissions of the same category.
    """
    game_l = (game or "").strip().lower()
    cat_l = (category or "").strip().lower()
    if not game_l or not cat_l:
        return False
    for g in sub.games:
        if (g.name or "").strip().lower() != game_l:
            continue
        for c in g.categories:
            if (c.name or "").strip().lower() == cat_l:
                return True
    return False


def find_participant_submissions(
    item: "ScheduleItem",
    all_submissions: list["OengusSubmission"],
) -> list[tuple["OengusSubmission", str, str]]:
    """Match all Oengus submissions whose runner appears in this schedule item.

    Returns a list of `(submission, match_confidence, source_twitch_or_username)`.
    The Horaro-linked primary submission is returned first (highest priority)
    when present; remaining matches follow in markdown order. Same submission
    is never returned twice.

    Match confidence values:
      - "twitch" — markdown twitch handle == OengusUser TWITCH connection
      - "name"   — markdown link text == OengusUser.username (NOT displayName)
      - "game-category" — same game+category submitted; user is not in
        players markdown (defense-in-depth, e.g. markdown typo)

    Markdown entries that produce no Oengus match are NOT returned. The
    caller decides whether to surface them as `match_confidence="markdown-only"`
    participants built from the markdown alone.
    """
    from .horaro import ScheduleItem  # local import to avoid cycle
    assert isinstance(item, ScheduleItem)

    entries = item.participants

    # Pre-index by twitch + username for O(1) lookup
    by_twitch: dict[str, OengusSubmission] = {}
    by_username: dict[str, OengusSubmission] = {}
    for sub in all_submissions:
        t = _submission_twitch(sub)
        if t:
            by_twitch.setdefault(t, sub)
        u = _submission_username(sub)
        if u:
            by_username.setdefault(u, sub)

    results: list[tuple[OengusSubmission, str, str]] = []
    seen_ids: set[int] = set()

    primary_id: Optional[int] = None
    if item.submission_id:
        try:
            primary_id = int(item.submission_id)
        except (ValueError, TypeError):
            primary_id = None

    primary_sub: Optional[OengusSubmission] = None
    if primary_id is not None:
        for s in all_submissions:
            if s.id == primary_id:
                primary_sub = s
                break
    if primary_sub is not None:
        results.append((primary_sub, "primary", _submission_twitch(primary_sub) or _submission_username(primary_sub)))
        seen_ids.add(primary_sub.id)

    for e in entries:
        match: Optional[OengusSubmission] = None
        confidence = ""
        key = ""
        twitch = (e.get("twitch") or "").strip().lower()
        display = (e.get("display") or "").strip().lower()

        if twitch and twitch in by_twitch:
            match = by_twitch[twitch]
            confidence = "twitch"
            key = twitch
        elif display and display in by_username:
            match = by_username[display]
            confidence = "name"
            key = display

        if match is not None and match.id not in seen_ids:
            results.append((match, confidence, key))
            seen_ids.add(match.id)

    for sub in all_submissions:
        if sub.id in seen_ids:
            continue
        if _submission_matches_game_category(sub, item.game, item.category):
            results.append((sub, "game-category", ""))
            seen_ids.add(sub.id)

    return results
