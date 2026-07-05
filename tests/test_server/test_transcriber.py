"""Tests for vtext_server.transcriber."""
import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from vtext_server.errors import DependencyError, TranscriptionError
from vtext_server.transcriber import transcribe, _check_binary, _parse_output


class TestCheckBinary:
    def test_found_in_path(self):
        with patch("shutil.which", return_value="/usr/bin/whisper-cli"):
            _check_binary("whisper-cli")  # should not raise

    def test_found_as_file(self, tmp_path):
        binary = tmp_path / "whisper-cli"
        binary.touch()
        _check_binary(str(binary))  # should not raise

    def test_not_found_raises(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(DependencyError, match="whisper.cpp binary not found"):
                _check_binary("/nonexistent/whisper-cli")


class TestParseOutput:
    def test_valid_output(self, tmp_path):
        data = {
            "transcription": [
                {"offsets": {"from": 0, "to": 1500}, "text": " Hello"},
                {"offsets": {"from": 1500, "to": 3000}, "text": " world"},
            ],
            "result": {"language": "en"},
        }
        json_file = tmp_path / "output.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        result = _parse_output(json_file, source="test.wav")

        assert result.language == "en"
        assert result.source == "test.wav"
        assert len(result.segments) == 2
        assert result.segments[0].start == 0.0
        assert result.segments[0].end == 1.5
        assert result.segments[1].start == 1.5
        assert result.duration == 3.0
        assert not json_file.exists()  # cleaned up

    def test_empty_transcription(self, tmp_path):
        data = {"transcription": [], "result": {"language": "en"}}
        json_file = tmp_path / "output.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        result = _parse_output(json_file, source="test.wav")
        assert result.segments == []
        assert result.duration == 0.0

    def test_invalid_json_raises(self, tmp_path):
        json_file = tmp_path / "output.json"
        json_file.write_text("not json", encoding="utf-8")

        with pytest.raises(TranscriptionError, match="Failed to parse"):
            _parse_output(json_file, source="test.wav")

    def test_cleanup_on_parse_error(self, tmp_path):
        json_file = tmp_path / "output.json"
        json_file.write_text("bad json", encoding="utf-8")
        with pytest.raises(TranscriptionError):
            _parse_output(json_file, source="test.wav")
        assert not json_file.exists()  # still cleaned up


def _make_fake_popen(json_content: str, returncode: int = 0, stderr_lines: list[str] | None = None):
    """Build a mock Popen that writes the output JSON and streams stderr lines."""
    import io

    def _side_effect(cmd, **kwargs):
        # Write output JSON that whisper.cpp would produce
        for i, arg in enumerate(cmd):
            if arg == "--output-file" and i + 1 < len(cmd):
                out_path = Path(cmd[i + 1] + ".json")
                out_path.write_text(json_content, encoding="utf-8")
                break

        mock_proc = MagicMock()
        mock_proc.returncode = returncode
        mock_proc.stdout = io.StringIO("")
        mock_proc.stderr = io.StringIO("\n".join(stderr_lines or []))
        mock_proc.wait.return_value = returncode
        return mock_proc

    return _side_effect


class TestTranscribe:
    def _make_json_data(self):
        return json.dumps({
            "transcription": [
                {"offsets": {"from": 0, "to": 2000}, "text": " Test"},
            ],
            "result": {"language": "en"},
        })

    def test_success(self, tmp_path):
        wav = tmp_path / "audio.wav"
        wav.touch()
        model = tmp_path / "model.bin"
        model.touch()

        with patch("shutil.which", return_value="/usr/bin/whisper-cli"):
            with patch("subprocess.Popen", side_effect=_make_fake_popen(self._make_json_data())):
                result = transcribe(wav, "whisper-cli", model, language="en", threads=2)

        assert result.language == "en"
        assert len(result.segments) == 1

    def test_defaults_to_auto_language(self, tmp_path):
        """When no language is given, whisper must receive --language auto."""
        wav = tmp_path / "audio.wav"
        wav.touch()
        model = tmp_path / "model.bin"
        model.touch()

        captured_cmd = []

        def fake_popen(cmd, **kwargs):
            captured_cmd.extend(cmd)
            return _make_fake_popen(self._make_json_data())(cmd, **kwargs)

        with patch("shutil.which", return_value="/usr/bin/whisper-cli"):
            with patch("subprocess.Popen", side_effect=fake_popen):
                transcribe(wav, "whisper-cli", model, language=None, threads=2)

        assert "--language" in captured_cmd
        lang_idx = captured_cmd.index("--language")
        assert captured_cmd[lang_idx + 1] == "auto"

    def test_explicit_language_passed_through(self, tmp_path):
        """An explicit language code must be passed verbatim to whisper."""
        wav = tmp_path / "audio.wav"
        wav.touch()
        model = tmp_path / "model.bin"
        model.touch()

        captured_cmd = []

        def fake_popen(cmd, **kwargs):
            captured_cmd.extend(cmd)
            return _make_fake_popen(self._make_json_data())(cmd, **kwargs)

        with patch("shutil.which", return_value="/usr/bin/whisper-cli"):
            with patch("subprocess.Popen", side_effect=fake_popen):
                transcribe(wav, "whisper-cli", model, language="zh", threads=2)

        assert "--language" in captured_cmd
        lang_idx = captured_cmd.index("--language")
        assert captured_cmd[lang_idx + 1] == "zh"

    def test_progress_callback_called(self, tmp_path):
        """progress_callback receives parsed percentages from stderr."""
        wav = tmp_path / "audio.wav"
        wav.touch()
        model = tmp_path / "model.bin"
        model.touch()

        stderr = [
            "whisper_print_progress_callback: progress =  25%",
            "whisper_print_progress_callback: progress =  50%",
            "whisper_print_progress_callback: progress = 100%",
        ]
        received = []

        with patch("shutil.which", return_value="/usr/bin/whisper-cli"):
            with patch("subprocess.Popen",
                       side_effect=_make_fake_popen(self._make_json_data(), stderr_lines=stderr)):
                transcribe(wav, "whisper-cli", model, progress_callback=received.append)

        assert received == [25, 50, 100]

    def test_binary_not_found_raises(self, tmp_path):
        wav = tmp_path / "audio.wav"
        wav.touch()
        model = tmp_path / "model.bin"
        model.touch()

        with patch("shutil.which", return_value=None):
            with pytest.raises(DependencyError):
                transcribe(wav, "/no/such/binary", model)

    def test_nonzero_returncode_raises(self, tmp_path):
        wav = tmp_path / "audio.wav"
        wav.touch()
        model = tmp_path / "model.bin"
        model.touch()

        with patch("shutil.which", return_value="/usr/bin/whisper-cli"):
            with patch("subprocess.Popen",
                       side_effect=_make_fake_popen("{}", returncode=1)):
                with pytest.raises(TranscriptionError):
                    transcribe(wav, "whisper-cli", model)

    def test_timeout_raises(self, tmp_path):
        wav = tmp_path / "audio.wav"
        wav.touch()
        model = tmp_path / "model.bin"
        model.touch()

        import io
        mock_proc = MagicMock()
        mock_proc.stdout = io.StringIO("")
        mock_proc.stderr = io.StringIO("")
        mock_proc.wait.side_effect = subprocess.TimeoutExpired("cmd", 3600)

        with patch("shutil.which", return_value="/usr/bin/whisper-cli"):
            with patch("subprocess.Popen", return_value=mock_proc):
                with pytest.raises(TranscriptionError, match="timed out"):
                    transcribe(wav, "whisper-cli", model)
