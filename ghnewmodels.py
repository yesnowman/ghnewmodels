#!/usr/bin/env python3
"""Report Copilot models that use the default policy, every hour at :15."""

from __future__ import annotations

import re
import requests
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import Locator, Page, TimeoutError, sync_playwright

TARGET_URL = f"https://github.com/enterprises/{sys.argv[1] if len(sys.argv) > 1 else ""}/ai-controls/copilot/models"
LOGIN_CHECK_INTERVAL_SECONDS = 2
PAGE_LOAD_TIMEOUT_MS = 60_000
SHOW_ALL_BUTTON_TIMEOUT_MS = 30_000
DEFAULT_POLICY = "Delegate to default policy"
SLACK_WEBHOOK_URL = sys.argv[2] if len(sys.argv) > 2 else "OFF"
DISCORD_WEBHOOK_URL = sys.argv[3] if len(sys.argv) > 3 else "OFF"


def notify_slack(txt):
    message = f"{txt}"
    payload = {"text": message}
    try:
        requests.post(SLACK_WEBHOOK_URL, json=payload)
    except Exception as e:
        print(f"Slack notification failed: {e}")
        

def notify_sd(txt):
    message = f"{txt}"
    if SLACK_WEBHOOK_URL != "OFF":
      rs = requests.post(SLACK_WEBHOOK_URL, json={"text": message})
      rs.raise_for_status()
    if DISCORD_WEBHOOK_URL != "OFF":
      rd = requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=10)
      rd.raise_for_status()


def next_check_time(now: datetime | None = None) -> datetime:
    """Return the next local-time hourly :15 mark."""
    current = now or datetime.now().astimezone()
    target = current.replace(minute=15, second=0, microsecond=0)
    if current >= target:
        target += timedelta(hours=1)
    return target


def wait_for_login_to_finish(page: Page) -> None:
    """Let the user sign in through the visible browser without collecting credentials."""
    if "login" not in page.url.lower():
        return

    print(
        "GitHub redirected to a login page. Sign in using the open browser window; "
        "the script will continue when GitHub leaves the login URL.",
        flush=True,
    )
    while "login" in page.url.lower():
        page.wait_for_timeout(LOGIN_CHECK_INTERVAL_SECONDS * 1000)


def show_all_models(page: Page) -> None:
    button = page.get_by_role(
        "button", name=re.compile(r"Show all\b.*\bmodels\b", re.IGNORECASE)
    )
    button.wait_for(state="visible", timeout=SHOW_ALL_BUTTON_TIMEOUT_MS)
    button.click()


def selected_policy_and_model_name(control: Locator) -> tuple[str, str]:
    details = control.evaluate(
        """element => {
            const selected = element.tagName === "SELECT"
                ? element.selectedOptions[0]?.textContent?.trim() ?? ""
                : (element.getAttribute("aria-valuetext")
                    || (element.tagName === "INPUT" ? element.value : element.innerText)
                    || element.getAttribute("aria-label")
                    || "").trim();

            const row = element.closest('[role="row"], tr, li, [data-testid*="model"]');
            const container = row || element.parentElement?.parentElement || element.parentElement;
            const semanticNames = Array.from(container?.querySelectorAll(
                'h1, h2, h3, h4, h5, h6, [data-testid*="model-name"], ' +
                '[data-testid*="modelName"], strong'
            ) ?? []).map(node => node.innerText?.trim()).filter(Boolean);
            const text = container?.innerText ?? "";
            return {
                selected,
                semanticNames,
                text,
                label: element.getAttribute("aria-label") || element.getAttribute("title") || ""
            };
        }"""
    )

    selected_value = details["selected"].strip()
    def clean_candidate(candidate: str) -> str:
        candidate = re.sub(
            re.escape(DEFAULT_POLICY), "", candidate, flags=re.IGNORECASE
        )
        candidate = re.sub(
            r"\b(?:copilot\s+)?model\s+policy\b|\bpolicy\b(?:\s+(?:for|of)\b)?",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        candidate = re.sub(r"\s+", " ", candidate).strip(" \t\r\n:;,-–—|")
        if not candidate or candidate.casefold() in {
            selected_value.casefold(),
            "model",
            "copilot",
        }:
            return ""
        return candidate

    model_name = next(
        (
            name
            for candidate in [*details["semanticNames"], details["label"]]
            if (name := clean_candidate(candidate))
        ),
        "",
    )
    if not model_name:
        model_name = next(
            (
                name
                for line in details["text"].splitlines()
                if (name := clean_candidate(line))
            ),
            "(model name unavailable)",
        )

    return selected_value, model_name


def default_policy_model_names(page: Page) -> list[str]:
    controls = page.locator(
        "select, [role='combobox'], button, [role='button'], [aria-haspopup]"
    )
    count = controls.count()
    if count == 0:
        raise RuntimeError("No visible model policy controls were found after expanding the list.")

    names: list[str] = []
    for index in range(count):
        control = controls.nth(index)
        if not control.is_visible():
            continue
        selected, model_name = selected_policy_and_model_name(control)
        if DEFAULT_POLICY.casefold() in selected.casefold():
            names.append(model_name)
    return list(dict.fromkeys(names))


def run_check(page: Page) -> None:
    page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
    wait_for_login_to_finish(page)
    show_all_models(page)
    model_names = default_policy_model_names(page)

    print(f"\nChecked at {datetime.now().astimezone().isoformat(timespec='seconds')}")
    if model_names:
        for name in model_names:
            print(name)
        notify_sd(", ".join(model_names))
    else:
        print("No models are set to Delegate to default policy.")
        notify_sd("No new models")
    sys.stdout.flush()


def main() -> int:
    profile_directory = Path.home() / ".newmodels-playwright"
    profile_directory.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_directory),
                headless=False,
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                print(f"Browser profile: {profile_directory}", flush=True)
                print("Running initial check now.", flush=True)
                try:
                    run_check(page)
                except TimeoutError as error:
                    print(f"Timed out while checking the models page: {error}", file=sys.stderr)
                except Exception as error:
                    print(f"Model check failed: {error}", file=sys.stderr)

                while True:
                    check_at = next_check_time()
                    print(
                        f"Next check: {check_at.isoformat(timespec='minutes')}",
                        flush=True,
                    )
                    while True:
                        remaining = (check_at - datetime.now().astimezone()).total_seconds()
                        if remaining <= 0:
                            break
                        time.sleep(min(remaining, 60))

                    try:
                        run_check(page)
                    except TimeoutError as error:
                        print(f"Timed out while checking the models page: {error}", file=sys.stderr)
                    except Exception as error:
                        print(f"Model check failed: {error}", file=sys.stderr)
            finally:
                context.close()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
        return 0
    except Exception as error:
        print(f"Could not start the Playwright browser: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
