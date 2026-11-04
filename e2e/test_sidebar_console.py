"""The editor's sidebar and console in a real browser: what jsdom cannot lay out or reconnect."""
from __future__ import annotations

from conftest import open_file, set_text
from playwright.sync_api import Locator, Page, expect

LONG_OUTPUT = "for i in range(80):\n    print('line', i)\n"
SLOW_PROGRAM = "import time\nprint('started', flush=True)\ntime.sleep(4)\nprint('total', 6 * 7)\n"
LONG_NAME = "a_very_long_file_name_that_does_not_fit_in_the_sidebar_at_all_really.py"


def bottom_of(page: Page, selector: str) -> float:
    return page.evaluate("s => document.querySelector(s).getBoundingClientRect().bottom", selector)


def close_tab(tab: Locator) -> None:
    tab.hover()  # the close button only shows on hover
    tab.locator("button").click()


def test_the_last_console_line_is_not_cut_off(open_as, api):
    api.file("e2e_console_tail.py")
    alice = open_as("alice")
    open_file(alice, "e2e_console_tail.py")
    set_text(alice, LONG_OUTPUT)
    alice.get_by_role("button", name="Run", exact=True).click()
    expect(alice.locator(".run-out").last).to_contain_text("line 79")
    expect(alice.locator(".run-foot").last).to_contain_text("exit code 0")
    assert bottom_of(alice, ".console-runs") <= bottom_of(alice, ".bottom-panel")


def test_a_run_finishing_while_no_file_is_open_still_shows_as_finished(open_as, api):
    api.file("e2e_console_gap.py")
    alice, bob = open_as("alice"), open_as("bob")
    open_file(bob, "e2e_console_gap.py")
    set_text(bob, SLOW_PROGRAM)
    open_file(alice, "e2e_console_gap.py")
    for tab in alice.locator(".editor-tab").all()[::-1]:
        if "e2e_console_gap.py" not in tab.inner_text():
            close_tab(tab)

    bob.get_by_role("button", name="Run", exact=True).click()
    expect(alice.locator(".run-status").last).to_have_text("running")
    close_tab(alice.locator(".editor-tab"))  # the file's own socket closes
    expect(bob.locator(".run-status").last).to_have_text("completed", timeout=30_000)

    open_file(alice, "e2e_console_gap.py")
    expect(alice.locator(".run-status").last).to_have_text("completed")
    expect(alice.locator(".run-out").last).to_contain_text("total 42")


def test_selecting_a_folder_keeps_it_open_and_long_names_fit(open_as, api):
    pid = api.project_id()
    folders = api.call("GET", f"/projects/{pid}/folders")
    folder = next((f for f in folders if f["name"] == "e2e_folder"), None) \
        or api.call("POST", f"/projects/{pid}/folders", body={"name": "e2e_folder"})
    path = f"e2e_folder/{LONG_NAME}"
    if not any(f["path"] == path for f in api.call("GET", f"/projects/{pid}/files")):
        api.call("POST", f"/projects/{pid}/files", body={"path": path, "folder_id": folder["id"]})

    alice = open_as("alice")
    node = alice.locator(".file-node", has_text=LONG_NAME)
    alice.locator(".folder-name", has_text="e2e_folder").click()
    expect(alice.locator(".folder-header.active")).to_contain_text("e2e_folder")
    expect(node).to_be_visible()
    assert alice.evaluate("() => { const s = document.querySelector('.sidebar'); return s.scrollWidth <= s.clientWidth; }")

    alice.get_by_role("button", name="Collapse e2e_folder").click()
    expect(node).to_be_hidden()
