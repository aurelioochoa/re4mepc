"""Native Tk launcher; long import, save and game operations run in children."""
import os
import queue
import signal
import subprocess
import sys
import threading
from pathlib import Path

from .paths import game_dir, logs_dir


def child_command(command, *arguments):
    return [sys.executable, '-u', '-m', 're4pc', command, *map(str, arguments)]


class ChildProcess:
    """Bounded output reader. The Tk event loop never waits on a pipe or process."""
    def __init__(self, command):
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True,
                                        errors='replace', bufsize=1)
        self.output = queue.Queue(maxsize=256)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in iter(lambda: self.process.stdout.readline(8192), ''):
                # Bound both the number and length of lines retained by launcher.
                for chunk in (line[i:i + 8192] for i in range(0, len(line), 8192)):
                    try:
                        self.output.put_nowait(chunk)
                    except queue.Full:
                        try:
                            self.output.get_nowait()
                        except queue.Empty:
                            pass
                        try:
                            self.output.put_nowait(chunk)
                        except queue.Full:
                            pass
        finally:
            self.process.stdout.close()

    def poll(self):
        lines = []
        while True:
            try:
                lines.append(self.output.get_nowait())
            except queue.Empty:
                break
        code = self.process.poll()
        # Wait for final stdout in later GUI ticks; no blocking joins in Tk.
        done = code is not None and not self.reader.is_alive() and self.output.empty()
        return ''.join(lines), code if done else None

    def stop(self):
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)

    def kill(self):
        if self.process.poll() is None:
            self.process.kill()


class Launcher:
    def __init__(self, window, game=None):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.window = window
        window.launcher = self
        from .settings import Settings, validate
        try:
            preferences = Settings.load()
            settings_error = None
        except (ValueError, OSError) as error:
            preferences = validate({})
            settings_error = error
        self.launcher_language = preferences['launcher_language']
        self.child = None
        self.on_complete = None
        self.operation_output = ''
        self.last_output = ''
        self.log_output = ''
        self.log_window = None
        self.console = None
        self.buttons = []
        self.operation = None
        self.stopping = False
        self.folder_update = None
        self.kill_job = None
        self.assets = Path(__file__).resolve().parent / 'ui_assets'
        self.configure_style()
        window.title(self.tr('Resident Evil 4 Mobile - Launcher'))
        window.geometry(f'{min(1280, window.winfo_screenwidth())}x{min(720, window.winfo_screenheight())}')
        window.minsize(640, 520)
        window.configure(background=self.colors['background'])
        self.game = tk.StringVar(value=str(game or game_dir()))
        self.status = tk.StringVar(value='Ready')
        self.game_language = tk.StringVar(value=preferences['game_language'])
        self.launcher_language_value = tk.StringVar(value=self.launcher_language)
        self.installation = tk.StringVar()
        from .launcher_ui import CaseFileView
        self.view = CaseFileView(self)
        self.game.trace_add('write', self.folder_changed)
        self.refresh_installation()
        if settings_error:
            self.status.set('Could not load settings: ' + str(settings_error))
        window.protocol('WM_DELETE_WINDOW', self.close)
        self.tick_job = window.after(100, self.tick)
        window.bind('<Destroy>', self.cleanup, add='+')
        window.after_idle(self.warm_artwork)

    def warm_artwork(self):
        """Prepare dialog artwork in the background once the launcher is drawn."""
        from . import ui_images
        from .achievements import ACHIEVEMENTS
        from .launcher_ui import AchievementArtwork
        paper = self.assets / 'case-paper-v2.png'
        ui_images.warm(sources=[(paper if paper.is_file() else self.assets / 'paper.png', 'RGB')] +
                       [(self.assets / (name + '.png'), 'RGBA')
                        for name in ('settings', 'backups', 'case-seal', 'paperclip', 'ribbon-spools')])
        AchievementArtwork(self.assets).warm(ACHIEVEMENTS)

    def tr(self, text):
        from .languages import translate
        return translate(text, self.launcher_language)

    def translated_widget(self, widget):
        text = widget.cget('text')
        widget.translation_source = text
        widget.configure(text=self.tr(text))
        return widget

    def change_language(self, key, code):
        """Reload current settings so an open form cannot overwrite this choice."""
        from .settings import Settings
        from tkinter import messagebox
        try:
            values = Settings.load()
            values[key] = code
            Settings.save(values)
        except (ValueError, OSError) as error:
            self.view.sync_languages()
            messagebox.showerror(self.tr('Cannot save language'), self.tr(str(error)), parent=self.window)
            return False
        self.game_language.set(values['game_language'])
        self.launcher_language_value.set(values['launcher_language'])
        self.launcher_language = values['launcher_language']
        self.status.set('Launcher language saved.' if key == 'launcher_language' else
                        'Game language saved. Applies on next launch.')
        self.retranslate()
        return True

    def retranslate(self):
        from .launcher_ui import ArtworkButton
        from .case_dialog import PaperCanvas
        self.window.title(self.tr('Resident Evil 4 Mobile - Launcher'))
        def update(widget):
            # Native text widgets retain their source for switching back to English.
            title = getattr(widget, 'translation_title', None)
            if title is not None:
                widget.title(self.tr(title))
            source = getattr(widget, 'translation_source', None)
            if source is not None:
                widget.configure(text=self.tr(source))
            if isinstance(widget, ArtworkButton):
                widget.draw()
            elif isinstance(widget, PaperCanvas):
                widget.schedule()
            for child in widget.winfo_children():
                update(child)
        update(self.window)
        for popup in self.window.winfo_children():
            if isinstance(popup, self.tk.Toplevel):
                view = getattr(popup, 'view', None)
                if hasattr(view, 'chrome'):
                    view.chrome.schedule()
                if hasattr(view, 'translate_choices'):
                    view.translate_choices()
        self.view.sync_languages()
        self.view.draw(self.view.canvas.winfo_width(), self.view.canvas.winfo_height())

    def configure_style(self):
        # Native Tk controls, with a shared palette for the launcher and dialogs.
        self.colors = {'background': '#171810', 'panel': '#27271b', 'field': '#11130d',
                       'text': '#eee2c8', 'muted': '#b7ad98', 'accent': '#861b14',
                       'hover': '#a02a20', 'border': '#74674b', 'disabled': '#827967'}
        c = self.colors
        style = self.ttk.Style(self.window)
        style.theme_use('clam')
        style.configure('.', background=c['background'], foreground=c['text'],
                        font=('DejaVu Sans', 10), bordercolor=c['border'],
                        lightcolor=c['border'], darkcolor=c['border'], focuscolor=c['text'])
        style.configure('TFrame', background=c['background'])
        style.configure('Panel.TFrame', background=c['panel'])
        style.configure('TLabel', background=c['background'], foreground=c['text'])
        style.configure('Muted.TLabel', foreground=c['muted'], font=('DejaVu Sans', 9))
        style.configure('PanelHeading.TLabel', background=c['panel'], font=('DejaVu Sans', 11, 'bold'))
        style.configure('PanelMuted.TLabel', background=c['panel'], foreground=c['muted'], font=('DejaVu Sans', 9))
        style.configure('Error.TLabel', foreground='#f0a9a0')
        style.configure('TButton', background='#383727', foreground=c['text'], padding=(14, 10),
                        borderwidth=1, relief='flat', focusthickness=2)
        style.map('TButton', background=[('disabled', '#29281c'), ('pressed', '#292318'), ('active', '#4b4733')],
                  foreground=[('disabled', c['disabled'])], bordercolor=[('focus', c['text'])])
        style.configure('Play.TButton', background=c['accent'], padding=(36, 12), font=('DejaVu Sans', 12, 'bold'))
        style.map('Play.TButton', background=[('disabled', '#453231'), ('pressed', '#883133'), ('active', c['hover'])],
                  foreground=[('disabled', '#b49c98')])
        style.configure('Quiet.TButton', background=c['background'], padding=(10, 7), borderwidth=0)
        style.configure('Achievement.Horizontal.TProgressbar', background=c['accent'], troughcolor=c['field'])
        style.map('Quiet.TButton', background=[('active', '#303832'), ('pressed', '#292318')])
        for name in ('TEntry', 'TCombobox'):
            style.configure(name, fieldbackground=c['field'], foreground=c['text'], padding=9,
                            insertcolor=c['text'], borderwidth=1, selectbackground=c['accent'])
            style.map(name, fieldbackground=[('readonly', c['field']), ('disabled', '#29281c')],
                      foreground=[('readonly', c['text']), ('disabled', c['disabled'])],
                      bordercolor=[('focus', c['text'])])
        style.configure('Language.TCombobox', padding=(6, 2))
        style.configure('TNotebook', borderwidth=0)
        style.configure('TNotebook.Tab', padding=(12, 10), background='#383727', expand=(0, 0, 0, 0))
        style.map('TNotebook.Tab', background=[('selected', c['accent']), ('active', '#4b4733')])
        style.configure('TCheckbutton', padding=6)
        style.configure('TScrollbar', background='#4b4733', troughcolor=c['field'], borderwidth=0)
        style.configure('Activity.Horizontal.TProgressbar', troughcolor=c['panel'], background=c['accent'],
                        borderwidth=0, lightcolor=c['accent'], darkcolor=c['accent'], thickness=3)
        self.window.option_add('*TCombobox*Listbox.background', c['field'])
        self.window.option_add('*TCombobox*Listbox.foreground', c['text'])
        self.window.option_add('*TCombobox*Listbox.selectBackground', c['accent'])

    def button(self, parent, label, command, style='TButton'):
        button = self.translated_widget(self.ttk.Button(parent, text=label, command=command, style=style))
        self.buttons.append(button)
        return button

    def game_path(self):
        value = self.game.get().strip()
        return Path(value).expanduser() if value else None

    def folder_changed(self, *args):
        if self.folder_update:
            self.window.after_cancel(self.folder_update)
        self.folder_update = self.window.after(200, self.refresh_installation)

    def refresh_installation(self):
        from .assets import LIBRARIES, REQUIRED
        if self.folder_update:
            self.window.after_cancel(self.folder_update)
        self.folder_update = None
        root = self.game_path()
        found = root is not None and all((root / 'lib' / name).is_file() for name in LIBRARIES)
        found = found and all((root / 'data/monhun' / name).is_file() for name in REQUIRED)
        self.installation.set('Game files found' if found else 'Import needed')
        enabled = found and self.child is None
        for button in (self.play_button, self.diagnostics_button, self.backups_button, self.achievements_button):
            button.configure(state='normal' if enabled else 'disabled')
        if self.child is None:
            self.play_button.configure(text='Play')
        self.view.update_status()
        return found

    def append(self, text):
        self.log_output = (self.log_output + text)[-128 * 1024:]
        if self.console is not None and self.console.winfo_exists():
            self.console.configure(state='normal')
            self.console.insert('end', text)
            count = self.console.count('1.0', 'end-1c', 'chars')[0]
            if count > 128 * 1024:
                self.console.delete('1.0', '1.0 + ' + str(count - 128 * 1024) + ' chars')
            if int(self.console.index('end-1c').split('.')[0]) > 1500:
                self.console.delete('1.0', '500.0')
            self.console.see('end')
            self.console.configure(state='disabled')

    def show_logs(self):
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.deiconify()
            self.log_window.lift()
            return
        popup = self.dialog('Launcher logs', '820x460')
        self.log_window = popup
        frame = self.ttk.Frame(popup, padding=16)
        frame.pack(fill='both', expand=True)
        self.translated_widget(self.ttk.Label(frame, text='Session output', style='PanelHeading.TLabel')).pack(anchor='w')
        self.translated_widget(self.ttk.Label(frame, text='Logs are optional. You can close this window while an operation runs.',
                       style='Muted.TLabel')).pack(anchor='w', pady=(6, 12))
        body = self.ttk.Frame(frame)
        body.pack(fill='both', expand=True)
        self.console = self.tk.Text(body, wrap='word', height=14, font=('DejaVu Sans Mono', 9),
                                    background=self.colors['field'], foreground=self.colors['text'],
                                    insertbackground=self.colors['text'], relief='flat', padx=12, pady=12)
        scrollbar = self.ttk.Scrollbar(body, command=self.console.yview)
        self.console.configure(yscrollcommand=scrollbar.set)
        self.console.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        self.console.insert('end', self.log_output or self.tr('No operations have run in this session.\n'))
        self.console.configure(state='disabled')
        self.translated_widget(self.ttk.Button(frame, text='Close', command=popup.destroy)).pack(anchor='e', pady=(12, 0))

    def dialog(self, title, geometry):
        from .desktop import WINDOW_CLASS
        popup = self.tk.Toplevel(self.window, class_=WINDOW_CLASS)
        popup.launcher = self
        popup.translation_title = title
        popup.title(self.tr(title))
        popup.geometry(geometry)
        popup.configure(background=self.colors['background'])
        popup.transient(self.window)
        return popup

    def apply_icon(self):
        from PIL import Image, ImageTk
        from .desktop import locations, inspect_icon
        path = locations()[2]
        try:
            data = path.read_bytes()
            inspect_icon(data)
        except (OSError, ValueError):
            path = self.assets / 'icon.png'
        with Image.open(path) as source:
            image = source.convert('RGBA')
        self.app_icon = ImageTk.PhotoImage(image.resize((64, 64), Image.Resampling.LANCZOS), master=self.window)
        self.window.iconphoto(True, self.app_icon)

    def show_icons(self):
        from .launcher_ui import IconPickerView
        return IconPickerView(self)

    def scrolling_pane(self, parent):
        """Keep settings reachable at small window sizes without global bindings."""
        outer = self.ttk.Frame(parent)
        canvas = self.tk.Canvas(outer, background=self.colors['background'], highlightthickness=0)
        scrollbar = self.ttk.Scrollbar(outer, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        content = self.ttk.Frame(canvas, padding=12)
        identity = canvas.create_window(0, 0, anchor='nw', window=content)
        content.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(identity, width=event.width))
        return outer, content, canvas

    def start(self, command, *arguments, on_complete=None):
        from tkinter import messagebox
        if self.child is not None:
            return
        try:
            self.child = ChildProcess(child_command(command, *arguments))
        except OSError as error:
            messagebox.showerror(self.tr('Cannot start'), self.tr(str(error)), parent=self.window)
            return
        self.operation = command
        self.stopping = False
        self.on_complete = on_complete
        self.operation_output = ''
        descriptions = {'run': 'Game is running. Use the game window to play.', 'import': 'Importing your APK…',
                        'backups': 'Loading save backups…', 'backup': 'Creating a save snapshot…',
                        'export-backup': 'Exporting backup…', 'restore-backup': 'Restoring saves…',
                        'import-backup': 'Importing backup…', 'delete-backup': 'Deleting snapshot…',
                        'export-achievements': 'Exporting achievement captures…'}
        self.status.set(descriptions.get(command, 'Working…'))
        self.status_label.configure(style='TLabel')
        self.buttons[:] = [button for button in self.buttons if button.winfo_exists()]
        for button in self.buttons:
            button.configure(state='disabled')
        self.game_entry.configure(state='disabled')
        self.stop_button.configure(state='normal')
        if command == 'run':
            self.play_button.configure(text='Playing')
        self.progress.start(18)
        self.append('\n' + command.capitalize() + '\n')
        self.view.update_status()
        self.sync_dialogs()

    def sync_dialogs(self):
        for popup in self.window.winfo_children():
            view = getattr(popup, 'view', None)
            if hasattr(view, 'busy_changed'):
                view.busy_changed()

    def tick(self):
        if self.child is not None:
            output, code = self.child.poll()
            if output:
                self.operation_output = (self.operation_output + output)[-2 * 1024 * 1024:]
                self.append(output)
            if code is not None:
                self.last_output = self.operation_output
                callback, self.on_complete = self.on_complete, None
                operation = self.operation
                stopped = self.stopping
                self.child = None
                if self.kill_job:
                    self.window.after_cancel(self.kill_job)
                    self.kill_job = None
                self.progress.stop()
                self.progress.configure(value=0)
                self.buttons[:] = [button for button in self.buttons if button.winfo_exists()]
                for button in self.buttons:
                    button.configure(state='normal')
                self.game_entry.configure(state='normal')
                self.stop_button.configure(state='disabled')
                success = {'run': 'Game closed. Ready to play again.', 'import': 'Import complete. Ready to play.',
                           'backups': 'Save backups loaded.', 'backup': 'Save snapshot created.',
                           'export-backup': 'Backup exported.', 'restore-backup': 'Saves restored.',
                           'import-backup': 'Backup imported.', 'delete-backup': 'Snapshot deleted.',
                           'export-achievements': 'Achievement captures exported.'}
                self.status.set('Operation stopped.' if stopped else success.get(operation, 'Complete.') if code == 0
                                else 'Operation failed. Open View logs for details, then try again.')
                self.status_label.configure(style='Error.TLabel' if code and not stopped else 'TLabel')
                self.refresh_installation()
                if callback:
                    callback(code)
                self.sync_dialogs()
        self.tick_job = self.window.after(100, self.tick)

    def cleanup(self, event):
        if event.widget is self.window:
            from . import ui_images
            ui_images.shutdown()
            self.view.cleanup()
            self.window.after_cancel(self.tick_job)
            if self.folder_update:
                self.window.after_cancel(self.folder_update)
            if self.kill_job:
                self.window.after_cancel(self.kill_job)

    def browse(self):
        from tkinter import filedialog
        value = filedialog.askdirectory(parent=self.window, title=self.tr('Choose imported game folder'))
        if value:
            self.game.set(value)

    def achievements(self):
        from .launcher_ui import AchievementsView
        root = self.game_path()
        if root is None or self.child:
            return
        return AchievementsView(self, root)

    def import_apk(self):
        from tkinter import filedialog, simpledialog, messagebox
        apk = filedialog.askopenfilename(parent=self.window, title=self.tr('Select your game APK'),
                                         filetypes=[(self.tr('Android APK'), '*.apk'), (self.tr('All files'), '*')])
        if not apk:
            return
        destination = self.game_path() or game_dir()
        original = destination
        index = 2
        while os.path.lexists(destination):
            destination = original.with_name(original.name + '-' + str(index))
            index += 1
        output = simpledialog.askstring(self.tr('Import APK'), self.tr('Import into a new folder. Existing installations and saves are preserved.'),
                                        initialvalue=str(destination), parent=self.window)
        if not output or not output.strip():
            return
        output = str(Path(output.strip()).expanduser())
        if os.path.lexists(output):
            messagebox.showerror(self.tr('Choose a new folder'), self.tr('This folder already exists. Choose an unused folder for your import.'), parent=self.window)
            return
        def imported(code):
            if code == 0:
                self.game.set(output)
                self.refresh_installation()
        self.start('import', apk, '--output', output, on_complete=imported)

    def play(self):
        if self.refresh_installation():
            self.start('run', '--game', self.game_path())

    def diagnostics(self):
        import datetime
        output = logs_dir() / ('launcher-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            from tkinter import messagebox
            messagebox.showerror(self.tr('Cannot create diagnostics'), self.tr(str(error)), parent=self.window)
            return
        self.append('Diagnostics folder: ' + str(output) + '\nF3 toggles the in-game diagnostics overlay.\n')
        self.start('run', '--game', self.game_path(), '--profile', output / 'profile.jsonl',
                   '--stats', output / 'stats.json', '--log-file', output / 'runtime.log')

    def backups(self):
        from .launcher_ui import BackupsView
        root = self.game_path()
        if root is None or self.child:
            return
        return BackupsView(self, root)

    def settings(self):
        from .settings import Settings
        from .launcher_ui import SettingsView
        from tkinter import messagebox
        import ctypes as C
        try:
            values = Settings.load()
            sdl = C.CDLL('libSDL2-2.0.so.0')
            sdl.SDL_GetKeyName.argtypes = (C.c_int,)
            sdl.SDL_GetKeyName.restype = C.c_char_p
            sdl.SDL_GetKeyFromName.argtypes = (C.c_char_p,)
            sdl.SDL_GetKeyFromName.restype = C.c_int
        except (ValueError, OSError) as error:
            messagebox.showerror(self.tr('Cannot open settings'), self.tr(str(error)), parent=self.window)
            return
        return SettingsView(self, values, sdl)

    def stop(self):
        if self.child and not self.stopping:
            child = self.child
            self.stopping = True
            self.status.set('Stopping. Please wait…')
            self.stop_button.configure(state='disabled')
            child.stop()
            self.kill_job = self.window.after(3000, lambda: child.kill() if self.child is child else None)

    def close(self):
        from tkinter import messagebox
        from .launcher_ui import SettingsView
        if self.child and not messagebox.askyesno(
                self.tr('Operation in progress'), self.tr('Stop the active operation and close the launcher?'), parent=self.window):
            return
        for popup in self.window.winfo_children():
            view = getattr(popup, 'view', None)
            if isinstance(view, SettingsView) and not view.can_close():
                return
        if self.child:
            self.stop()
            self.window.after(100, self._close_when_stopped)
        else:
            self.window.destroy()

    def _close_when_stopped(self):
        if self.child:
            self.window.after(100, self._close_when_stopped)
        else:
            self.window.destroy()


def configure_bundled_fonts():
    """Add package fonts explicitly; old Fontconfig resolves relative dirs to cwd."""
    fonts = Path(sys.prefix) / 'share/fonts'
    if not fonts.is_dir():
        return
    import ctypes as C
    fontconfig = C.CDLL('libfontconfig.so.1')
    fontconfig.FcConfigAppFontAddDir.argtypes = (C.c_void_p, C.c_char_p)
    fontconfig.FcConfigAppFontAddDir.restype = C.c_int
    if not fontconfig.FcConfigAppFontAddDir(None, os.fsencode(fonts)):
        raise RuntimeError('Cannot register bundled launcher fonts')


def launch(game=None, smoke_test=False):
    import tkinter as tk
    from .desktop import WINDOW_CLASS
    configure_bundled_fonts()
    try:
        # Match the installed desktop entry so GNOME uses its selected icon.
        window = tk.Tk(className=WINDOW_CLASS)
    except tk.TclError as error:
        raise RuntimeError('The launcher needs a graphical display: ' + str(error)) from error
    Launcher(window, game)
    if smoke_test:
        window.after(500, window.destroy)
    window.mainloop()
    return 0
