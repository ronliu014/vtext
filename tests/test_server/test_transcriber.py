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

        json_content = self._make_json_data()

        def fake_run(cmd, **kwargs):
            # Write the output JSON that whisper.cpp would produce
            # whisper.cpp writes to <output_file>.json
            for i, arg in enumerate(cmd):
                if arg == "--output-file" and i + 1 < len(cmd):
                    out_path = Path(cmd[i + 1] + ".json")
                    out_path.write_text(json_content, encoding="utf-8")
                    break
            mock = MagicMock()
            mock.returncode = 0
            return mock

        with patch("shutil.which", return_value="/usr/bin/whisper-cli"):
            with patch("subprocess.run", side_effect=fake_run):
                result = transcribe(wav, "whisper-cli", model, language="en", threads=2)

        assert result.language == "en"
        assert len(result.segments) == 1

    def test_defaults_to_auto_language(self, tmp_path):
        """When no language is given, whisper must receive --language auto,
        otherwise whisper.cpp defaults to English."""
        wav = tmp_path / "audio.wav"
        wav.touch()
        model = tmp_path / "model.bin"
        model.touch()

        json_content = self._make_json_data()
        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            for i, arg in enumerate(cmd):
                if arg == "--output-file" and i + 1 < len(cmd):
                    out_path = Path(cmd[i + 1] + ".json")
                    out_path.write_text(json_content, encoding="utf-8")
                    break
            mock = MagicMock()
            mock.returncode = 0
            return mock

        with patch("shutil.which", return_value="/usr/bin/whisper-cli"):
            with patch("subprocess.run", side_effect=fake_run):
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

        json_content = self._make_json_data()
        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            for i, arg in enumerate(cmd):
                if arg == "--output-file" and i + 1 < len(cmd):
                    out_path = Path(cmd[i + 1] + ".json")
                    out_path.write_text(json_content, encoding="utf-8")
                    break
            mock = MagicMock()
            mock.returncode = 0
            return mock

        with patch("shutil.which", return_value="/usr/bin/whisper-cli"):
            with patch("subprocess.run", side_effect=fake_run):
                transcribe(wav, "whisper-cli", model, language="zh", threads=2)

        assert "--language" in captured_cmd
        lang_idx = captured_cmd.index("--language")
        assert captured_cmd[lang_idx + 1] == "zh"

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

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error output"

        with patch("shutil.which", return_value="/usr/bin/whisper-cli"):
            with patch("subprocess.run", return_value=mock_result):
                with pytest.raises(TranscriptionError):
                    transcribe(wav, "whisper-cli", model)

    def test_timeout_raises(self, tmp_path):
        wav = tmp_path / "audio.wav"
        wav.touch()
        model = tmp_path / "model.bin"
        model.touch()

        with patch("shutil.which", return_value="/usr/bin/whisper-cli"):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 3600)):
                with pytest.raises(TranscriptionError, match="timed out"):
                    transcribe(wav, "whisper-cli", model)
