from unittest.mock import patch

from immersion_app.core import anki


def test_start_anki_if_needed_leaves_an_available_ankiconnect_alone():
    with (
        patch.object(anki, "_anki_connect_is_available", return_value=True),
        patch.object(anki, "_anki_process_is_running") as running,
        patch("immersion_app.core.anki.subprocess.Popen") as popen,
    ):
        assert anki.start_anki_if_needed() is False

    running.assert_not_called()
    popen.assert_not_called()


def test_start_anki_if_needed_does_not_launch_a_second_running_anki():
    with (
        patch.object(anki, "_anki_connect_is_available", return_value=False),
        patch.object(anki, "_anki_process_is_running", return_value=True),
        patch("immersion_app.core.anki.subprocess.Popen") as popen,
    ):
        assert anki.start_anki_if_needed() is False

    popen.assert_not_called()


def test_start_anki_if_needed_launches_and_waits_for_ankiconnect():
    with (
        patch.object(anki, "_anki_connect_is_available", side_effect=[False, True]),
        patch.object(anki, "_anki_process_is_running", return_value=False),
        patch.object(anki, "_find_anki_executable", return_value="C:/Program Files/Anki/anki.exe"),
        patch("immersion_app.core.anki.subprocess.Popen") as popen,
    ):
        assert anki.start_anki_if_needed() is True

    popen.assert_called_once_with(
        ["C:/Program Files/Anki/anki.exe"],
        stdout=anki.subprocess.DEVNULL,
        stderr=anki.subprocess.DEVNULL,
    )
