import logging
import io
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from re4pc.runtime_log import ConsoleFormatter, RuntimeLog, configure, log


class RuntimeLogTests(unittest.TestCase):
    def test_console_colors_do_not_modify_record_or_plain_formatter(self):
        for level in (logging.DEBUG, logging.INFO, logging.WARNING,
                      logging.ERROR, logging.CRITICAL):
            with self.subTest(level=level):
                record = logging.LogRecord('re4pc', level, '', 0, 'hello %s',
                                           ('world',), None)
                colored = ConsoleFormatter(True).format(record)
                self.assertIn('\033[', colored)
                self.assertIn('\033[0m', colored)
                self.assertIn('hello world', colored)
                self.assertNotIn('\033[', record.levelname)
                self.assertNotIn('\033[', ConsoleFormatter().format(record))

    def test_color_detection_and_log_file(self):
        root = logging.getLogger()
        previous_handlers, previous_level = root.handlers[:], root.level
        # basicConfig(force=True) closes old handlers; detach them for this test.
        root.handlers = []
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'game.log'
                for terminal, env, expected in (
                    (True, {}, True), (False, {}, False),
                    (True, {'NO_COLOR': '1'}, False),
                    (True, {'TERM': 'dumb'}, False),
                    (False, {'FORCE_COLOR': '1'}, True),
                    (True, {'NO_COLOR': '1', 'FORCE_COLOR': '1'}, True),
                ):
                    with self.subTest(terminal=terminal, env=env):
                        stream = io.StringIO()
                        stream.isatty = lambda: terminal
                        with patch('sys.stderr', stream), patch.dict('os.environ', env, clear=True):
                            configure(path=path)
                            root.warning('test warning')
                        self.assertEqual('\033[' in stream.getvalue(), expected)
                        self.assertNotIn('\033[', path.read_text())
        finally:
            for handler in root.handlers:
                handler.close()
            root.handlers, root.level = previous_handlers, previous_level

    def test_loading_heartbeat_runs_without_engine_frames(self):
        arrived = threading.Event()
        records = []
        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())
                arrived.set()
        handler = Capture()
        old_level = log.level
        log.setLevel(logging.INFO)
        log.addHandler(handler)
        try:
            with RuntimeLog(0.01) as runtime:
                self.assertTrue(arrived.wait(1))
            self.assertFalse(runtime.thread.is_alive())
            self.assertIn('waiting for engine/startup', records[0])
        finally:
            log.removeHandler(handler)
            log.setLevel(old_level)

    def test_sample_labels_gameplay_and_cursor(self):
        runtime = RuntimeLog(0)
        game = SimpleNamespace(media=SimpleNamespace(video=None),
            pc=SimpleNamespace(story_active=False, active=True), frames=12,
            graphics=SimpleNamespace(draws=42), input_events=3, mouse_captured=True)
        runtime.sample(game)
        self.assertEqual(runtime.snapshot, ('gameplay', 12, 42, 3, True))
        with runtime:
            self.assertIsNone(runtime.thread)
