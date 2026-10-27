import sys
import tempfile
import time
import unittest
from pathlib import Path
from re4pc.launcher import ChildProcess, child_command
from unittest.mock import patch, Mock


def widget_texts(widget):
    """Read rendered native text, including transparent canvas typography."""
    import tkinter as tk
    from tkinter import ttk
    result = []
    if isinstance(widget, ttk.Label):
        result.append(widget.cget('text'))
    if isinstance(widget, tk.Canvas):
        result.extend(widget.itemcget(identity, 'text') for identity in widget.find_all()
                      if widget.type(identity) == 'text')
    for child in widget.winfo_children():
        result.extend(widget_texts(child))
    return result


class LauncherTests(unittest.TestCase):
    def test_package_fonts_are_registered_from_runtime_prefix_with_spaces(self):
        from re4pc.launcher import configure_bundled_fonts
        with tempfile.TemporaryDirectory(prefix='runtime with spaces ') as directory:
            fonts = Path(directory) / 'share/fonts'
            fonts.mkdir(parents=True)
            library = Mock()
            library.FcConfigAppFontAddDir.return_value = 1
            with patch('re4pc.launcher.sys.prefix', directory), patch('ctypes.CDLL', return_value=library):
                configure_bundled_fonts()
            library.FcConfigAppFontAddDir.assert_called_once_with(None, bytes(str(fonts), 'utf-8'))

    def drain(self, child, timeout=5):
        output = ''
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            text, code = child.poll()
            output += text
            if code is not None:
                return output, code
            time.sleep(.01)
        child.kill()
        self.fail('Child did not complete')

    def test_commands_preserve_spaces_and_use_active_interpreter(self):
        self.assertEqual(child_command('run', '--game', '/game with spaces'),
                         [sys.executable, '-u', '-m', 're4pc', 'run', '--game', '/game with spaces'])
        self.assertEqual(child_command('export-backup', 'id', '/backup with spaces.zip')[-2:],
                         ['id', '/backup with spaces.zip'])

    def test_child_output_and_failure_do_not_block_gui_poll(self):
        start = time.monotonic()
        child = ChildProcess([sys.executable, '-c', 'import time; print("begin",flush=True); time.sleep(.2); print("end"); raise SystemExit(7)'])
        self.assertLess(time.monotonic() - start, .15)
        text, code = child.poll()
        self.assertIsNone(code)
        rest, code = self.drain(child)
        self.assertEqual(code, 7)
        self.assertIn('begin', text + rest)
        self.assertIn('end', text + rest)

    def test_stop_and_output_are_bounded(self):
        child = ChildProcess([sys.executable, '-c', 'import time; print("x"*3000000,flush=True); time.sleep(30)'])
        time.sleep(.1)
        self.assertLessEqual(child.output.qsize(), 256)
        child.stop()
        _, code = self.drain(child)
        self.assertLess(code, 0)

    def test_cli_help_has_no_tk_display_dependency(self):
        import subprocess
        result = subprocess.run(child_command('launcher', '--help'), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--game', result.stdout)


class LauncherGuiFixture(unittest.TestCase):
    """Real widget lifecycle; skipped on runners without a graphical display."""
    def setUp(self):
        import tkinter as tk
        from re4pc.launcher import Launcher
        try:
            self.window = tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        self.addCleanup(self.window.destroy)
        self.callback_errors = []
        self.window.report_callback_exception = lambda kind, value, trace: self.callback_errors.append(str(value))
        self.addCleanup(lambda: self.assertEqual(self.callback_errors, [], 'Native callback errors'))
        self.window.geometry('1000x600')
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        environment = patch.dict('os.environ', {'XDG_CONFIG_HOME': str(Path(temporary.name) / 'config'),
                                               'XDG_DATA_HOME': str(Path(temporary.name) / 'data')})
        environment.start()
        self.addCleanup(environment.stop)
        self.folder = Path(temporary.name) / 'game with spaces'
        self.app = Launcher(self.window, self.folder)
        self.window.update_idletasks()

    def complete_installation(self):
        from re4pc.assets import LIBRARIES, REQUIRED
        for name in [*('lib/' + name for name in LIBRARIES),
                     *('data/monhun/' + name for name in REQUIRED)]:
            path = self.folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture; readiness only, not validated game data')
        self.app.refresh_installation()


class LauncherGuiTests(LauncherGuiFixture):
    def test_launch_and_dialogs_use_installed_desktop_window_class(self):
        from re4pc.launcher import launch
        classes = []
        def inspect(window, game):
            classes.append(window.winfo_class())
            def close():
                window.quit()
                window.destroy()
            window.after_idle(close)
        with patch('re4pc.launcher.Launcher', side_effect=inspect):
            launch()
        self.assertEqual(classes, ['Re4mepc'])
        popup = self.app.dialog('Launcher icon', '400x200')
        self.assertEqual(popup.winfo_class(), classes[0])
        popup.destroy()

    def test_icon_picker_applies_and_remembers_a_choice(self):
        from re4pc.desktop import locations
        view = self.app.show_icons()
        self.assertEqual([button.label for button in view.choices],
                         ['Classic 4', 'Blood moon', 'Crimson seal', 'Church bell'])
        self.assertEqual([button.selected for button in view.choices], [True, False, False, False])
        view.choices[1].invoke()
        self.assertEqual(locations()[2].read_bytes(), (self.app.assets / 'icon-village.png').read_bytes())
        self.assertIsNotNone(self.app.app_icon)
        self.assertEqual([button.selected for button in view.choices], [False, True, False, False])
        view.window.destroy()
        view = self.app.show_icons()
        self.assertTrue(view.choices[1].selected)
        view.window.destroy()

    def test_icon_picker_fits_minimum_and_keeps_selection_after_save_failure(self):
        from re4pc.desktop import locations
        view = self.app.show_icons()
        for geometry in ('600x400', '680x400'):
            view.window.geometry(geometry)
            self.window.update()
            for button in (*view.choices, view.browse_button, view.done_button):
                self.assertGreaterEqual(button.winfo_x(), 0)
                self.assertGreaterEqual(button.winfo_y(), 0)
                self.assertLessEqual(button.winfo_x()+button.winfo_width(), view.paper.winfo_width())
                self.assertLessEqual(button.winfo_y()+button.winfo_height(), view.paper.winfo_height())
        view.choices[0].focus_force()
        view.choices[0].event_generate('<Right>')
        self.window.update()
        self.assertIs(view.window.focus_get(), view.choices[1])
        view.choices[1].event_generate('<Return>')
        self.window.update()
        previous = locations()[2].read_bytes()
        with patch('re4pc.desktop.save_icon', side_effect=OSError('Permission denied')):
            view.choices[2].invoke()
        self.assertTrue(view.error)
        self.assertIn('Permission denied', view.notice.get())
        self.assertTrue(view.choices[1].selected)
        self.assertFalse(view.choices[2].selected)
        self.assertEqual(locations()[2].read_bytes(), previous)
        custom = self.folder.parent / 'custom.png'
        from PIL import Image
        Image.new('RGBA', (64, 64), '#78190f').save(custom)
        with patch('tkinter.filedialog.askopenfilename', return_value=str(custom)):
            view.browse_button.invoke()
        self.assertFalse(view.error)
        self.assertFalse(any(button.selected for button in view.choices))
        self.assertEqual(locations()[2].read_bytes(), custom.read_bytes())
        view.window.event_generate('<Escape>')
        self.window.update()
        self.assertFalse(view.window.winfo_exists())

    def test_console_is_absent_until_requested_and_log_survives_reopening(self):
        self.assertIsNone(self.app.console)
        self.assertIsNone(self.app.log_window)
        self.app.append('Captured without a console\n')
        self.app.show_logs()
        self.assertIn('Captured without a console', self.app.console.get('1.0', 'end'))
        self.app.log_window.destroy()
        self.app.append('More output\n')
        self.app.show_logs()
        self.assertIn('More output', self.app.console.get('1.0', 'end'))
        self.app.log_window.destroy()
        self.app.append('x' * 300000)
        self.assertLessEqual(len(self.app.log_output), 128 * 1024)

    def test_missing_installation_disables_game_actions_but_keeps_import(self):
        self.assertTrue(self.app.play_button.instate(['disabled']))
        self.assertTrue(self.app.backups_button.instate(['disabled']))
        self.assertTrue(self.app.diagnostics_button.instate(['disabled']))
        self.assertTrue(self.app.achievements_button.instate(['disabled']))
        self.assertFalse(self.app.import_button.instate(['disabled']))
        self.complete_installation()
        self.assertFalse(self.app.play_button.instate(['disabled']))
        self.assertFalse(self.app.achievements_button.instate(['disabled']))
        self.app.game.set('   ')
        self.app.refresh_installation()
        self.assertTrue(self.app.play_button.instate(['disabled']))

    def test_achievements_show_saved_unlocks_progress_and_scroll(self):
        import tkinter as tk
        from tkinter import ttk
        from re4pc.achievements import ACHIEVEMENTS, AchievementStore, Progress
        self.complete_installation()
        ranks = [[-1] * 5 for _ in range(22)]
        ranks[0][0] = 4
        AchievementStore(self.folder).update(Progress(tuple(tuple(row) for row in ranks)))
        self.app.achievements()
        popup = next(widget for widget in self.window.winfo_children() if isinstance(widget, tk.Toplevel))
        self.window.update()

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        widgets = list(descendants(popup))
        texts = widget_texts(popup)
        self.assertIn('It Begins With a Ring', texts)
        self.assertIn('Unlocked', texts)
        self.assertIn('Locked', texts)
        self.assertIn(f'2 / {len(ACHIEVEMENTS)} unlocked', popup.view.summary.get())
        canvas = popup.view.catalog.canvas
        popup.view.select(ACHIEVEMENTS[-1].id)
        canvas.yview_moveto(1)
        self.assertGreater(canvas.yview()[0], 0)
        canvas.event_generate('<Button-4>', x=40, y=40)
        canvas.event_generate('<Button-4>', x=40, y=40)
        deadline = time.monotonic() + .1
        while time.monotonic() < deadline:
            self.window.update()
            time.sleep(.01)
        self.window.update()
        self.assertLess(canvas.yview()[1], 1)
        popup.destroy()

    def test_achievements_empty_state_and_bad_record_are_visible(self):
        import tkinter as tk
        from tkinter import ttk
        from re4pc.achievements import AchievementStore
        self.complete_installation()
        for corrupt in (False, True):
            if corrupt:
                path = AchievementStore(self.folder).path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'broken')
            self.app.achievements()
            popup = next(widget for widget in self.window.winfo_children() if isinstance(widget, tk.Toplevel))
            self.assertIn('Could not read' if corrupt else 'Play once', popup.view.summary.get())
            popup.destroy()

    def test_achievement_media_icons_preview_and_capture_settings(self):
        import tkinter as tk
        from tkinter import ttk
        from PIL import Image
        from re4pc.achievements import AchievementStore, Progress, ACHIEVEMENTS
        from re4pc.achievement_media import UnlockCapture
        self.complete_installation()
        store = AchievementStore(self.folder)
        store.update(Progress(story=(True,) + (False,) * 21))
        capture = UnlockCapture(self.folder, store, {'achievement_capture':'screenshot'})
        capture.tick(lambda:Image.new('RGB', (80,48), 'green'), ['village'])
        capture.close()
        self.app.achievements()
        popup = next(widget for widget in self.window.winfo_children() if isinstance(widget, tk.Toplevel))
        self.window.update()
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        widgets = list(descendants(popup))
        self.assertGreaterEqual(sum(isinstance(widget, tk.Canvas) for widget in widgets), len(ACHIEVEMENTS) + 1)
        view = next(widget for widget in widgets if isinstance(widget, ttk.Button) and widget.cget('text') == 'View screenshot')
        view.invoke()
        viewer = next(widget for widget in popup.winfo_children() if isinstance(widget, tk.Toplevel))
        self.assertIsNotNone(viewer.capture_image)
        popup.destroy()
        self.app.settings()
        popup = next(widget for widget in self.window.winfo_children() if isinstance(widget, tk.Toplevel))
        popup.view.select('Achievements')
        controls = [widget for widget in descendants(popup.view.panes['Achievements'].content) if isinstance(widget, ttk.Combobox)]
        controls[0].set('both')
        controls[1].set('7')
        save = popup.view.save_button
        with patch('re4pc.settings.Settings.save') as saved:
            save.invoke()
        self.assertEqual(saved.call_args.args[0]['achievement_capture'], 'both')
        self.assertEqual(saved.call_args.args[0]['achievement_clip_seconds'], 7)

    def test_generated_assets_load_and_settings_bindings_scroll(self):
        import tkinter as tk
        from tkinter import ttk
        self.assertIsNotNone(self.app.banner_source)
        self.assertEqual(set(self.app.utility_images), {'settings', 'backups', 'achievements'})
        self.assertIsNotNone(self.app.app_icon)
        self.app.settings()
        popup = next(widget for widget in self.window.winfo_children() if isinstance(widget, tk.Toplevel))
        popup.geometry('640x520')
        self.window.update()
        popup.view.select('Keyboard')
        self.window.update()
        canvas = popup.view.panes['Keyboard'].canvas
        canvas.yview_moveto(1)
        self.assertGreater(canvas.yview()[0], 0)
        popup.event_generate('<Button-4>')
        self.window.update()
        self.assertLess(canvas.yview()[1], 1)
        popup.destroy()

    def test_busy_failure_and_stop_are_visible_without_opening_logs(self):
        self.complete_installation()
        child = Mock()
        child.poll.return_value = ('fixture failure\n', 7)
        with patch('re4pc.launcher.ChildProcess', return_value=child):
            self.app.play()
        self.assertTrue(self.app.import_button.instate(['disabled']))
        self.assertTrue(self.app.game_entry.instate(['disabled']))
        self.assertEqual(self.app.play_button.cget('text'), 'Playing')
        self.window.after_cancel(self.app.tick_job)
        self.app.tick()
        self.assertIn('failed', self.app.status.get())
        self.assertIsNone(self.app.log_window)
        self.assertFalse(self.app.play_button.instate(['disabled']))
        self.assertIn('fixture failure', self.app.log_output)
        with patch('re4pc.launcher.ChildProcess', return_value=child):
            self.app.play()
        self.app.stop()
        self.app.stop()
        child.stop.assert_called_once()
        self.window.after_cancel(self.app.tick_job)
        self.app.tick()
        self.assertEqual(self.app.status.get(), 'Operation stopped.')

    def test_import_uses_unused_destination_and_only_switches_on_success(self):
        self.complete_installation()
        destination = self.folder.with_name('new imported game')
        with patch('tkinter.filedialog.askopenfilename', return_value='/tmp/my game.apk'), \
             patch('tkinter.simpledialog.askstring', return_value=str(destination)) as prompt, \
             patch.object(self.app, 'start') as start:
            self.app.import_apk()
        self.assertEqual(prompt.call_args.kwargs['initialvalue'], str(self.folder.with_name(self.folder.name + '-2')))
        self.assertEqual(self.app.game.get(), str(self.folder))
        callback = start.call_args.kwargs['on_complete']
        callback(1)
        self.assertEqual(self.app.game.get(), str(self.folder))
        callback(0)
        self.assertEqual(self.app.game.get(), str(destination))

    def test_artwork_actions_support_keyboard_activation_and_disabled_state(self):
        self.window.deiconify()
        button = self.app.import_button
        button.command = Mock()
        button.focus_force()
        self.window.update()
        button.event_generate('<Return>')
        self.window.update()
        button.command.assert_called_once_with()
        button.configure(state='disabled')
        button.event_generate('<space>')
        button.invoke()
        self.window.update()
        button.command.assert_called_once_with()
        self.assertFalse(bool(int(button.cget('takefocus'))))

    def test_resize_keeps_controls_inside_artwork_and_stop_is_only_visible_when_busy(self):
        self.window.deiconify()
        self.complete_installation()
        for width, height in ((1000, 600), (1000, 800), (1440, 810)):
            with self.subTest(size=(width, height)):
                self.window.geometry(f'{width}x{height}')
                self.window.update()
                self.app.view.draw(width, height)
                self.window.update_idletasks()
                for button, bounds in self.app.view.bounds.items():
                    x, y, bw, bh = bounds
                    self.assertGreaterEqual(x, 0)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(x + bw, width)
                    self.assertLessEqual(y + bh, height)
                self.assertFalse(self.app.stop_button.winfo_ismapped())
        child = Mock()
        child.poll.return_value = ('', None)
        with patch('re4pc.launcher.ChildProcess', return_value=child):
            self.app.play()
        self.window.update_idletasks()
        self.assertTrue(self.app.stop_button.winfo_ismapped())
        self.assertGreaterEqual(self.app.stop_button.winfo_width(), 80)
        self.assertGreaterEqual(self.app.stop_button.winfo_height(), 30)
        self.assertTrue(self.app.view.nav['settings'].instate(['disabled']))
        self.assertTrue(self.app.view.nav['backups'].instate(['disabled']))
        child.poll.return_value = ('', 0)
        self.window.after_cancel(self.app.tick_job)
        self.app.tick()
        self.window.update_idletasks()
        self.assertFalse(self.app.stop_button.winfo_ismapped())
        self.assertFalse(self.app.view.nav['settings'].instate(['disabled']))

    def test_responsive_composition_fills_viewport_and_keeps_controls_separate(self):
        from itertools import combinations
        view = self.app.view
        for width, height in ((640, 520), (800, 600), (800, 850), (899, 520),
                              (900, 520), (1000, 800), (1440, 810), (1500, 560),
                              (2560, 1080), (900, 1600)):
            with self.subTest(size=(width, height)):
                self.window.geometry(f'{width}x{height}')
                self.window.update()
                view.draw(width, height)
                self.window.update_idletasks()
                self.assertEqual(view.scaled.size, (width, height))
                self.assertEqual(view.canvas.coords(view.canvas.find_withtag('backdrop')[0]), [0, 0])
                self.assertEqual(view.stacked, width < 900)
                controls = [button for button in view.bounds if button.winfo_ismapped()]
                controls += [self.app.game_entry, *(item[0] for item in view.language_controls.values())]
                rectangles = []
                for control in controls:
                    x, y = control.winfo_x(), control.winfo_y()
                    w, h = control.winfo_width(), control.winfo_height()
                    self.assertGreaterEqual(x, 0)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(x + w, width)
                    self.assertLessEqual(y + h, height)
                    self.assertGreaterEqual(h, 30)
                    rectangles.append((x, y, x + w, y + h))
                for a, b in combinations(rectangles, 2):
                    self.assertFalse(a[0] < b[2] and b[0] < a[2] and
                                     a[1] < b[3] and b[1] < a[3], (a, b))

    def test_reflow_preserves_focused_folder_languages_and_keyboard_actions(self):
        view = self.app.view
        self.app.game.set('/a folder with spaces/installation')
        self.app.game_entry.focus_force()
        self.app.game_entry.selection_range(3, 12)
        self.window.update()
        for width, height in ((640, 520), (1280, 720), (800, 800)):
            self.window.geometry(f'{width}x{height}')
            self.window.update()
            view.draw(width, height)
            self.window.update_idletasks()
            self.assertIs(self.window.focus_get(), self.app.game_entry)
            self.assertEqual(self.app.game.get(), '/a folder with spaces/installation')
            self.assertEqual(self.app.game_entry.index('sel.first'), 3)
            self.assertEqual(self.app.game_entry.index('sel.last'), 12)
            for key, (control, _, choices) in view.language_controls.items():
                code = getattr(self.app, key if key == 'game_language' else 'launcher_language_value').get()
                self.assertEqual(control.current(), tuple(choices).index(code))
        view.settings_button.command = Mock()
        view.settings_button.focus_force()
        self.window.update()
        view.settings_button.event_generate('<Return>')
        view.settings_button.command.assert_called_once_with()

    def test_compact_busy_and_error_feedback_stays_above_footer_in_every_language(self):
        from re4pc.languages import LAUNCHER_LANGUAGES
        view = self.app.view
        self.app.child = Mock()
        self.app.child.poll.return_value = ('', None)
        self.app.operation = 'run'
        self.app.status.set('Long error details\n' * 100 + 'x' * 1000)
        self.window.geometry('640x520')
        self.window.update()
        for language in LAUNCHER_LANGUAGES:
            self.app.launcher_language = language
            self.app.retranslate()
            self.window.update_idletasks()
            self.assertTrue(self.app.stop_button.winfo_ismapped())
            self.assertTrue(self.app.progress.winfo_ismapped())
            for item in view.canvas.find_withtag('status'):
                bounds = view.canvas.bbox(item)
                self.assertLessEqual(bounds[3], view.status_bounds[3] + 40)
                if view.canvas.type(item) == 'text' and 'Long error' in view.canvas.itemcget(item, 'text'):
                    self.assertLessEqual(bounds[3], view.status_bounds[3])
                    self.assertIn('…', view.canvas.itemcget(item, 'text'))
        self.app.child = None
        view.update_status()
        self.assertFalse(self.app.stop_button.winfo_ismapped())
        self.assertFalse(self.app.progress.winfo_ismapped())


class DialogFormattingTests(unittest.TestCase):
    def test_completion_timestamp_local_zone_and_midnight(self):
        import datetime as dt
        from re4pc.launcher_ui import completion_time
        zone = dt.timezone(dt.timedelta(hours=-5))
        stamp = int(dt.datetime(2026, 10, 12, 19, 32, 8, tzinfo=dt.timezone.utc).timestamp() * 1e9)
        self.assertEqual(completion_time(stamp, zone=zone),
                         'Completion recorded: 12 Oct 2026 · 14:32:08 UTC−05:00')
        self.assertEqual(completion_time(stamp, short=True, zone=zone), '12 Oct 2026 · 14:32')
        midnight = int(dt.datetime(2026, 10, 12, 4, 59, 59, tzinfo=dt.timezone.utc).timestamp() * 1e9)
        self.assertIn('11 Oct 2026 · 23:59:59', completion_time(midnight, zone=zone))
        self.assertIn('12 Oct 2026 · 00:00:00', completion_time(midnight + 1_000_000_000, zone=zone))
        self.assertIn('UTC+05:30', completion_time(stamp, zone=dt.timezone(dt.timedelta(hours=5, minutes=30))))


class CaseFileDialogTests(LauncherGuiFixture):
    def test_settings_roundtrip_every_field_and_all_bindings(self):
        from re4pc.settings import Settings, DEFAULTS
        from re4pc.actions import NATIVE_CODES
        from copy import deepcopy
        path = self.folder / 'fixture-settings.json'
        values = deepcopy(DEFAULTS)
        values.update(sensitivity=2.3, controller_sensitivity=.8, invert_y=True, stick_dead_zone=.3,
                      window_mode='fullscreen', window_width=1280, window_height=720,
                      achievement_capture='both', achievement_clip_seconds=7)
        # Include a comma key and an unbound action without colliding with defaults.
        values['bindings']['keyboard'] = {action: [] for action in NATIVE_CODES}
        values['bindings']['keyboard']['forward'] = [ord(','), ord('w')]
        Settings.save(values, path)
        with patch('re4pc.settings.Settings.load', return_value=Settings.load(path)):
            view = self.app.settings()
        self.window.update()
        save_to_disk = Settings.save
        with patch('re4pc.settings.Settings.save', side_effect=lambda data: save_to_disk(data, path)):
            view.save()
        expected = Settings.load(path)
        for device in ('mouse', 'controller'):
            values['bindings'][device] = {action: values['bindings'][device].get(action, []) for action in NATIVE_CODES}
        self.assertEqual(expected, values)
        self.assertFalse(view.window.winfo_exists())

    def test_invalid_values_and_bindings_are_inline_and_do_not_write(self):
        from re4pc.settings import Settings, DEFAULTS
        path = self.folder / 'settings.json'
        Settings.save(DEFAULTS, path)
        original = path.read_bytes()
        with patch('re4pc.settings.Settings.load', return_value=Settings.load(path)):
            view = self.app.settings()
        for key, invalid in (('window_width', '239'), ('sensitivity', 'nan'),
                             ('achievement_clip_seconds', '16'), ('presentation_rate', '21'),
                             (('keyboard', 'forward'), 'Tab'), (('mouse', 'forward'), 'Unknown'),
                             (('controller', 'forward'), 'not-a-button')):
            with self.subTest(field=key):
                variables = view.binding_editors if isinstance(key, tuple) else view.editors
                old = variables[key].get()
                variables[key].set(invalid)
                with patch('re4pc.settings.Settings.save') as save:
                    view.save()
                save.assert_not_called()
                self.assertTrue(view.fields[key][2].cget('text'))
                self.assertEqual(view.section, view.fields[key][0])
                self.assertEqual(path.read_bytes(), original)
                variables[key].set(old)
        self.assertTrue(view.window.winfo_exists())
        view.window.destroy()

    def test_cancel_and_wm_close_confirm_only_actual_edits(self):
        view = self.app.settings()
        with patch('tkinter.messagebox.askyesno') as ask:
            view.close()
        ask.assert_not_called()
        view = self.app.settings()
        view.editors['window_width'].set('1440')
        with patch('tkinter.messagebox.askyesno', return_value=False) as ask:
            view.close()
        ask.assert_called_once()
        self.assertTrue(view.window.winfo_exists())
        with patch('tkinter.messagebox.askyesno', return_value=True):
            view.close()
        self.assertFalse(view.window.winfo_exists())

    def test_settings_focus_navigation_scroll_and_footer_at_minimum(self):
        view = self.app.settings()
        view.window.geometry('640x520')
        self.window.update()
        view.nav['Display & sensitivity'].focus_force()
        view.nav['Display & sensitivity'].event_generate('<Down>')
        self.window.update()
        self.assertEqual(view.section, 'Laser sight')
        view.select('Keyboard')
        self.window.update()
        pane = view.panes['Keyboard']
        keys = [key for key in view.binding_editors if key[0] == 'keyboard']
        control = view.fields[keys[-1]][1]
        control.focus_force()
        self.window.update()
        self.assertGreater(pane.canvas.yview()[0], 0)
        self.assertLess(control.winfo_rooty(), pane.canvas.winfo_rooty() + pane.canvas.winfo_height())
        for button in (view.save_button, view.cancel_button):
            self.assertTrue(button.winfo_ismapped())
            self.assertLessEqual(button.winfo_y() + button.winfo_height(), button.master.winfo_height())
        view.window.destroy()
        self.window.update()

    def test_catalog_filters_refresh_retention_and_keyboard_selection(self):
        from re4pc.achievements import ACHIEVEMENTS, AchievementStore, Progress
        store = AchievementStore(self.folder)
        store.update(Progress(story=(True,) + (False,) * 21))
        view = self.app.achievements()
        self.window.update()
        self.assertEqual([item.id for item in view.visible], [item.id for item in ACHIEVEMENTS])
        self.assertEqual(view.selected, 'village')
        with patch.object(self.app, 'start') as start:
            view.rows['village'].focus_force()
            view.rows['village'].event_generate('<Down>')
            self.window.update()
            self.assertEqual(view.selected, 'gigante')
            view.select('expert')
            view.catalog.canvas.yview_moveto(.5)
            self.window.update()
            fraction = view.catalog.canvas.yview()[0]
            view.refresh()
            self.window.update()
            self.assertEqual(view.selected, 'expert')
            self.assertAlmostEqual(view.catalog.canvas.yview()[0], fraction, delta=.015)
        start.assert_not_called()
        view.filter.set('Unlocked')
        self.window.update()
        self.assertEqual([item.id for item in view.visible], ['village'])
        self.assertEqual(view.selected, 'village')
        view.search.set('no-such-title')
        self.window.update()
        self.assertEqual(view.visible, [])
        self.assertIsNone(view.selected)
        view.filter.set('Locked')
        view.search.set('tune-up')
        self.window.update()
        self.assertEqual([item.id for item in view.visible], ['first_upgrade', 'tuned', 'expert'])
        view.window.destroy()
        self.assertEqual(view.art.images, {})
        self.assertIsNone(view.job)

    def test_responsive_achievement_panes_and_independent_scroll(self):
        view = self.app.achievements()
        for geometry, stacked in (('1040x760', False), ('600x420', True), ('900x600', False)):
            view.window.geometry(geometry)
            self.window.update()
            self.assertEqual(view.mode, stacked)
            self.assertEqual(int(view.detail.frame.grid_info()['row']), 1 if stacked else 0)
            for button in (view.close_button, view.refresh_button):
                self.assertTrue(button.winfo_ismapped())
                self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                     view.window.winfo_rooty() + view.window.winfo_height())
            self.assertGreater(view.detail.canvas.winfo_height(), 65)
            self.assertTrue(view.detail.frame.winfo_ismapped())
            self.assertGreater(view.catalog.frame.winfo_width(), view.body.winfo_width() * (.8 if stacked else .4))
        view.window.geometry('600x420')
        self.window.update()
        before = view.catalog.canvas.yview()
        view.detail.canvas.event_generate('<Button-5>', x=10, y=10)
        self.window.update()
        self.assertEqual(view.catalog.canvas.yview(), before)
        self.assertGreater(view.detail.canvas.yview()[0], 0)
        view.window.destroy()

    def test_achievement_wheel_pages_accumulate_bound_and_keep_rows_alive(self):
        view = self.app.achievements()
        view.window.geometry('1040x760')
        self.window.update()
        rows = dict(view.rows)
        rows[view.visible[0].id].focus_force()
        self.window.update()

        def settle():
            deadline = time.monotonic() + .08
            while time.monotonic() < deadline:
                self.window.update()
                time.sleep(.005)

        def wheel(sequence, *, delta=None, count=1, target=None):
            canvas = view.catalog.canvas
            target = target or canvas
            first = view.rows[view.visible[0].id]
            y = min(canvas.winfo_height() - 10,
                    max(10, first.winfo_rooty() - canvas.winfo_rooty() + 10))
            for _ in range(count):
                options = dict(x=40, y=y if target is canvas else 10, when='tail')
                if delta is not None:
                    options['delta'] = delta
                target.event_generate(sequence, **options)
            settle()

        def selected(index):
            self.assertEqual(view.selected, view.visible[index].id)
            self.assertEqual(view.rows, rows)
            self.assertIsNone(view.wheel_job)

        wheel('<Button-5>', target=rows[view.visible[0].id])
        selected(4)
        self.assertIs(view.window.focus_get(), rows[view.visible[4].id])
        self.assertGreater(view.catalog.canvas.yview()[0], 0)
        wheel('<Button-4>')
        selected(0)
        self.assertEqual(view.catalog.canvas.yview()[0], 0)
        wheel('<MouseWheel>', delta=0)
        selected(0)
        # Tk's native delta units differ on macOS.
        unit = 1 if view.window.tk.call('tk', 'windowingsystem') == 'aqua' else 120
        if unit == 120:
            for _ in range(3):
                wheel('<MouseWheel>', delta=-30)
                selected(0)
            wheel('<MouseWheel>', delta=-30)
            selected(4)
            wheel('<MouseWheel>', delta=-150)
            selected(8)
            wheel('<MouseWheel>', delta=-90)
            selected(12)
        wheel('<MouseWheel>', delta=-unit, count=100)
        selected(20)
        wheel('<Button-5>', count=20)
        selected(20)
        wheel('<MouseWheel>', delta=unit, count=100)
        selected(0)
        wheel('<Button-5>', target=view.close_button, count=10)
        selected(0)
        wheel('<Button-5>', target=view.search_entry)
        selected(0)
        before = view.catalog.canvas.yview()
        wheel('<Button-5>', target=view.detail.canvas)
        selected(0)
        self.assertEqual(view.catalog.canvas.yview(), before)
        view.window.geometry('600x420')
        self.window.update()
        wheel('<Button-5>')
        selected(4)
        wheel('<Button-4>')
        selected(0)
        view.window.destroy()

    def test_achievement_pending_wheel_filter_refresh_and_close(self):
        view = self.app.achievements()
        self.window.update()

        def queue_wheel():
            row = view.rows[view.visible[0].id]
            row.event_generate('<Button-5>', x=40, y=10)
            self.assertIsNotNone(view.wheel_job)

        queue_wheel()
        view.search.set('tune-up')
        self.window.update()
        self.assertIsNone(view.wheel_job)
        self.assertEqual(view.selected, view.visible[0].id)
        view.rows[view.visible[0].id].event_generate('<Button-5>', x=40, y=10)
        self.assertIsNone(view.wheel_job)
        self.assertEqual(view.selected, view.visible[0].id)
        view.search.set('no-such-title')
        self.window.update()
        view.catalog.canvas.event_generate('<Button-5>', x=40, y=40)
        self.assertIsNone(view.wheel_job)
        self.assertIsNone(view.selected)
        view.search.set('')
        self.window.update()
        queue_wheel()
        view.refresh()
        self.window.update()
        self.assertIsNone(view.wheel_job)
        queue_wheel()
        view.window.destroy()
        self.window.update()
        self.assertIsNone(view.wheel_job)

    def test_achievement_scroll_keeps_embedded_rows_and_their_artwork_drawn(self):
        view = self.app.achievements()
        view.window.geometry('1040x760')
        self.window.update()
        paper = view.catalog.content
        first = view.rows[view.visible[0].id]
        first.focus_force()
        self.window.update()
        self.assertTrue(any(first.itemcget(item, 'dash') for item in first.find_all()
                            if first.type(item) == 'rectangle'))
        windows = [item for item in paper.find_all() if paper.type(item) == 'window']
        unchanged_row = view.rows[view.visible[5].id]
        row_items = unchanged_row.find_all()

        def settle():
            deadline = time.monotonic() + .15
            while time.monotonic() < deadline:
                self.window.update()
                time.sleep(.005)

        with patch.object(paper, 'render', wraps=paper.render) as redraw:
            view.rows[view.visible[0].id].event_generate('<Button-5>', x=40, y=10)
            settle()
            self.assertEqual(view.selected, view.visible[4].id)
            redraw.assert_not_called()
            self.assertEqual(windows, [item for item in paper.find_all() if paper.type(item) == 'window'])
            self.assertTrue(unchanged_row.winfo_ismapped())
            self.assertEqual(unchanged_row.find_all(), row_items)
            # Scrolling the scrollbar must also preserve the embedded windows.
            view.catalog.canvas.yview_moveto(.8)
            settle()
            view.catalog.canvas.yview_moveto(0)
            settle()
            redraw.assert_not_called()
            self.assertTrue(view.rows[view.visible[0].id].winfo_ismapped())
            # A real resize must still reflow and repaint the paper.
            view.window.geometry('900x600')
            settle()
            self.assertTrue(redraw.called)
        view.window.destroy()

    def test_missing_capture_corrupt_record_and_fallbacks(self):
        from re4pc.achievements import AchievementStore, Progress, ACHIEVEMENTS
        from re4pc.launcher_ui import AchievementArtwork
        import tkinter as tk
        store = AchievementStore(self.folder)
        store.update(Progress(story=(True,) + (False,) * 21))
        store.attach_media(['village'], {'image': 'unlock-missing.png', 'clip': 'unlock-missing.mp4'})
        view = self.app.achievements()
        self.window.update()
        def texts(widget):
            from tkinter import ttk
            return widget_texts(widget)
        self.assertTrue(any('missing' in text for text in texts(view.detail.content)))
        self.assertTrue(any('detection timestamp' in text for text in texts(view.detail.content)))
        with patch('tkinter.messagebox.showerror') as error:
            view.open_capture('unlock-missing.png')
        error.assert_called_once()
        art = AchievementArtwork(self.folder / 'no art')
        canvas = tk.Canvas(view.window, width=192, height=192)
        for item in ACHIEVEMENTS:
            art.draw(canvas, item, 192)
            self.assertTrue(canvas.find_all())
        self.assertEqual(len(art.images), len(ACHIEVEMENTS))
        store.path.write_bytes(b'corrupt record')
        view.refresh()
        self.window.update()
        self.assertIn('Could not read', view.summary.get())
        self.assertEqual(view.rows, {})
        self.assertIsNone(view.selected)
        view.window.destroy()

    def test_clip_open_uses_safe_path_without_game_launch(self):
        from re4pc.achievement_media import media_path
        from re4pc.achievements import AchievementStore, Progress
        media = self.folder / 'achievement-media'
        media.mkdir(parents=True)
        (media / 'unlock-fixture.mp4').write_bytes(b'synthetic fixture; external opener mocked')
        store = AchievementStore(self.folder)
        store.update(Progress(story=(True,) + (False,) * 21))
        store.attach_media(['village'], {'clip': 'unlock-fixture.mp4'})
        view = self.app.achievements()
        with patch('subprocess.Popen') as opened, patch.object(self.app, 'start') as start:
            view.open_capture('unlock-fixture.mp4')
        self.assertEqual(opened.call_args.args[0], ['xdg-open', str(media_path(self.folder, 'unlock-fixture.mp4'))])
        start.assert_not_called()
        with patch('tkinter.messagebox.showerror') as error, patch('subprocess.Popen') as opened:
            view.open_capture('../escape.mp4')
        error.assert_called_once()
        opened.assert_not_called()
        view.window.destroy()

    def test_every_catalog_entry_locked_unlocked_and_artwork_cache(self):
        from re4pc.achievements import ACHIEVEMENTS, AchievementStore, Progress
        from tkinter import ttk
        store = AchievementStore(self.folder)
        stamp = 1791833528000000000
        store._write(Progress(), {item.id: stamp for item in ACHIEVEMENTS})
        view = self.app.achievements()
        self.window.update()
        for item in ACHIEVEMENTS:
            view.select(item.id)
            labels = widget_texts(view.detail.content)
            self.assertIn('EARNED', labels)
            self.assertIn(item.title, labels)
            self.assertTrue(any(text.startswith('Completion recorded:') for text in labels))
            self.assertIsNotNone(view.art.images[(item.id, 72)])
            self.assertTrue(any(key[0] == item.id and key[1] >= 192 and image is not None for key, image in view.art.images.items()))
        photos = dict(view.art.images)
        store._write(Progress(), {})
        view.refresh()
        self.window.update()
        for item in ACHIEVEMENTS:
            view.select(item.id)
            labels = widget_texts(view.detail.content)
            self.assertIn('LOCKED', labels)
            self.assertIn(item.description, labels)
            self.assertFalse(any(text.startswith('Completion recorded:') for text in labels))
            self.assertIs(view.art.images[(item.id, 72)], photos[(item.id, 72)])
            for key in photos:
                if key[0] == item.id:
                    self.assertIs(view.art.images[key], photos[key])
        view.window.destroy()
        self.assertEqual(view.art.images, {})

    def test_launcher_close_checks_unsaved_settings(self):
        view = self.app.settings()
        view.editors['window_height'].set('720')
        with patch('tkinter.messagebox.askyesno', return_value=False) as ask:
            self.app.close()
        ask.assert_called_once()
        self.assertTrue(self.window.winfo_exists())
        self.assertTrue(view.window.winfo_exists())
        view.window.destroy()


class FinalCaseFileTests(LauncherGuiFixture):
    def test_gallery_exports_selected_identity_all_independent_of_filter_and_busy_errors(self):
        view = self.app.achievements()
        view.search.set('Rock')
        self.window.update()
        self.assertEqual(view.selected, 'gigante')
        with patch.object(self.app, 'start') as start, patch('tkinter.filedialog.asksaveasfilename', return_value='/tmp/gallery with spaces.zip'):
            view.export(True)
            self.assertEqual(start.call_args.args, ('export-achievements', '/tmp/gallery with spaces.zip', '--achievement', 'gigante', '--game', view.root))
            view.filter.set('Unlocked')
            self.window.update()
            self.assertIsNone(view.selected)
            view.export(False)
            self.assertEqual(start.call_args.args, ('export-achievements', '/tmp/gallery with spaces.zip', '--game', view.root))
        self.app.child = Mock()
        view.busy_changed()
        self.assertTrue(view.export_all_button.instate(['disabled']))
        self.assertTrue(view.export_selected_button.instate(['disabled']))
        with patch.object(self.app, 'start') as start:
            view.export(False)
        start.assert_not_called()
        self.app.child = None
        view.store.path.parent.mkdir(parents=True, exist_ok=True)
        view.store.path.write_bytes(b'invalid record')
        view.refresh()
        self.assertTrue(view.export_all_button.instate(['disabled']))
        view.window.destroy()

    def test_backup_media_option_is_unchecked_visible_and_opt_in(self):
        view, items = self.backup_view()
        view.window.geometry('640x520')
        self.window.update()
        self.assertFalse(view.include_media.get())
        self.assertTrue(view.media_option.winfo_ismapped())
        relative = view.media_option.winfo_rooty() - view.detail.canvas.winfo_rooty()
        self.assertGreaterEqual(relative, 0)
        self.assertLess(relative + view.media_option.winfo_height(), view.detail.canvas.winfo_height())
        with patch.object(self.app, 'start') as start, patch('tkinter.filedialog.asksaveasfilename', return_value='/tmp/bundle.zip'):
            view.include_media.set(True)
            view.export()
            self.assertEqual(start.call_args.args, ('export-backup', view.selected, '/tmp/bundle.zip', '--include-media', '--game', view.root))
        self.app.child = Mock()
        view.busy_changed()
        self.assertTrue(view.media_option.instate(['disabled']))
        self.app.child = None
        view.window.destroy()

    def backup_view(self, items=None):
        import json
        with patch.object(self.app, 'start'):
            view = self.app.backups()
        if items is None:
            items = [{'id': str(index)*64, 'created_ns': 1791822484000000000-index*60000000000,
                      'label': label, 'files': {'slot': {'bytes': 3}}}
                     for index, label in enumerate(('manual', 'saved', 'before-save'))]
        self.app.last_output = json.dumps(items)
        view.load(0)
        self.window.update()
        return view, items

    def test_sliders_sync_entries_keyboard_and_invalid_input_remains_visible(self):
        view = self.app.settings()
        self.window.update()
        for key, value in (('sensitivity', 2.3), ('controller_sensitivity', 1.8), ('stick_dead_zone', .32)):
            slider = view.sliders[key]
            slider.set(value)
            self.assertEqual(float(view.editors[key].get()), value)
            view.editors[key].set(str(value+.1))
            self.assertAlmostEqual(slider.value(), value+.1)
            slider.focus_force()
            slider.event_generate('<Right>')
            self.window.update()
            self.assertGreater(float(view.editors[key].get()), value+.1)
        view.editors['sensitivity'].set('nan')
        with patch('re4pc.settings.Settings.save') as save:
            view.save()
        save.assert_not_called()
        self.assertEqual(view.editors['sensitivity'].get(), 'nan')
        self.assertTrue(view.fields['sensitivity'][2].winfo_ismapped())
        view.window.destroy()

    def test_backup_keyboard_selection_retention_empty_error_and_busy_states(self):
        view, items = self.backup_view()
        self.assertEqual(view.selected, items[0]['id'])
        view.rows[items[0]['id']].focus_force()
        view.rows[items[0]['id']].event_generate('<Down>')
        self.window.update()
        self.assertEqual(view.selected, items[1]['id'])
        view.load(0)
        self.window.update()
        self.assertEqual(view.selected, items[1]['id'])
        self.assertIn('Game save', widget_texts(view.detail.content))
        self.app.child = Mock()
        view.busy_changed()
        for button in (view.create_button, view.import_button, view.export_button, view.restore_button, view.delete_button):
            self.assertTrue(button.instate(['disabled']))
        with patch.object(self.app, 'start') as start:
            view.create()
            view.delete()
        start.assert_not_called()
        self.app.child = None
        view.busy_changed()
        self.assertFalse(view.export_button.instate(['disabled']))
        self.app.last_output = 'not json'
        view.load(0)
        self.assertIn('Could not read', view.notice)
        self.assertEqual(view.selected, items[1]['id'])
        self.app.last_output = '[]'
        view.load(0)
        self.assertIsNone(view.selected)
        self.assertTrue(view.restore_button.instate(['disabled']))
        self.assertIn('No snapshots yet', view.notice)
        view.window.destroy()

    def test_backup_routes_preserve_root_and_confirmation_and_refresh_on_success(self):
        view, items = self.backup_view()
        identity = view.selected
        root = self.app.game_path()
        self.app.game.set('/another installation')
        with patch.object(self.app, 'start') as start:
            view.create()
            self.assertEqual(start.call_args.args, ('backup', '--game', root))
            with patch('tkinter.filedialog.askopenfilename', return_value='/tmp/import with spaces.zip'):
                view.import_backup()
            self.assertEqual(start.call_args.args, ('import-backup', '/tmp/import with spaces.zip', '--game', root))
            with patch('tkinter.filedialog.asksaveasfilename', return_value='/tmp/export with spaces.zip'):
                view.export()
            self.assertEqual(start.call_args.args, ('export-backup', identity, '/tmp/export with spaces.zip', '--game', root))
            for method, command in ((view.restore, 'restore-backup'), (view.delete, 'delete-backup')):
                start.reset_mock()
                with patch('tkinter.messagebox.askyesno', return_value=False):
                    method()
                start.assert_not_called()
                with patch('tkinter.messagebox.askyesno', return_value=True):
                    method()
                self.assertEqual(start.call_args.args, (command, identity, '--game', root))
                callback = start.call_args.kwargs['on_complete']
                callback(1)
                self.assertIn('failed', view.notice)
                callback(0)
                self.assertEqual(start.call_args.args, ('backups', '--game', root))
        view.window.destroy()

    def test_three_windows_keep_back_and_footer_actions_visible_at_minimum(self):
        with patch.object(self.app, 'start'):
            backup = self.app.backups()
        views = (self.app.settings(), self.app.achievements(), backup)
        for view in views:
            width, height = (600, 420) if view is views[1] else (640, 520)
            view.window.geometry(f'{width}x{height}')
            self.window.update()
            for button, _ in view.chrome.footer_buttons:
                self.assertTrue(button.winfo_ismapped())
                self.assertGreater(len(button.find_all()), 0)
                self.assertLess(button.winfo_y()+button.winfo_height(), height)
            self.assertTrue(view.chrome.back.winfo_ismapped())
            if view is backup:
                for button, pane in ((view.create_button, view.catalog), (view.import_button, view.catalog),
                                     (view.export_button, view.detail), (view.restore_button, view.detail),
                                     (view.delete_button, view.detail)):
                    # No selected row in this fixture; empty-state detail actions
                    # are disabled, while creating and importing remain visible.
                    if pane is view.catalog:
                        self.assertTrue(button.winfo_ismapped())
                        self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),
                                             pane.canvas.winfo_rooty()+pane.canvas.winfo_height())
            view.window.destroy()

    def test_selected_backup_actions_are_visible_at_minimum(self):
        view, _ = self.backup_view()
        view.window.geometry('640x520')
        self.window.update()
        for button in (view.export_button, view.restore_button, view.delete_button):
            self.assertTrue(button.winfo_ismapped())
            self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),
                                 view.detail.canvas.winfo_rooty()+view.detail.canvas.winfo_height())
        view.window.destroy()


class LanguageSwitcherTests(LauncherGuiFixture):
    def setUp(self):
        self.config = tempfile.TemporaryDirectory()
        self.addCleanup(self.config.cleanup)
        environment = patch.dict('os.environ', {'XDG_CONFIG_HOME': self.config.name})
        environment.start()
        self.addCleanup(environment.stop)
        super().setUp()

    def choose(self, key, code):
        control, variable, choices = self.app.view.language_controls[key]
        control.current(tuple(choices).index(code))
        control.event_generate('<<ComboboxSelected>>')
        self.window.update()

    def test_language_parity_updates_open_forms_and_restores_on_restart(self):
        from re4pc.languages import LAUNCHER_LANGUAGES, translate
        from re4pc.launcher import Launcher
        from re4pc.settings import Settings
        import tkinter as tk
        view = self.app.settings()
        view.editors['window_width'].set('1440')
        original = view.snapshot()
        self.choose('game_language', 'saved')
        for code in LAUNCHER_LANGUAGES:
            with self.subTest(language=code):
                self.choose('launcher_language', code)
                self.assertEqual(Settings.load()['launcher_language'], code)
                self.assertEqual(Settings.load()['game_language'], 'saved')
                self.assertEqual(view.snapshot(), original)
                self.assertIn(translate('Display & sensitivity', code), widget_texts(view.panes[view.section].content))
                self.assertIn(translate('Import APK', code), widget_texts(self.app.import_button))
                self.assertEqual(view.fields['window_mode'][1].get(), translate('Windowed', code))
                self.assertEqual(view.window.title(), translate('Settings & controls', code))
                other = tk.Toplevel(self.window)
                restarted = Launcher(other, self.folder)
                self.assertEqual(restarted.launcher_language, code)
                self.assertEqual(restarted.game_language.get(), 'saved')
                other.destroy()
        view.window.destroy()

    def test_independent_selectors_live_translation_and_restart(self):
        from re4pc.settings import Settings
        self.choose('game_language', 'fr')
        self.choose('launcher_language', 'es')
        self.assertEqual(Settings.load()['game_language'], 'fr')
        self.assertEqual(Settings.load()['launcher_language'], 'es')
        self.assertIn('JUGAR', widget_texts(self.app.play_button))
        self.assertIn('Idioma del juego', widget_texts(self.app.view.canvas))
        self.assertIn('Importar APK', widget_texts(self.app.import_button))
        self.assertTrue(self.app.play_button.instate(['disabled']))
        from re4pc.launcher import Launcher
        import tkinter as tk
        other = tk.Toplevel(self.window)
        restarted = Launcher(other, self.folder)
        self.assertEqual(restarted.launcher_language, 'es')
        self.assertEqual(restarted.game_language.get(), 'fr')
        other.destroy()
        self.choose('launcher_language', 'en')
        self.assertIn('P L A Y', widget_texts(self.app.play_button))
        self.assertEqual(Settings.load()['game_language'], 'fr')

    def test_open_form_survives_and_cannot_overwrite_language(self):
        from re4pc.settings import Settings
        view = self.app.settings()
        view.editors['window_width'].set('1440')
        self.choose('game_language', 'es')
        self.choose('launcher_language', 'es')
        self.assertEqual(view.editors['window_width'].get(), '1440')
        self.assertEqual(view.section, 'Display & sensitivity')
        self.assertIn('Pantalla y sensibilidad', widget_texts(view.panes[view.section].content))
        mode = view.fields['window_mode'][1]
        self.assertEqual(mode.cget('values'), ('Ventana', 'Pantalla completa'))
        mode.current(1)
        mode.event_generate('<<ComboboxSelected>>')
        self.assertEqual(view.editors['window_mode'].get(), 'Fullscreen')
        view.save()
        self.assertEqual(Settings.load()['game_language'], 'es')
        self.assertEqual(Settings.load()['launcher_language'], 'es')
        self.assertEqual(Settings.load()['window_width'], 1440)
        self.assertEqual(Settings.load()['window_mode'], 'fullscreen')

    def test_failed_save_reverts_selection_and_busy_change_preserves_operation(self):
        from re4pc.settings import Settings
        self.choose('game_language', 'ja')
        with patch('re4pc.settings.Settings.save', side_effect=OSError('read only')), \
                patch('tkinter.messagebox.showerror') as error:
            self.choose('game_language', 'de')
        error.assert_called_once()
        self.assertEqual(self.app.game_language.get(), 'ja')
        from re4pc.languages import GAME_LANGUAGES
        self.assertEqual(self.app.view.language_controls['game_language'][0].current(), tuple(GAME_LANGUAGES).index('ja'))
        child = Mock()
        child.poll.return_value = ('', None)
        with patch('re4pc.launcher.ChildProcess', return_value=child):
            self.app.start('run', '--game', self.folder)
        self.choose('launcher_language', 'es')
        self.assertIs(self.app.child, child)
        self.assertTrue(self.app.play_button.instate(['disabled']))
        self.assertIn('JUGANDO', widget_texts(self.app.play_button))
        self.assertTrue(self.app.stop_button.winfo_ismapped())
        self.assertEqual(Settings.load()['game_language'], 'ja')
        self.app.child = None
        self.app.progress.stop()

    def test_selectors_reachable_at_minimum_size(self):
        for geometry in ('1000x600', '1000x800', '1440x810'):
            self.window.geometry(geometry)
            self.window.update()
            self.app.view.draw(self.window.winfo_width(), self.window.winfo_height())
            self.window.update_idletasks()
            for control, _, _ in self.app.view.language_controls.values():
                self.assertTrue(control.winfo_ismapped())
                self.assertGreaterEqual(control.winfo_x(), 0)
                self.assertLessEqual(control.winfo_x()+control.winfo_width(), self.window.winfo_width())
                self.assertLessEqual(control.winfo_y()+control.winfo_height(), self.window.winfo_height())
