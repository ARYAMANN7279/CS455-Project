"""The editor's sidebar and console in a real browser: what jsdom cannot lay out or reconnect."""
from __future__ import annotations

from conftest import APP, open_file, set_text
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


def drag(page: Page, handle: str, dx: float, dy: float) -> None:
    box = page.get_by_role("separator", name=handle).bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y + dy, steps=5)
    page.mouse.up()


def size_of(page: Page, selector: str) -> dict:
    return page.locator(selector).first.bounding_box()


def test_the_console_and_both_sidebars_can_be_dragged_and_the_editor_follows(open_as, api):
    api.file("e2e_resize.py")
    alice = open_as("alice")
    open_file(alice, "e2e_resize.py")
    assistant = "aside:not(.sidebar)"
    editor = size_of(alice, ".monaco-editor")
    panel, left, right = size_of(alice, ".bottom-panel"), size_of(alice, ".sidebar"), size_of(alice, assistant)

    drag(alice, "Resize the console", 0, -120)
    drag(alice, "Resize the sidebar", 80, 0)
    drag(alice, "Resize the assistant panel", -60, 0)

    assert size_of(alice, ".bottom-panel")["height"] == panel["height"] + 120
    assert bottom_of(alice, ".bottom-panel") <= alice.viewport_size["height"]  # grew up, not off screen
    assert size_of(alice, ".sidebar")["width"] == left["width"] + 80
    assert size_of(alice, assistant)["width"] == right["width"] + 60
    resized = size_of(alice, ".monaco-editor")  # Monaco lays itself out again
    assert resized["height"] == editor["height"] - 120
    assert resized["width"] == editor["width"] - 140

    alice.reload()
    alice.wait_for_selector(".monaco-editor", timeout=90_000)
    assert size_of(alice, ".sidebar")["width"] == left["width"] + 80


def test_only_the_creator_sees_add_member_on_the_dashboard(open_as):
    alice, bob = open_as("alice"), open_as("bob")
    for page in (alice, bob):
        page.goto(f"{APP}/")
    expect(alice.get_by_text("Add Member:").first).to_be_visible()
    expect(bob.locator(".project-card").first).to_be_visible()
    expect(bob.get_by_text("Add Member:")).to_have_count(0)


def test_a_member_with_the_owner_role_can_add_the_api_key(open_as, api):
    projects = api.call("GET", "/projects")
    pid = next((p["id"] for p in projects if p["name"] == "e2e co-owner"), None) \
        or api.call("POST", "/projects", body={"name": "e2e co-owner"})["id"]
    if not api.call("GET", f"/projects/{pid}/files"):
        api.call("POST", f"/projects/{pid}/files", body={"path": "e2e_co_owner.py"})
        api.call("POST", f"/projects/{pid}/members", body={"user_id": "bob", "role": "owner"})
        api.call("POST", f"/projects/{pid}/members", body={"user_id": "carol", "role": "editor"})

    bob, carol = open_as("bob"), open_as("carol")
    for page in (bob, carol):
        page.goto(f"{APP}/projects/{pid}")
        page.wait_for_selector(".monaco-editor", timeout=90_000)
    expect(bob.get_by_label("Mistral API key")).to_be_visible()
    expect(carol.get_by_text("Ask the project owner to add an API key.")).to_be_visible()
    expect(carol.get_by_label("Mistral API key")).to_have_count(0)
