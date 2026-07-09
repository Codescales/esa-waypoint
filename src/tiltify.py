"""Tiltify dashboard automation.

Tiltify's V5 API exposes no write endpoints for rewards, polls, or targets
(see ADR-012 for rationale). This module drives the Tiltify dashboard via
Playwright to create incentives on behalf of the fundraising team.

Design:

  TiltifySession  - load cookies from a Playwright storage_state JSON or
                    parse a "name=value; name=value" cookie string. Both
                    produce a Playwright-compatible storage_state dict.

  TiltifyClient   - Protocol (structural typing). The push orchestrator
                    depends on this, not on Playwright.

  PlaywrightTiltifyClient
                  - Concrete implementation backed by a real Chromium
                    session. Selectors are module-level constants so they
                    can be patched when Tiltify changes the dashboard DOM.

  StubTiltifyClient
                  - In-memory fake used by tests. Records every call so
                    unit tests can assert on request parameters without
                    launching a browser.

Authentication model
--------------------

Preferred: a one-time `--tiltify-login` flow captures a storage_state JSON
file (cookies + localStorage). Subsequent push runs reuse that file. This
survives Phoenix session rotation as long as the underlying session token
is valid.

Fallback: paste the dashboard cookies into `.env` as `TILTIFY_COOKIE` and
the push command injects them. Cookie-encoded sessions break on rotation.

Both approaches store credentials equivalent to a password. The session
file lives under `output/` (already gitignored) and `chmod 600` is set
on write.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from http.cookiejar import Cookie
from typing import Iterable, Optional, Protocol, runtime_checkable

DEFAULT_DASHBOARD_BASE = "https://app.tiltify.com"
DEFAULT_BROWSER_TIMEOUT_MS = 30_000

SELECTOR_REWARD_TAB_LINK = 'a[href*="/rewards"]'
SELECTOR_CREATE_REWARD_BUTTON = 'text="Create reward+"'
SELECTOR_REWARD_NAME_INPUT = 'input[name="name"]'
SELECTOR_REWARD_AMOUNT_INPUT = 'input[name="amount"]'
SELECTOR_REWARD_DESCRIPTION_INPUT = 'textarea[name="description"]'
SELECTOR_REWARD_SAVE_BUTTON = 'button:has-text("Save")'
SELECTOR_REWARD_LIST_ROW = '[data-testid="reward-row"]'
SELECTOR_REWARD_LIST_ROW_NAME = '[data-testid="reward-name"]'
SELECTOR_REWARD_LIST_ROW_AMOUNT = '[data-testid="reward-amount"]'
SELECTOR_REWARD_LIST_ROW_ID = '[data-testid="reward-id"]'

SELECTOR_POLL_TAB_LINK = 'a[href*="/polls"]'
SELECTOR_CREATE_POLL_BUTTON = 'text="Create poll+"'
SELECTOR_POLL_NAME_INPUT = 'input[name="name"]'
SELECTOR_POLL_OPTION_INPUT_TEMPLATE = 'input[name="option-{i}"]'
SELECTOR_POLL_SAVE_BUTTON = 'button:has-text("Save")'

SELECTOR_TARGET_TAB_LINK = 'a[href*="/targets"]'
SELECTOR_CREATE_TARGET_BUTTON = 'text="Create target+"'
SELECTOR_TARGET_NAME_INPUT = 'input[name="name"]'
SELECTOR_TARGET_AMOUNT_INPUT = 'input[name="amount"]'
SELECTOR_TARGET_SAVE_BUTTON = 'button:has-text("Save")'

SELECTOR_LOGIN_EMAIL = 'input[type="email"]'
SELECTOR_LOGIN_PASSWORD = 'input[type="password"]'
SELECTOR_LOGIN_SUBMIT = 'button[type="submit"]'

TILTIFY_DOMAIN = ".tiltify.com"
SESSION_COOKIE_NAME = "_tiltify_session_key_v7"


@dataclass
class ExistingReward:
    name: str
    amount_cents: Optional[int] = None
    reward_id: Optional[str] = None
    active: Optional[bool] = None


@dataclass
class CreateRewardRequest:
    name: str
    amount_cents: int
    description: str = ""
    quantity: Optional[int] = None


@dataclass
class CreatePollRequest:
    name: str
    options: list[str] = field(default_factory=list)


@dataclass
class CreateTargetRequest:
    name: str
    amount_cents: int


@runtime_checkable
class TiltifyClient(Protocol):
    """Tiltify dashboard automation protocol.

    Implementations MUST support idempotency: `list_rewards()` is called
    once per push run and the orchestrator skips rows whose (name, amount)
    already exist. Implementations MUST be safe to call concurrently with
    different campaigns but may serialize within a single campaign.
    """

    def list_rewards(self) -> list[ExistingReward]:
        ...

    def create_reward(self, req: CreateRewardRequest) -> str:
        ...

    def create_poll(self, req: CreatePollRequest) -> str:
        ...

    def create_target(self, req: CreateTargetRequest) -> str:
        ...

    def close(self) -> None:
        ...


class TiltifySessionError(Exception):
    """Raised when the session cannot be loaded or appears expired."""
    pass


@dataclass
class TiltifySession:
    """Playwright storage_state dict plus optional origin URL for the session.

    Constructed via `from_storage_state(path)` or `from_cookie_header(header)`.
    The resulting `storage_state` is suitable for `playwright.sync_api`
    `BrowserContext.new_page(storage_state=...)`.
    """

    storage_state: dict
    url: str = DEFAULT_DASHBOARD_BASE

    @classmethod
    def from_storage_state(cls, path: str) -> "TiltifySession":
        if not os.path.exists(path):
            raise TiltifySessionError(f"Session file not found: {path}")
        with open(path) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                raise TiltifySessionError(f"Invalid session JSON at {path}: {e}") from e
        if "cookies" not in data and "origins" not in data:
            raise TiltifySessionError(
                f"File at {path} is not a Playwright storage_state dict "
                "(missing 'cookies' or 'origins' key)."
            )
        session_cookie_present = any(
            c.get("name") == SESSION_COOKIE_NAME
            for c in data.get("cookies", [])
        )
        if not session_cookie_present:
            raise TiltifySessionError(
                f"Session file at {path} is missing the auth cookie "
                f"'{SESSION_COOKIE_NAME}'. Re-capture with --tiltify-login or "
                "update the file from DevTools > Application > Cookies."
            )
        return cls(storage_state=data)

    @classmethod
    def from_cookie_header(cls, header: str) -> "TiltifySession":
        """Build a storage_state from a raw `Cookie:` header value.

        The header is what the browser sends in `Cookie:` request header:
        e.g. `_tiltify_session_key_v7=...; cf_clearance=...`. Cookies are
        injected with domain `.tiltify.com` so they apply to all subdomains
        of app.tiltify.com.
        """
        if not header or not header.strip():
            raise TiltifySessionError("Empty Tiltify cookie header.")
        cookies: list[dict] = []
        for part in header.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            name, _, value = part.partition("=")
            name = name.strip()
            value = value.strip()
            if not name:
                continue
            cookies.append({
                "name": name,
                "value": value,
                "domain": TILTIFY_DOMAIN,
                "path": "/",
                "expires": -1,
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            })
        if not any(c["name"] == SESSION_COOKIE_NAME for c in cookies):
            raise TiltifySessionError(
                f"Cookie header is missing '{SESSION_COOKIE_NAME}'. "
                "Re-grab from DevTools > Application > Cookies > app.tiltify.com."
            )
        return cls(storage_state={"cookies": cookies, "origins": []})

    @classmethod
    def from_env(cls) -> Optional["TiltifySession"]:
        """Build from env, preferring a persisted storage_state file."""
        path = os.getenv("TILTIFY_SESSION_PATH", "output/tiltify_session.json")
        header = os.getenv("TILTIFY_COOKIE", "")
        if os.path.exists(path):
            try:
                return cls.from_storage_state(path)
            except TiltifySessionError:
                pass
        if header:
            return cls.from_cookie_header(header)
        return None


def save_session_from_console_cookies(path: str, cookies_json: dict) -> None:
    """Persist a cookies blob (e.g. from the Chrome DevTools Cookies panel)
    as a Playwright storage_state file. Tightens perms on write.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(cookies_json, f, indent=2)
    os.chmod(path, 0o600)


class PlaywrightTiltifyClient:
    """Concrete TiltifyClient backed by a long-running Chromium session.

    Lifecycle: open() -> list_rewards / create_* / ... -> close().

    All selectors are module-level constants prefixed `SELECTOR_`. When
    Tiltify changes the dashboard DOM, update those constants in one place
    instead of hunting through method bodies.

    ⚠️ The selector guesses below have NOT been verified against the live
    dashboard. Run `python -m src.pipeline --tiltify-dry-run` first to
    confirm classification; then `--tiltify-headless=false --tiltify-push
    --max 1` to trial a single reward creation while watching the browser.
    """

    USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        session: TiltifySession,
        campaign_id: str,
        headless: bool = True,
        timeout_ms: int = DEFAULT_BROWSER_TIMEOUT_MS,
    ):
        self._session = session
        self._campaign_id = campaign_id
        self._headless = headless
        self._timeout_ms = timeout_ms
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def open(self) -> "PlaywrightTiltifyClient":
        from playwright.sync_api import sync_playwright

        if self._browser is not None:
            return self

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self._headless,
            args=[f"--user-agent={self.USER_AGENT}"],
        )
        self._context = self._browser.new_context(
            storage_state=self._session.storage_state,
            user_agent=self.USER_AGENT,
            viewport={"width": 1280, "height": 900},
        )
        self._page = self._context.new_page()
        self._page.set_default_timeout(self._timeout_ms)
        return self

    def close(self) -> None:
        for closer_attr in ("_page", "_context", "_browser"):
            obj = getattr(self, closer_attr, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
                setattr(self, closer_attr, None)
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def __enter__(self) -> "PlaywrightTiltifyClient":
        return self.open()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _navigate_to_rewards(self) -> None:
        url = (
            f"{DEFAULT_DASHBOARD_BASE}/dashboard/campaigns/"
            f"{self._campaign_id}/rewards"
        )
        self._page.goto(url, wait_until="networkidle")

    def _navigate_to_polls(self) -> None:
        url = (
            f"{DEFAULT_DASHBOARD_BASE}/dashboard/campaigns/"
            f"{self._campaign_id}/polls"
        )
        self._page.goto(url, wait_until="networkidle")

    def _navigate_to_targets(self) -> None:
        url = (
            f"{DEFAULT_DASHBOARD_BASE}/dashboard/campaigns/"
            f"{self._campaign_id}/targets"
        )
        self._page.goto(url, wait_until="networkidle")

    def list_rewards(self) -> list[ExistingReward]:
        self.open()
        self._navigate_to_rewards()
        rewards: list[ExistingReward] = []
        rows = self._page.query_selector_all(SELECTOR_REWARD_LIST_ROW)
        for row in rows:
            name_el = row.query_selector(SELECTOR_REWARD_LIST_ROW_NAME)
            amount_el = row.query_selector(SELECTOR_REWARD_LIST_ROW_AMOUNT)
            id_el = row.query_selector(SELECTOR_REWARD_LIST_ROW_ID)
            name = name_el.inner_text().strip() if name_el else ""
            amount_cents: Optional[int] = None
            if amount_el is not None:
                raw = amount_el.inner_text().strip()
                amount_cents = _parse_amount_cents(raw)
            reward_id = id_el.get_attribute("data-reward-id") if id_el else None
            rewards.append(ExistingReward(
                name=name,
                amount_cents=amount_cents,
                reward_id=reward_id,
            ))
        return rewards

    def create_reward(self, req: CreateRewardRequest) -> str:
        self.open()
        self._navigate_to_rewards()
        self._page.click(SELECTOR_CREATE_REWARD_BUTTON)
        self._page.fill(SELECTOR_REWARD_NAME_INPUT, req.name)
        self._page.fill(SELECTOR_REWARD_AMOUNT_INPUT, str(_format_amount(req.amount_cents)))
        if req.description:
            self._page.fill(SELECTOR_REWARD_DESCRIPTION_INPUT, req.description)
        self._page.click(SELECTOR_REWARD_SAVE_BUTTON)
        self._page.wait_for_load_state("networkidle")
        new_row = self._page.query_selector(
            f'{SELECTOR_REWARD_LIST_ROW}:has-text("{_css_escape(req.name)}")'
        )
        if new_row is None:
            raise TiltifySessionError(
                f"Reward '{req.name}' did not appear in the rewards list after save."
            )
        id_el = new_row.query_selector(SELECTOR_REWARD_LIST_ROW_ID)
        reward_id = (
            id_el.get_attribute("data-reward-id")
            if id_el is not None
            else f"unknown:{req.name}"
        )
        return reward_id or f"unknown:{req.name}"

    def create_poll(self, req: CreatePollRequest) -> str:
        if not req.options:
            raise ValueError("Poll creation requires at least one option.")
        self.open()
        self._navigate_to_polls()
        self._page.click(SELECTOR_CREATE_POLL_BUTTON)
        self._page.fill(SELECTOR_POLL_NAME_INPUT, req.name)
        for i, option_text in enumerate(req.options):
            selector = SELECTOR_POLL_OPTION_INPUT_TEMPLATE.format(i=i)
            self._page.fill(selector, option_text)
        self._page.click(SELECTOR_POLL_SAVE_BUTTON)
        self._page.wait_for_load_state("networkidle")
        return f"poll:{req.name}"

    def create_target(self, req: CreateTargetRequest) -> str:
        self.open()
        self._navigate_to_targets()
        self._page.click(SELECTOR_CREATE_TARGET_BUTTON)
        self._page.fill(SELECTOR_TARGET_NAME_INPUT, req.name)
        self._page.fill(SELECTOR_TARGET_AMOUNT_INPUT, str(_format_amount(req.amount_cents)))
        self._page.click(SELECTOR_TARGET_SAVE_BUTTON)
        self._page.wait_for_load_state("networkidle")
        return f"target:{req.name}"


def _parse_amount_cents(raw: str) -> Optional[int]:
    import re
    m = re.search(r"(\d+(?:[.,]\d{1,2})?)", raw.replace(",", ""))
    if not m:
        return None
    dollars, _, cents = m.group(1).partition(".")
    cents = (cents + "00")[:2]
    return int(dollars) * 100 + int(cents)


def _format_amount(amount_cents: int) -> str:
    dollars, cents = divmod(amount_cents, 100)
    return f"{dollars}.{cents:02d}"


def _css_escape(text: str) -> str:
    """Escape a literal string for use inside a CSS attribute selector."""
    return text.replace('"', '\\"').replace("\\", "\\\\")


class StubTiltifyClient:
    """In-memory TiltifyClient for unit tests.

    Records every call into `calls` and returns the ID it assigned when
    the call was made. Implementations can pre-seed `existing_rewards`
    to exercise the idempotency check.
    """

    def __init__(self, existing_rewards: Optional[list[ExistingReward]] = None):
        self.existing_rewards = existing_rewards or []
        self.calls: list[tuple] = []
        self._next_id = 1

    def list_rewards(self) -> list[ExistingReward]:
        return list(self.existing_rewards)

    def create_reward(self, req: CreateRewardRequest) -> str:
        rid = f"r{self._next_id}"
        self._next_id += 1
        self.calls.append(("create_reward", req))
        return rid

    def create_poll(self, req: CreatePollRequest) -> str:
        rid = f"p{self._next_id}"
        self._next_id += 1
        self.calls.append(("create_poll", req))
        return rid

    def create_target(self, req: CreateTargetRequest) -> str:
        rid = f"t{self._next_id}"
        self._next_id += 1
        self.calls.append(("create_target", req))
        return rid

    def close(self) -> None:
        pass


def iter_session_files(session_paths: Iterable[str]) -> Optional[TiltifySession]:
    """Try each candidate storage_state path; return the first that loads."""
    for path in session_paths:
        if not path:
            continue
        try:
            return TiltifySession.from_storage_state(path)
        except TiltifySessionError:
            continue
    return None


def parse_cookie_header_as_storage_state(header: str) -> dict:
    """Public helper: same as TiltifySession.from_cookie_header(header)
    but returns the raw storage_state dict. Used by tests.
    """
    return TiltifySession.from_cookie_header(header).storage_state