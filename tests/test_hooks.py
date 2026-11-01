#!/usr/bin/env python3
"""Unit tests for prompt-efficiency-analyzer hooks."""

import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Ensure hooks/ is on sys.path so sibling imports resolve
_HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "hooks")
sys.path.insert(0, os.path.abspath(_HOOKS_DIR))

import utils  # noqa: E402
import analyze_efficiency as ae  # noqa: E402


class TestStripFence(unittest.TestCase):
    def test_no_fence_returned_unchanged(self):
        self.assertEqual(utils.strip_fence('{"a": 1}'), '{"a": 1}')

    def test_json_fence_stripped(self):
        text = "```json\n{\"a\": 1}\n```"
        self.assertEqual(utils.strip_fence(text), '{"a": 1}')

    def test_plain_fence_stripped(self):
        text = "```\n{\"a\": 1}\n```"
        self.assertEqual(utils.strip_fence(text), '{"a": 1}')

    def test_fence_without_closing_strips_opening(self):
        text = "```json\n{\"a\": 1}"
        self.assertEqual(utils.strip_fence(text), '{"a": 1}')

    def test_empty_string(self):
        self.assertEqual(utils.strip_fence(""), "")

    def test_multiline_body_preserved(self):
        text = "```\nline1\nline2\nline3\n```"
        self.assertEqual(utils.strip_fence(text), "line1\nline2\nline3")


class TestBuildWarningMessage(unittest.TestCase):
    def test_empty_signals_returns_none(self):
        self.assertIsNone(ae.build_warning_message({"signals": [], "token_risk": "low"}))

    def test_no_signals_key_returns_none(self):
        self.assertIsNone(ae.build_warning_message({"token_risk": "low"}))

    def test_only_low_signals_returns_none(self):
        analysis = {
            "signals": [{"type": "padding", "severity": "low", "explanation": "x", "suggested_fix": "y"}],
            "token_risk": "low",
        }
        self.assertIsNone(ae.build_warning_message(analysis))

    def test_only_medium_signals_returns_none(self):
        analysis = {
            "signals": [{"type": "padding", "severity": "medium", "explanation": "x", "suggested_fix": "y"}],
            "token_risk": "medium",
        }
        self.assertIsNone(ae.build_warning_message(analysis))

    def test_high_signal_returns_warning(self):
        analysis = {
            "signals": [{
                "type": "vague_scope",
                "severity": "high",
                "explanation": "Too vague.",
                "suggested_fix": "Be specific.",
            }],
            "token_risk": "high",
        }
        msg = ae.build_warning_message(analysis)
        self.assertIsNotNone(msg)
        self.assertIn("vague_scope", msg)
        self.assertIn("Too vague.", msg)
        self.assertIn("Be specific.", msg)
        self.assertIn("token_risk: high", msg)

    def test_only_high_signals_included_in_output(self):
        analysis = {
            "signals": [
                {"type": "padding", "severity": "low", "explanation": "low signal", "suggested_fix": "remove"},
                {"type": "vague_scope", "severity": "high", "explanation": "high signal", "suggested_fix": "fix it"},
            ],
            "token_risk": "high",
        }
        msg = ae.build_warning_message(analysis)
        self.assertIn("high signal", msg)
        self.assertNotIn("low signal", msg)

    def test_multiple_high_signals_all_appear(self):
        analysis = {
            "signals": [
                {"type": "vague_scope", "severity": "high", "explanation": "sig1", "suggested_fix": "fix1"},
                {"type": "missing_context", "severity": "high", "explanation": "sig2", "suggested_fix": "fix2"},
            ],
            "token_risk": "high",
        }
        msg = ae.build_warning_message(analysis)
        self.assertIn("sig1", msg)
        self.assertIn("sig2", msg)

    def test_missing_token_risk_uses_unknown(self):
        analysis = {
            "signals": [{"type": "vague_scope", "severity": "high", "explanation": "e", "suggested_fix": "f"}],
        }
        msg = ae.build_warning_message(analysis)
        self.assertIn("token_risk: unknown", msg)

    def test_signal_without_suggested_fix(self):
        analysis = {
            "signals": [{"type": "vague_scope", "severity": "high", "explanation": "vague"}],
            "token_risk": "high",
        }
        msg = ae.build_warning_message(analysis)
        self.assertIn("vague", msg)


# ---------------------------------------------------------------------------
# LLM backend (_analyze_with_llm)
# ---------------------------------------------------------------------------

class TestAnalyzeWithLlm(unittest.TestCase):
    _GOOD_ANALYSIS = {
        "signals": [],
        "overall_efficiency": "good",
        "token_risk": "low",
    }

    def _mock_run(self, stdout, returncode=0):
        mock = MagicMock()
        mock.returncode = returncode
        mock.stdout = stdout
        return mock

    @patch("analyze_efficiency.subprocess.run")
    def test_returns_parsed_dict_on_success(self, mock_run):
        mock_run.return_value = self._mock_run(json.dumps(self._GOOD_ANALYSIS))
        result = ae._analyze_with_llm("fix my code")
        self.assertEqual(result, self._GOOD_ANALYSIS)

    @patch("analyze_efficiency.subprocess.run")
    def test_returns_none_on_nonzero_exit(self, mock_run):
        mock_run.return_value = self._mock_run("", returncode=1)
        self.assertIsNone(ae._analyze_with_llm("fix my code"))

    @patch("analyze_efficiency.subprocess.run")
    def test_returns_none_on_invalid_json(self, mock_run):
        mock_run.return_value = self._mock_run("not json at all")
        self.assertIsNone(ae._analyze_with_llm("fix my code"))

    @patch("analyze_efficiency.subprocess.run")
    def test_strips_fence_before_parsing(self, mock_run):
        fenced = "```json\n" + json.dumps(self._GOOD_ANALYSIS) + "\n```"
        mock_run.return_value = self._mock_run(fenced)
        result = ae._analyze_with_llm("fix my code")
        self.assertEqual(result, self._GOOD_ANALYSIS)

    @patch("analyze_efficiency.subprocess.run", side_effect=Exception("boom"))
    def test_returns_none_on_exception(self, _mock_run):
        self.assertIsNone(ae._analyze_with_llm("fix my code"))

    @patch("analyze_efficiency.subprocess.run")
    def test_sets_sentinel_env_var(self, mock_run):
        captured_env = {}

        def capture(cmd, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            return self._mock_run(json.dumps(self._GOOD_ANALYSIS))

        mock_run.side_effect = capture
        ae._analyze_with_llm("hello")
        self.assertEqual(captured_env.get(ae._SENTINEL_ENV), "1")


# ---------------------------------------------------------------------------
# Rules backend (_analyze_with_rules)
# ---------------------------------------------------------------------------

class TestAnalyzeWithRules(unittest.TestCase):
    def test_returns_dict_always(self):
        result = ae._analyze_with_rules("look at my code and fix stuff")
        self.assertIsInstance(result, dict)
        self.assertIn("signals", result)
        self.assertIn("overall_efficiency", result)
        self.assertIn("token_risk", result)

    def test_vague_prompt_has_signals(self):
        result = ae._analyze_with_rules("look at my code and fix stuff")
        self.assertTrue(len(result["signals"]) > 0)

    def test_clean_prompt_has_no_signals(self):
        result = ae._analyze_with_rules("Add a docstring to the parse_args function in cli.py")
        self.assertEqual(result["signals"], [])
        self.assertEqual(result["overall_efficiency"], "good")

    def test_returns_safe_dict_on_internal_error(self):
        with patch("analyze_efficiency.run_rules", side_effect=RuntimeError("boom")):
            result = ae._analyze_with_rules("any prompt")
        self.assertEqual(result["signals"], [])
        self.assertEqual(result["token_risk"], "low")


# ---------------------------------------------------------------------------
# Dispatch (analyze_efficiency)
# ---------------------------------------------------------------------------

class TestAnalyzeEfficiencyDispatch(unittest.TestCase):
    @patch("analyze_efficiency._get_analyzer", return_value="llm")
    @patch("analyze_efficiency._analyze_with_llm", return_value={"signals": [], "overall_efficiency": "good", "token_risk": "low"})
    def test_dispatches_to_llm_when_configured(self, mock_llm, _get):
        ae.analyze_efficiency("hello")
        mock_llm.assert_called_once_with("hello")

    @patch("analyze_efficiency._get_analyzer", return_value="rules")
    @patch("analyze_efficiency._analyze_with_rules", return_value={"signals": [], "overall_efficiency": "good", "token_risk": "low"})
    def test_dispatches_to_rules_when_configured(self, mock_rules, _get):
        ae.analyze_efficiency("hello")
        mock_rules.assert_called_once_with("hello")

    @patch("analyze_efficiency._get_analyzer", return_value="rules")
    def test_rules_path_never_returns_none(self, _get):
        result = ae.analyze_efficiency("look at my code and fix stuff")
        self.assertIsNotNone(result)

    @patch("analyze_efficiency._get_analyzer", return_value="llm")
    @patch("analyze_efficiency._analyze_with_llm", return_value=None)
    def test_llm_path_can_return_none(self, _llm, _get):
        self.assertIsNone(ae.analyze_efficiency("hello"))


# ---------------------------------------------------------------------------
# _get_analyzer
# ---------------------------------------------------------------------------

class TestGetAnalyzer(unittest.TestCase):
    def _write_config(self, tmpdir, data):
        path = os.path.join(tmpdir, "config.json")
        with open(path, "w") as fh:
            json.dump(data, fh)
        return tmpdir

    def test_env_var_llm_wins(self):
        with patch.dict(os.environ, {ae._ANALYZER_ENV: "llm", "CLAUDE_PLUGIN_ROOT": ""}):
            self.assertEqual(ae._get_analyzer(), "llm")

    def test_env_var_rules_wins(self):
        with patch.dict(os.environ, {ae._ANALYZER_ENV: "rules", "CLAUDE_PLUGIN_ROOT": ""}):
            self.assertEqual(ae._get_analyzer(), "rules")

    def test_env_var_case_insensitive(self):
        with patch.dict(os.environ, {ae._ANALYZER_ENV: "LLM", "CLAUDE_PLUGIN_ROOT": ""}):
            self.assertEqual(ae._get_analyzer(), "llm")

    def test_invalid_env_falls_through_to_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_config(tmpdir, {"analyzer": "llm"})
            with patch.dict(os.environ, {ae._ANALYZER_ENV: "garbage", "CLAUDE_PLUGIN_ROOT": tmpdir}):
                self.assertEqual(ae._get_analyzer(), "llm")

    def test_config_file_llm(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_config(tmpdir, {"analyzer": "llm"})
            with patch.dict(os.environ, {ae._ANALYZER_ENV: "", "CLAUDE_PLUGIN_ROOT": tmpdir}):
                self.assertEqual(ae._get_analyzer(), "llm")

    def test_config_file_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_config(tmpdir, {"analyzer": "rules"})
            with patch.dict(os.environ, {ae._ANALYZER_ENV: "", "CLAUDE_PLUGIN_ROOT": tmpdir}):
                self.assertEqual(ae._get_analyzer(), "rules")

    def test_config_invalid_json_returns_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "config.json"), "w") as fh:
                fh.write("not json")
            with patch.dict(os.environ, {ae._ANALYZER_ENV: "", "CLAUDE_PLUGIN_ROOT": tmpdir}):
                self.assertEqual(ae._get_analyzer(), "rules")

    def test_config_unknown_value_returns_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_config(tmpdir, {"analyzer": "gpt"})
            with patch.dict(os.environ, {ae._ANALYZER_ENV: "", "CLAUDE_PLUGIN_ROOT": tmpdir}):
                self.assertEqual(ae._get_analyzer(), "rules")

    def test_missing_config_file_returns_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {ae._ANALYZER_ENV: "", "CLAUDE_PLUGIN_ROOT": tmpdir}):
                self.assertEqual(ae._get_analyzer(), "rules")

    def test_no_plugin_root_returns_default(self):
        env = {k: v for k, v in os.environ.items() if k not in (ae._ANALYZER_ENV, "CLAUDE_PLUGIN_ROOT")}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(ae._get_analyzer(), "rules")


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

class TestMain(unittest.TestCase):
    def _run_main(self, stdin_data: dict, env_extra: dict | None = None):
        stdin_json = json.dumps(stdin_data)
        env = {k: v for k, v in os.environ.items() if k != ae._SENTINEL_ENV}
        if env_extra:
            env.update(env_extra)
        with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(stdin_json.encode()))):
            with patch.dict(os.environ, env, clear=True):
                with patch("builtins.print") as mock_print:
                    with patch("analyze_efficiency.os.makedirs"):
                        with patch("builtins.open", unittest.mock.mock_open()):
                            try:
                                ae.main()
                            except SystemExit:
                                pass
                            return mock_print

    @patch.dict(os.environ, {"CLAUDE_EFFICIENCY_ANALYZING": "1"})
    def test_sentinel_env_exits_immediately(self):
        with self.assertRaises(SystemExit) as ctx:
            ae.main()
        self.assertEqual(ctx.exception.code, 0)

    def test_invalid_json_stdin_exits_cleanly(self):
        with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(b"not json"))):
            with self.assertRaises(SystemExit) as ctx:
                ae.main()
        self.assertEqual(ctx.exception.code, 0)

    def test_empty_prompt_exits_without_analysis(self):
        with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps({"session_id": "s", "prompt": "  "}).encode()))):
            with patch("analyze_efficiency.analyze_efficiency") as mock_analyze:
                with self.assertRaises(SystemExit):
                    ae.main()
                mock_analyze.assert_not_called()

    @patch("analyze_efficiency.analyze_efficiency")
    @patch("analyze_efficiency.os.makedirs")
    def test_high_signal_prints_system_message(self, _mkdirs, mock_analyze):
        mock_analyze.return_value = {
            "signals": [{"type": "vague_scope", "severity": "high", "explanation": "vague", "suggested_fix": "fix"}],
            "overall_efficiency": "poor",
            "token_risk": "high",
        }
        stdin = json.dumps({"session_id": "abc123", "prompt": "fix my stuff"}).encode()
        with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(stdin))):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop(ae._SENTINEL_ENV, None)
                with patch("builtins.print") as mock_print:
                    with patch("builtins.open", unittest.mock.mock_open()):
                        try:
                            ae.main()
                        except SystemExit:
                            pass
        mock_print.assert_called_once()
        output = json.loads(mock_print.call_args[0][0])
        self.assertIn("systemMessage", output)
        self.assertIn("vague_scope", output["systemMessage"])

    @patch("analyze_efficiency.analyze_efficiency")
    @patch("analyze_efficiency.os.makedirs")
    def test_no_high_signal_prints_nothing(self, _mkdirs, mock_analyze):
        mock_analyze.return_value = {
            "signals": [{"type": "padding", "severity": "low", "explanation": "filler", "suggested_fix": "trim"}],
            "overall_efficiency": "fair",
            "token_risk": "low",
        }
        stdin = json.dumps({"session_id": "abc", "prompt": "please carefully fix the bug"}).encode()
        with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(stdin))):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop(ae._SENTINEL_ENV, None)
                with patch("builtins.print") as mock_print:
                    with patch("builtins.open", unittest.mock.mock_open()):
                        try:
                            ae.main()
                        except SystemExit:
                            pass
        mock_print.assert_not_called()

    @patch("analyze_efficiency.analyze_efficiency", return_value=None)
    @patch("analyze_efficiency.os.makedirs")
    def test_none_analysis_prints_nothing(self, _mkdirs, _analyze):
        stdin = json.dumps({"session_id": "abc", "prompt": "hello"}).encode()
        with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(stdin))):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop(ae._SENTINEL_ENV, None)
                with patch("builtins.print") as mock_print:
                    with patch("builtins.open", unittest.mock.mock_open()):
                        try:
                            ae.main()
                        except SystemExit:
                            pass
        mock_print.assert_not_called()


class TestSessionIdSanitization(unittest.TestCase):
    """Verify path traversal is blocked in session_id handling."""

    @patch("analyze_efficiency.analyze_efficiency", return_value=None)
    @patch("analyze_efficiency.os.makedirs")
    def test_path_traversal_sanitized(self, _mkdirs, _analyze):
        malicious_id = "../../etc/passwd"
        stdin = json.dumps({"session_id": malicious_id, "prompt": "hello"}).encode()
        written_paths = []

        def fake_open(path, mode, **kwargs):
            written_paths.append(path)
            return unittest.mock.mock_open()(path, mode)

        with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(stdin))):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop(ae._SENTINEL_ENV, None)
                with patch("builtins.open", side_effect=fake_open):
                    try:
                        ae.main()
                    except SystemExit:
                        pass

        for p in written_paths:
            self.assertNotIn("..", p)
            self.assertNotIn("/etc/passwd", p)


if __name__ == "__main__":
    unittest.main()
