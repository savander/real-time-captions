from real_time_captions.cli import main


def test_main_returns_success_for_core_smoke_command(capsys) -> None:
    assert main(["core-smoke"]) == 0
    assert capsys.readouterr().out.strip() == "portable core ready"
