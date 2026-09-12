from pathlib import Path
from types import SimpleNamespace


def test_desktop_self_test_uses_canonical_surface_without_gui(monkeypatch):
    import aqorath.desktop_entrypoint as desktop

    calls = []
    monkeypatch.setattr(desktop, "bootstrap_local_product", lambda: calls.append("bootstrap"))
    monkeypatch.setattr(
        desktop,
        "load_local_app",
        lambda: SimpleNamespace(title="Aqorath Local Surface"),
    )

    assert desktop.main(["--self-test"]) == 0
    assert calls == ["bootstrap"]


def test_desktop_version_path_does_not_bootstrap(monkeypatch, capsys):
    import aqorath.desktop_entrypoint as desktop

    monkeypatch.setattr(
        desktop,
        "bootstrap_local_product",
        lambda: (_ for _ in ()).throw(AssertionError("version must not bootstrap")),
    )

    assert desktop.main(["--version"]) == 0
    assert desktop.__version__ in capsys.readouterr().out


def test_local_server_materializes_the_canonical_app():
    from aqorath.local_server import load_local_app
    from aqorath.web_surface import app as canonical_app

    assert load_local_app() is canonical_app


def test_windows_installer_is_per_user_and_double_click_oriented():
    source = (Path(__file__).resolve().parents[1] / "packaging" / "windows" / "Aqorath.iss").read_text()

    assert "PrivilegesRequired=lowest" in source
    assert "DefaultDirName={localappdata}\\Programs\\Aqorath" in source
    assert 'Filename: "{app}\\{#MyAppExeName}"' in source
    assert 'Description: "Abrir Aqorath"' in source
    assert "postinstall" in source
