import json

from real_time_captions.cli import main


def test_main_prints_deterministic_core_smoke_snapshot(capsys) -> None:
    assert main(['core-smoke']) == 0

    assert json.loads(capsys.readouterr().out) == {
        'session_id': 'core-smoke',
        'sequence': 2,
        'language': 'cs',
        'source_committed': 'Dobr\u00fd den',
        'source_provisional': '',
        'translation_committed': 'Dzie\u0144 dobry',
        'translation_provisional': '',
    }
