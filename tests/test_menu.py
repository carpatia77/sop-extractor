import os

from menu import (
    Capability,
    find_capability,
    is_available,
    build_command,
    format_menu,
    dispatch,
    run_interactive,
    CAPABILITIES,
)


def _fake_registry(tmp_path, coming_soon=False, info_only=False, missing_script=False):
    if not missing_script and not info_only:
        (tmp_path / "fake_script.py").write_text("print('ran')\n", encoding="utf-8")
    return [
        Capability("1", "fake", "Fake capability", None if info_only else "fake_script.py",
                   "<arg>", coming_soon, info_only, "info text here" if info_only else None),
    ]


def test_find_capability_by_key_and_verb():
    caps = _fake_registry_static()
    assert find_capability("1", caps) is caps[0]
    assert find_capability("fake", caps) is caps[0]
    assert find_capability("nope", caps) is None


def _fake_registry_static():
    return [Capability("1", "fake", "Fake", "fake_script.py", "<arg>", False, False, None)]


def test_is_available_true_when_script_exists(tmp_path):
    caps = _fake_registry(tmp_path)
    ok, reason = is_available(caps[0], str(tmp_path))
    assert ok
    assert reason == ""


def test_is_available_false_when_script_missing(tmp_path):
    caps = _fake_registry(tmp_path, missing_script=True)
    ok, reason = is_available(caps[0], str(tmp_path))
    assert not ok
    assert "not found" in reason


def test_is_available_false_when_coming_soon(tmp_path):
    caps = _fake_registry(tmp_path, coming_soon=True)
    ok, reason = is_available(caps[0], str(tmp_path))
    assert not ok
    assert "coming soon" in reason


def test_is_available_true_for_info_only_capability(tmp_path):
    caps = _fake_registry(tmp_path, info_only=True)
    ok, reason = is_available(caps[0], str(tmp_path))
    assert ok


def test_build_command_matches_manual_invocation(tmp_path):
    caps = _fake_registry(tmp_path)
    cmd = build_command(caps[0], ["arg1", "--flag"], str(tmp_path), python_bin="python3")
    assert cmd == ["python3", os.path.join(str(tmp_path), "fake_script.py"), "arg1", "--flag"]


def test_format_menu_greys_out_unavailable_with_reason(tmp_path):
    caps = _fake_registry(tmp_path, missing_script=True)
    menu = format_menu(caps, str(tmp_path))
    assert "unavailable" in menu
    assert "not found" in menu


def test_format_menu_shows_available_cleanly(tmp_path):
    caps = _fake_registry(tmp_path)
    menu = format_menu(caps, str(tmp_path))
    assert "Fake capability" in menu
    assert "unavailable" not in menu


def test_dispatch_runs_available_script(tmp_path, capfd):
    caps = _fake_registry(tmp_path)
    code = dispatch(caps[0], [], str(tmp_path))
    assert code == 0
    out = capfd.readouterr().out
    assert "ran" in out


def test_dispatch_refuses_unavailable_capability(tmp_path, capsys):
    caps = _fake_registry(tmp_path, coming_soon=True)
    code = dispatch(caps[0], [], str(tmp_path))
    assert code == 1
    out = capsys.readouterr().out
    assert "unavailable" in out


def test_dispatch_prints_info_text_for_info_only(tmp_path, capsys):
    caps = _fake_registry(tmp_path, info_only=True)
    code = dispatch(caps[0], [], str(tmp_path))
    assert code == 0
    out = capsys.readouterr().out
    assert "info text here" in out


def test_run_interactive_quits_on_q(tmp_path, capsys):
    caps = _fake_registry(tmp_path)
    inputs = iter(["q"])
    code = run_interactive(caps, str(tmp_path), input_fn=lambda _: next(inputs))
    assert code == 0


def test_run_interactive_dispatches_then_quits(tmp_path, capfd):
    caps = _fake_registry(tmp_path)
    inputs = iter(["1", "", "q"])
    code = run_interactive(caps, str(tmp_path), input_fn=lambda _: next(inputs))
    assert code == 0
    out = capfd.readouterr().out
    assert "ran" in out


def test_real_capability_registry_scan_is_available():
    """The real menu (not a fake registry): 'scan' must resolve to the actual
    preflight_scan.py file in scripts/, proving the default SCRIPTS_DIR wiring
    is correct, not just the pure dispatch logic."""
    cap = find_capability("scan", CAPABILITIES)
    assert cap is not None
    ok, reason = is_available(cap)
    assert ok, reason


def test_real_capability_registry_view_wires_to_render_skill_viewer():
    """'view' must dispatch to render_skill_viewer.py (Item 13.4), proving
    the menu and the HTML viewer are wired together as speced."""
    cap = find_capability("view", CAPABILITIES)
    assert cap is not None
    assert cap.script == "render_skill_viewer.py"


def test_headless_scan_command_matches_manual_invocation():
    """sopx scan <path> must be byte-identical to `python scripts/preflight_scan.py <path>`."""
    cap = find_capability("scan", CAPABILITIES)
    cmd = build_command(cap, ["/tmp/book.pdf", "--emit-prompt"], python_bin="python3")
    assert cmd[0] == "python3"
    assert cmd[1].endswith("preflight_scan.py")
    assert cmd[2:] == ["/tmp/book.pdf", "--emit-prompt"]
