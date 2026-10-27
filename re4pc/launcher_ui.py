"""Case-file presentation for the native launcher, with keyboard operable controls."""
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageOps, ImageTk
from .languages import GAME_LANGUAGES, LAUNCHER_LANGUAGES, widget_translate
from . import ui_images


INK = '#211b13'
IVORY = '#eee2c8'
MUTED = '#b7ad98'
RED = '#78190f'


class ArtworkButton(tk.Canvas):
    """A real focusable widget whose surface continues the artwork beneath it."""
    def __init__(self, parent, text, command, *, kind='quiet', detail='', icon=None):
        super().__init__(parent, highlightthickness=0, borderwidth=0,
                         takefocus=True, cursor='hand2', background='#171810')
        self.label, self.command = text, command
        self.kind, self.detail, self.icon = kind, detail, icon
        self.enabled, self.hovered, self.pressed = True, False, False
        self.selected = False
        self.scale = 1
        self.surface = None
        self.ink_source = None
        self.paint_surface = None
        self.bind('<Enter>', lambda event: self.feedback(hover=True))
        self.bind('<Leave>', lambda event: self.feedback(hover=False, pressed=False))
        self.bind('<ButtonPress-1>', self.press)
        self.bind('<ButtonRelease-1>', self.release)
        self.bind('<FocusIn>', lambda event: self.draw())
        self.bind('<FocusOut>', lambda event: self.draw())
        self.bind('<space>', self.activate)
        self.bind('<Return>', self.activate)
        self.bind('<Configure>', lambda event: self.draw())

    def configure(self, cnf=None, **options):
        if cnf:
            options.update(cnf)
        if 'text' in options:
            self.label = options.pop('text')
        if 'state' in options:
            self.enabled = options.pop('state') != 'disabled'
            super().configure(takefocus=self.enabled, cursor='hand2' if self.enabled else '')
        result = super().configure(**options) if options else None
        if hasattr(self, 'enabled'):
            self.draw()
        return result

    config = configure

    def cget(self, key):
        if key == 'text':
            return self.label
        if key == 'state':
            return 'normal' if self.enabled else 'disabled'
        return super().cget(key)

    def instate(self, states):
        return all((not self.enabled if state == 'disabled' else self.enabled)
                   for state in states if state in ('disabled', '!disabled'))

    def invoke(self):
        if self.enabled:
            return self.command()

    def activate(self, event):
        self.invoke()
        return 'break'

    def feedback(self, *, hover=None, pressed=None):
        if hover is not None:
            self.hovered = hover
        if pressed is not None:
            self.pressed = pressed
        self.draw()

    def press(self, event):
        if self.enabled:
            self.focus_set()
            self.feedback(pressed=True)

    def release(self, event):
        pressed = self.pressed
        self.feedback(pressed=False)
        if pressed and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.invoke()

    def position(self, image, bounds, scale):
        x, y, width, height = bounds
        self.scale = scale
        self.surface = ImageTk.PhotoImage(image.crop((x, y, x + width, y + height)))
        if self.ink_source:
            self.paint_surface = ImageTk.PhotoImage(self.ink_source.resize((width, height), Image.Resampling.LANCZOS))
        self.place(x=x, y=y, width=width, height=height)
        self.draw()

    def draw(self):
        self.delete('all')
        if self.surface:
            self.create_image(0, 0, image=self.surface, anchor='nw')
            if self.kind == 'section' and self.selected:
                from PIL import Image as PILImage
                base = ImageTk.getimage(self.surface).convert('RGB')
                self.selection_surface = ImageTk.PhotoImage(PILImage.blend(base, PILImage.new('RGB', base.size, RED), .12))
                self.create_image(0, 0, image=self.selection_surface, anchor='nw')
        width, height = self.winfo_width(), self.winfo_height()
        # place() sizes are available after geometry settles; the image is immediate.
        if self.surface:
            width, height = self.surface.width(), self.surface.height()
        s = self.scale
        active = self.enabled and (self.hovered or self.pressed)
        offset = 1 if self.pressed else 0
        font = lambda size, family='DejaVu Serif': (family, -max(10, round(size * s)))
        if self.kind == 'play':
            color = '#a02a20' if active else RED if self.enabled else '#62463a'
            self.create_rectangle(0, 0, width, height, fill=color, outline='#9e3828')
            if self.paint_surface:
                self.create_image(0, 0, image=self.paint_surface, anchor='nw')
                if active or not self.enabled:
                    self.create_rectangle(0, 0, width, height, fill=color, outline='', stipple='gray50')
            label = widget_translate(self, self.label)
            text = 'P L A Y' if label == 'Play' else label.upper()
            self.create_text(width / 2 + 27 * s, height / 2 + offset, text=text,
                             font=font(42), fill=IVORY)
            x, y = width / 2 - 92 * s, height / 2 + offset
            self.create_polygon(x - 15 * s, y - 18 * s, x - 15 * s, y + 18 * s,
                                x + 17 * s, y, fill=IVORY, outline='')
        elif self.kind in ('primary', 'paper-outline', 'danger', 'section', 'segment'):
            paper = self.kind in ('paper-outline', 'danger', 'section', 'segment')
            selected = self.selected or (self.kind == 'primary')
            color = IVORY if selected else RED if self.kind == 'danger' else INK
            if (selected or active) and not (self.kind == 'section' and selected):
                self.create_rectangle(1, 1, width - 1, height - 1,
                                      fill=RED if selected else '#977743',
                                      stipple='gray12' if self.kind == 'section' or not selected else '', outline='')
            if self.kind == 'section' and selected:
                self.create_rectangle(0, 0, 5, height, fill=RED, outline='')
                color = INK
            if self.kind != 'section':
                self.create_rectangle(1, 1, width - 2, height - 2,
                                      outline=RED if self.kind == 'danger' else '#887757')
            if not self.enabled:
                color = '#827967'
            self.create_text(18 if self.kind == 'section' else width / 2,
                             height / 2 + offset, text=self.label, fill=color,
                             font=font(20 if self.kind == 'section' else 18),
                             anchor='w' if self.kind == 'section' else 'center',
                             width=max(60, width-52) if self.kind == 'section' else max(60, width-12))
            if self.kind == 'section' and selected:
                self.create_text(width - 20, height / 2, text='›', fill=color, font=font(26))
        elif self.kind == 'paper-compact':
            if active:
                self.create_rectangle(1, 1, width - 1, height - 1,
                                      fill='#977743', stipple='gray12', outline='')
            self.create_text(width / 2, height / 2 + offset, text=self.label,
                             font=font(17), fill=INK if self.enabled else '#78654b',
                             width=width - 12)
        elif self.kind == 'paper':
            if active:
                self.create_rectangle(1, 1, width - 1, height - 1,
                                      fill='#977743', stipple='gray12', outline='')
            if self.icon:
                self.create_image(27 * s, height / 2, image=self.icon)
            color = INK if self.enabled else '#78654b'
            self.create_text(82 * s, 30 * s + offset, text=self.label, anchor='w',
                             font=font(25), fill=color)
            self.create_text(82 * s, 56 * s + offset, text=self.detail, anchor='w',
                             font=font(18), fill=color)
            self.create_text(width - 10 * s, height / 2, text='›', font=font(40), fill=color)
        else:
            color = IVORY if self.enabled else '#827967'
            if self.kind == 'nav' and not (self.selected or active):
                color = MUTED if self.enabled else '#827967'
            if active and self.kind in ('outline', 'stop'):
                self.create_rectangle(1, 1, width - 1, height - 1,
                                      fill='#534b33', stipple='gray25', outline='')
            size = 20 if self.kind == 'nav' else 18
            self.create_text(width / 2, height / 2 + offset, text=self.label,
                             fill=color, font=font(size))
            if self.kind in ('outline', 'stop'):
                self.create_rectangle(1, 1, width - 2, height - 2, outline='#bbaa83')
            if self.kind == 'nav' and self.selected:
                self.create_line(10 * s, height - 2, width - 10 * s, height - 2,
                                 fill='#a33525', width=max(2, round(2 * s)))
            if self.kind == 'quiet':
                self.create_line(9 * s, height - 7 * s, width - 9 * s, height - 7 * s,
                                 fill='#9d8860')
        if self.enabled and self.focus_get() is self:
            self.create_rectangle(3, 3, width - 4, height - 4,
                                  outline='#6b3c19' if self.kind in ('paper', 'paper-compact', 'paper-outline', 'danger', 'section', 'segment') else IVORY,
                                  dash=(3, 3), width=2)

    def create_text(self, *args, **options):
        if 'text' in options:
            options['text'] = widget_translate(self, options['text'])
        if len(str(options.get('text', ''))) > 1 and self.winfo_width() > 30:
            from tkinter.font import Font
            available = options.get('width') or self.winfo_width() - (
                112 * self.scale if self.kind == 'paper' else 120 * self.scale if self.kind == 'play' else 16)
            face = Font(root=self, font=options['font'])
            size = abs(face.cget('size'))
            measured = face.measure(options['text'])
            if measured > available:
                face.configure(size=-max(12 if self.kind == 'section' else 9,
                                         int(size * available / measured)))
                # Copy the descriptor; Tk must not retain a temporary named font.
                options['font'] = (face.cget('family'), face.cget('size'))
        return super().create_text(*args, **options)


class IconChoice(ArtworkButton):
    """Focusable icon artwork with separate selection and keyboard focus states."""
    def draw(self):
        self.delete('all')
        if self.surface:
            self.create_image(0, 0, image=self.surface, anchor='nw')
        width, height = self.winfo_width(), self.winfo_height()
        if self.hovered or self.pressed or self.selected:
            self.create_rectangle(1, 1, width-1, height-1, fill=RED if self.selected else '#977743',
                                  stipple='gray12', outline='')
        if self.selected or self.hovered:
            self.create_rectangle(1, 1, width-2, height-2,
                                  outline=RED if self.selected else '#887757',
                                  width=2 if self.selected else 1)
        offset = int(self.pressed)
        if self.icon:
            self.create_image(width/2, 65+offset, image=self.icon)
        self.create_text(width/2, 128+offset, text=self.label, fill=INK,
                         font=('DejaVu Serif', -16), width=max(1, width-16))
        if self.selected:
            self.create_text(width/2, 151, text='✓', fill=RED, font=('DejaVu Sans', -16))
        if self.focus_get() is self:
            self.create_rectangle(5, 5, width-6, height-6, outline=RED, dash=(3, 3))


class IconPickerView:
    """Compact case-file picker; selection is persisted as soon as it succeeds."""
    CHOICES = (('icon.png', 'Classic 4'), ('icon-village.png', 'Blood moon'),
               ('icon-seal.png', 'Crimson seal'), ('icon-bell.png', 'Church bell'))

    def __init__(self, app):
        from .case_dialog import PaperCanvas
        from .desktop import locations, inspect_icon
        self.app = app
        self.window = app.dialog('Launcher icon', '680x400')
        self.window.view = self
        self.window.minsize(600, 400)
        self.window.bind('<Escape>', lambda event: self.window.destroy())
        self.paper = PaperCanvas(self.window, app.assets, render=self.draw)
        self.paper.pack(fill='both', expand=True, padx=8, pady=8)
        self.notice = app.tk.StringVar(value='Choose an icon or select your own PNG.')
        self.notice.trace_add('write', lambda *args: self.paper.schedule())
        self.error = False
        try:
            current = locations()[2].read_bytes()
            inspect_icon(current)
        except (OSError, ValueError):
            current = (app.assets / 'icon.png').read_bytes()
        self.choices = []
        for index, (filename, label) in enumerate(self.CHOICES):
            path = app.assets / filename
            image = ui_images.contained(ui_images.source(path, 'RGBA'), (96, 96))
            preview = ImageTk.PhotoImage(image, master=self.window)
            button = IconChoice(self.paper, label, lambda path=path: self.select(path), icon=preview)
            button.selected = current == path.read_bytes()
            button.bind('<Left>', lambda event, i=index: self.navigate(i-1))
            button.bind('<Right>', lambda event, i=index: self.navigate(i+1))
            self.choices.append(button)
        self.browse_button = ArtworkButton(self.paper, 'Choose PNG…', self.browse, kind='paper-outline')
        self.done_button = ArtworkButton(self.paper, 'Done', self.window.destroy, kind='primary')
        self.window.update_idletasks()
        width, height = self.window.winfo_width(), self.window.winfo_height()
        x = app.window.winfo_rootx() + (app.window.winfo_width()-width)//2
        y = app.window.winfo_rooty() + (app.window.winfo_height()-height)//2
        self.window.geometry(f'+{max(0, min(x, self.window.winfo_screenwidth()-width))}'
                             f'+{max(0, min(y, self.window.winfo_screenheight()-height-40))}')
        next((button for button in self.choices if button.selected), self.choices[0]).focus_set()

    def navigate(self, index):
        self.choices[index % len(self.choices)].focus_set()
        return 'break'

    def select(self, path):
        from .desktop import save_icon
        try:
            data = Path(path).read_bytes()
            save_icon(data)
            self.app.apply_icon()
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            self.error = True
            self.notice.set(self.app.tr('Could not save icon: ') + str(error))
            return
        self.error = False
        for button, (filename, _) in zip(self.choices, self.CHOICES):
            button.selected = data == (self.app.assets / filename).read_bytes()
            button.draw()
        self.notice.set('Icon saved.')

    def browse(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self.window, title=self.app.tr('Choose a PNG icon'),
                                          filetypes=[('PNG', '*.png')])
        if path:
            self.select(path)

    def draw(self):
        from .case_dialog import MUTED, RED
        width, height = self.paper.surface()
        self.paper.text(24, 22, 'Choose your launcher icon', size=26)
        self.paper.text(24, 61, 'Changes apply immediately and are remembered next time.',
                        size=14, color=MUTED, family='DejaVu Sans', width=width-48)
        gap = 10
        card_width = (width-48-gap*3)/4
        for index, button in enumerate(self.choices):
            self.paper.window(button, round(24+index*(card_width+gap)), 96, round(card_width), 174)
        self.paper.text(24, 281, self.notice.get(), size=13, color=RED if self.error else MUTED,
                        family='DejaVu Sans', width=width-48)
        self.paper.rule(height-66, x=24, end=width-24)
        self.paper.window(self.browse_button, 24, height-52, 148, 36)
        self.paper.window(self.done_button, width-128, height-52, 104, 36)


class CaseFileView:
    """Recompose the case file to fill wide, short and portrait windows."""
    def __init__(self, launcher):
        self.app = launcher
        self.canvas = tk.Canvas(launcher.window, highlightthickness=0, background='#15160f')
        self.canvas.pack(fill='both', expand=True)
        self.source = None
        self.icon_sources = {}
        self.image = None
        self.buttons = []
        self.nav = {}
        self.layout_job = None
        # Decode the launcher's artwork in parallel; the loads below then share it.
        icons = (('settings', 'settings.png'), ('backups', 'backups.png'),
                 ('achievements', 'achievement-platinum.png'))
        for future in ui_images.warm(sources=[(launcher.assets / name, mode) for name, mode in (
                ('case-file.png', 'RGB'),
                ('icon.png', None), *((filename, 'RGBA') for _, filename in icons))]):
            future.result()
        try:
            self.source = ui_images.source(launcher.assets / 'case-file.png', 'RGB')
        except OSError:
            # Source checkouts with missing artwork still have the complete UI.
            self.source = Image.new('RGB', (1672, 941), '#171810')
            from PIL import ImageDraw, ImageOps
            draw = ImageDraw.Draw(self.source)
            draw.rectangle((24, 82, 797, 852), fill='#e5d1ac')
            try:
                with Image.open(launcher.assets / 'forest.png') as image:
                    self.source.paste(ImageOps.fit(image.convert('RGB'), (800, 508)), (838, 99))
            except OSError:
                pass
        launcher.banner_source = self.source
        for name, filename in icons:
            try:
                self.icon_sources[name] = ui_images.source(launcher.assets / filename, 'RGBA')
            except OSError:
                pass
        try:
            launcher.apply_icon()
        except (OSError, ValueError):
            pass
        for text, bounds, section in (
                ('Overview', (251, 0, 127, 52), 'overview'),
                ('Settings & controls', (416, 0, 198, 52), 'settings'),
                ('Save backups', (630, 0, 144, 52), 'backups'),
                ('Installation', (805, 0, 134, 52), 'installation'),
                ('Achievements', (965, 0, 166, 52), 'achievements')):
            self.nav[section] = self.action(text, lambda section=section: self.open_section(section), bounds, kind='nav')
        self.nav['overview'].selected = True
        launcher.play_button = self.action('Play', launcher.play, (81, 465, 647, 88), kind='play')
        launcher.achievements_button = self.action('Achievements', lambda: self.open_section('achievements'),
                                                  (84, 557, 646, 78), kind='paper',
                                                  detail='View unlocks, progress and captures.')
        self.settings_button = self.action('Settings & controls', lambda: self.open_section('settings'),
                                          (84, 653, 646, 78), kind='paper',
                                          detail='Display, mouse, keyboard and controller.')
        launcher.backups_button = self.action('Save backups', lambda: self.open_section('backups'),
                                             (84, 752, 646, 78), kind='paper',
                                             detail='Create, export or restore your saves.')
        launcher.game_entry = launcher.ttk.Entry(self.canvas, textvariable=launcher.game)
        self.language_controls = {}
        for key, choices in (('game_language', GAME_LANGUAGES), ('launcher_language', LAUNCHER_LANGUAGES)):
            variable = tk.StringVar()
            control = launcher.ttk.Combobox(self.canvas, textvariable=variable, state='readonly',
                                           style='Language.TCombobox')
            control.bind('<<ComboboxSelected>>', lambda event, key=key, choices=choices:
                         launcher.change_language(key, tuple(choices)[event.widget.current()]))
            self.language_controls[key] = (control, variable, choices)
        self.sync_languages()
        self.browse_button = self.action('Browse', launcher.browse, (1296, 737, 151, 48), kind='outline')
        launcher.import_button = self.action('Import APK', launcher.import_apk, (1472, 737, 160, 48), kind='outline')
        launcher.diagnostics_button = self.action('Diagnostics', launcher.diagnostics, (170, 884, 100, 39))
        self.logs_button = self.action('View logs', launcher.show_logs, (294, 884, 92, 39), busy=False)
        self.icon_button = self.action('Launcher icon', launcher.show_icons, (400, 884, 120, 39), busy=False)
        launcher.stop_button = self.action('Stop', launcher.stop, (1542, 821, 90, 38), kind='stop', busy=False)
        launcher.stop_button.configure(state='disabled')
        # Dialog/process code shares this style state; visible status is drawn on canvas.
        launcher.status_label = launcher.ttk.Label(self.canvas, textvariable=launcher.status)
        launcher.progress = launcher.ttk.Progressbar(self.canvas, mode='indeterminate',
                                                    style='Activity.Horizontal.TProgressbar')
        launcher.status.trace_add('write', self.update_status)
        launcher.installation.trace_add('write', self.update_status)
        self.canvas.bind('<Configure>', self.schedule_layout)
        launcher.game_entry.bind('<FocusIn>', lambda event: self.select('installation'))
        self.draw(1280, 720)

    def action(self, text, callback, bounds, *, busy=True, **options):
        button = ArtworkButton(self.canvas, text, callback, **options)
        self.buttons.append((button, bounds))
        if busy:
            self.app.buttons.append(button)
        return button

    def select(self, section):
        for key, button in self.nav.items():
            button.selected = key == section
            button.draw()

    def sync_languages(self):
        for key, (control, variable, choices) in self.language_controls.items():
            control.configure(values=tuple(self.app.tr(label) for label in choices.values()))
            code = getattr(self.app, key if key == 'game_language' else 'launcher_language_value').get()
            control.current(tuple(choices).index(code))

    def open_section(self, section):
        self.select(section)
        if section == 'overview':
            (self.app.play_button if self.app.play_button.enabled else self.app.import_button).focus_set()
            return
        if section == 'installation':
            self.app.game_entry.focus_set()
            self.app.game_entry.selection_range(0, 'end')
            return
        previous = set(self.app.window.winfo_children())
        getattr(self.app, section)()
        for popup in set(self.app.window.winfo_children()) - previous:
            if isinstance(popup, tk.Toplevel):
                popup.bind('<Destroy>', lambda event, popup=popup:
                           self.select('overview') if event.widget is popup else None, add='+')

    def schedule_layout(self, event):
        if self.layout_job:
            self.canvas.after_cancel(self.layout_job)
        self.layout_job = self.canvas.after(35, lambda: self.draw(event.width, event.height))

    def draw(self, width, height):
        if self.layout_job:
            self.canvas.after_cancel(self.layout_job)
        self.layout_job = None
        if width < 2 or height < 2:
            return
        self.scale, self.origin = 1, (0, 0)
        self.stacked = width < 900
        ui = min(1.25, max(.85, min(width / 1280, height / 720)))
        margin = 14 if self.stacked else max(14, round(24 * ui))
        gap = margin
        header, footer = round(48 * ui), round(46 * ui)
        top, bottom = header + margin, height - footer - margin
        area = bottom - top
        if self.stacked:
            paper_height = max(176, round(area * .43))
            # Reserve real space for both language selectors, installation and
            # operation feedback before giving any room to decoration.
            paper_height = min(paper_height, area - gap - 214)
            paper = (margin, top, width - margin * 2, paper_height)
            right = (margin, top + paper_height + gap, width - margin * 2,
                     area - paper_height - gap)
        else:
            paper_width = round((width - margin * 2 - gap) * .47)
            paper = (margin, top, paper_width, area)
            right = (margin + paper_width + gap, top,
                     width - margin * 2 - gap - paper_width, area)

        # Only the presentation stretches/crops. Controls use independent bounds
        # and readable type, rather than inheriting a fixed image aspect ratio.
        background = self.source.crop((839, 650, 1672, 941))
        self.scaled = ImageOps.fit(background, (width, height), Image.Resampling.LANCZOS)
        self.scaled = Image.blend(self.scaled, Image.new('RGB', (width, height), '#15160f'), .4)
        px, py, pw, ph = paper
        sheet = self.source.crop((20, 78, 804, 858))
        paper_texture = sheet.crop((0, 300, sheet.width, sheet.height)) if self.stacked else sheet
        self.scaled.paste(ImageOps.fit(paper_texture, (pw, ph), Image.Resampling.LANCZOS), (px, py))
        rx, ry, rw, rh = right
        block_height = round(224 * ui) if not self.stacked else 214
        form_y = bottom - block_height
        photo_height = form_y - ry - gap
        if photo_height >= 100:
            frame = max(5, round(9 * ui))
            photograph = ImageOps.fit(self.source.crop((839, 109, 1623, 598)),
                                      (rw - frame * 2, photo_height - frame * 2),
                                      Image.Resampling.LANCZOS, centering=(.5, .35))
            self.scaled.paste(sheet.resize((rw, photo_height), Image.Resampling.LANCZOS), (rx, ry))
            self.scaled.paste(photograph, (rx + frame, ry + frame))
        self.image = ImageTk.PhotoImage(self.scaled)
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, image=self.image, anchor='nw', tags='backdrop')
        self.bounds = {}

        def label(x, y, text, size=16, **options):
            return self.text(x, y, text, round(size * ui), **options)

        def position(button, bounds, scale=ui):
            x, y, w, h = bounds
            # Round shared edges together so adjacent actions never overlap by
            # one pixel at fractional widths or display scales.
            bounds = (round(x), round(y), round(x + w) - round(x), round(y + h) - round(y))
            button.position(self.scaled, bounds, scale)
            self.bounds[button] = bounds

        label(margin, header / 2, 'r e 4 m e p c', 18, anchor='w')
        self.line(0, header, width, header, '#514a37')
        # On narrow windows the three utility actions already live on the paper.
        # Keep a direct route to the folder without repeating them in a tight row.
        visible_nav = ('installation',) if self.stacked else tuple(self.nav)
        nav_x = round(158 * ui) if not self.stacked else width - margin - 140
        available = width - margin - nav_x
        from tkinter.font import Font
        face = Font(root=self.canvas, family='DejaVu Serif', size=-round(16 * ui))
        weights = {key: face.measure(self.app.tr(self.nav[key].label)) + 24 for key in visible_nav}
        total = sum(weights.values())
        for key, button in self.nav.items():
            if key not in visible_nav:
                if self.app.window.focus_get() is button:
                    target = {'overview': self.app.play_button if self.app.play_button.enabled else self.app.import_button,
                              'settings': self.settings_button, 'backups': self.app.backups_button,
                              'achievements': self.app.achievements_button}[key]
                    target.focus_set()
                button.place_forget()
                continue
            nav_width = available * weights[key] / total
            position(button, (nav_x, 0, nav_width, header), ui * .85)
            nav_x += nav_width

        pad = 14 if self.stacked else max(14, round(36 * ui))
        content_x, content_width = px + pad, pw - pad * 2
        play_height = round((52 if self.stacked else 72) * ui)
        row_height = round((46 if self.stacked else 76) * ui)
        action_bottom = py + ph - pad
        row_y = action_bottom - row_height * (1 if self.stacked else 3)
        play_y = row_y - play_height - round(10 * ui)
        title_height = play_y - py - pad - round(14 * ui)
        title_width = min(content_width, title_height * 2.25)
        title_x = px + (pw - title_width) / 2
        title_y = py + pad + (title_height - title_width / 2.25) / 2
        compact_hero = self.stacked and ph < 260
        if compact_hero:
            title_height = row_y - py - pad - 8
            title_width = min(content_width * .48, title_height * 2.25)
            title_x = content_x + (content_width * .48 - title_width) / 2
            title_y = py + pad + (title_height - title_width / 2.25) / 2
        art_scale = title_width / 620
        self.text(title_x, title_y, '4', max(32, round(240 * art_scale)), color=RED)
        self.text(title_x + 168 * art_scale, title_y + 115 * art_scale,
                  'RESIDENT EVIL', max(12, round(32 * art_scale)), color=INK)
        self.text(title_x + 168 * art_scale, title_y + 208 * art_scale, 'M O B I L E',
                  max(10, round(28 * art_scale)), color=INK, weight='bold')
        if title_height >= 110:
            self.text(title_x + 170 * art_scale, title_y + 249 * art_scale,
                      'P C  P O R T', max(10, round(17 * art_scale)), color=INK,
                      family='DejaVu Sans Mono')
        if compact_hero:
            position(self.app.play_button, (content_x + content_width * .53,
                                            py + pad + (title_height - play_height) / 2,
                                            content_width * .47, play_height), ui * .8)
        else:
            position(self.app.play_button, (content_x, play_y, content_width, play_height), ui * .9)
        self.app.utility_images = {
            name: ImageTk.PhotoImage(ui_images.resized(icon, (round(48 * ui), round(48 * ui))))
            for name, icon in self.icon_sources.items()}
        utilities = ((self.app.achievements_button, 'achievements'),
                     (self.settings_button, 'settings'), (self.app.backups_button, 'backups'))
        for index, (button, name) in enumerate(utilities):
            button.kind = 'paper-compact' if self.stacked else 'paper'
            button.icon = self.app.utility_images.get(name)
            if self.stacked:
                cell = content_width / 3
                position(button, (content_x + index * cell, row_y, cell, row_height), ui)
                if index:
                    self.line(content_x + index * cell, row_y + 6,
                              content_x + index * cell, action_bottom - 6, '#8c7855')
            else:
                position(button, (content_x, row_y + index * row_height, content_width, row_height), ui)
                if index:
                    self.line(content_x, row_y + index * row_height,
                              content_x + content_width, row_y + index * row_height, '#8c7855')

        # Languages and installation stay anchored above the footer; the image
        # receives the remaining height and disappears when the form needs it.
        field_height = round(36 * ui) if not self.stacked else 32
        language_gap = max(12, round(20 * ui))
        language_width = (rw - language_gap) // 2
        for index, (key, text) in enumerate((('game_language', 'Game language'),
                                           ('launcher_language', 'Launcher language'))):
            x = rx + index * (language_width + language_gap)
            label(x, form_y, text, 14, color=MUTED, family='DejaVu Sans')
            control = self.language_controls[key][0]
            control.place(x=x, y=form_y + round(22 * ui), width=language_width, height=field_height)
            control.configure(font=('DejaVu Sans', -round(14 * ui)))
        install_y = form_y + round(70 * ui) if not self.stacked else form_y + 62
        label(rx, install_y, 'Installation', 22)
        self.installation_bounds = (rx + round(150 * ui), install_y, rw - round(150 * ui), round(28 * ui))
        folder_y = install_y + round(34 * ui)
        self.app.game_entry.place(x=rx, y=folder_y, width=rw, height=field_height)
        self.app.game_entry.configure(font=('DejaVu Sans Mono', -round(14 * ui)))
        buttons_y = folder_y + field_height + round(10 * ui)
        action_width = (rw - 2 * language_gap) // 3
        position(self.browse_button, (rx, buttons_y, action_width, field_height), ui)
        position(self.app.import_button, (rx + action_width + language_gap, buttons_y,
                                          action_width, field_height), ui)
        self.stop_bounds = (rx + 2 * (action_width + language_gap), buttons_y, action_width, field_height)
        position(self.app.stop_button, self.stop_bounds, ui)
        self.status_bounds = (rx, buttons_y + field_height + round(8 * ui), rw, bottom)
        self.progress_bounds = (rx, bottom - 3, rw, 3)

        self.line(margin, height - footer, width - margin, height - footer, '#8d774a')
        footer_y = height - footer + round(5 * ui)
        self.footer_status = (margin, footer_y + round(16 * ui))
        position(self.app.diagnostics_button, (margin + round(90 * ui), footer_y,
                                              round(118 * ui), max(30, round(32 * ui))), ui)
        position(self.logs_button, (margin + round(218 * ui), footer_y,
                                    round(100 * ui), max(30, round(32 * ui))), ui)
        position(self.icon_button, (margin + round(328 * ui), footer_y,
                                    round(125 * ui), max(30, round(32 * ui))), ui)
        if width >= 1100:
            label(width - margin, footer_y + round(16 * ui), 'Alt+Enter fullscreen  ·  F12 quit',
                  14, color=MUTED, anchor='e')
        self.update_status()

    def text(self, x, y, text, size, *, color=IVORY, family='DejaVu Serif', weight='normal', anchor='nw', **options):
        ox, oy = self.origin
        return self.canvas.create_text(ox + x * self.scale, oy + y * self.scale, text=self.app.tr(text),
                                       font=(family, -max(10, round(size * self.scale)), weight),
                                       fill=color, anchor=anchor, **options)

    def line(self, x1, y1, x2, y2, color):
        ox, oy = self.origin
        s = self.scale
        self.canvas.create_line(ox + x1 * s, oy + y1 * s, ox + x2 * s, oy + y2 * s, fill=color)

    def update_status(self, *args):
        if not hasattr(self, 'status_bounds'):
            return
        app = self.app
        self.canvas.delete('status')
        ready = app.installation.get() == 'Game files found'
        busy = app.child is not None
        error = app.status_label.cget('style') == 'Error.TLabel'
        x, y, width, height = self.installation_bounds
        self.text(x + width, y + height / 2, app.installation.get(), 13,
                  color=MUTED, anchor='e', width=width, tags='status')
        status = app.status.get()
        detail = status if status != 'Ready' else (
            'Game is running.' if app.operation == 'run' and busy else
            'Operation in progress.' if busy else 'Ready to play.' if ready else
            'Choose Import APK to install.')
        x, y, width, bottom = self.status_bounds
        # Full output remains in View logs. Keep the summary inside its reserved
        # area even for child commands that return long multiline errors.
        detail = ' '.join(self.app.tr(detail).split())
        item = self.text(x, y, detail, 12, color='#e1ab91' if error else IVORY,
                         width=width, tags='status')
        if self.canvas.bbox(item)[3] > bottom - 7:
            low, high = 0, len(detail)
            while low < high:
                middle = (low + high + 1) // 2
                self.canvas.itemconfigure(item, text=detail[:middle].rstrip() + '…')
                if self.canvas.bbox(item)[3] <= bottom - 7:
                    low = middle
                else:
                    high = middle - 1
            self.canvas.itemconfigure(item, text=detail[:low].rstrip() + '…')
        short = 'Working' if busy else 'Error' if error else 'Ready' if ready else 'Setup'
        fx, fy = self.footer_status
        self.canvas.create_oval(fx, fy - 5, fx + 10, fy + 5,
                                fill='#6b2c21' if error else '#364d28' if ready else '#806137',
                                outline='#a39369', tags='status')
        self.text(fx + 18, fy, short, 13, anchor='w', tags='status')
        for name in ('overview', 'settings', 'installation'):
            self.nav[name].configure(state='disabled' if busy else 'normal')
        self.nav['backups'].configure(state='normal' if ready and not busy else 'disabled')
        self.nav['achievements'].configure(state='normal' if ready and not busy else 'disabled')
        if busy:
            x, y, width, height = self.stop_bounds
            app.stop_button.place(x=x, y=y, width=width, height=height)
            x, y, width, height = self.progress_bounds
            app.progress.place(x=x, y=y, width=width, height=height)
        else:
            app.stop_button.place_forget()
            app.progress.place_forget()

    def cleanup(self):
        if self.layout_job:
            self.canvas.after_cancel(self.layout_job)
            self.layout_job = None


# Shared dialog surfaces use the same case-file palette as the main window.
PAPER = '#e7d8b9'
PAPER_MUTED = '#65583f'
OLIVE = '#27271b'


def dialog_styles(window):
    from tkinter import ttk
    style = ttk.Style(window)
    style.configure('Paper.TFrame', background=PAPER)
    for name, font, color in (
            ('Paper.TLabel', ('DejaVu Sans', 10), INK),
            ('PaperMuted.TLabel', ('DejaVu Sans', 9), PAPER_MUTED),
            ('PaperHeading.TLabel', ('DejaVu Serif', 18, 'bold'), INK),
            ('PaperTitle.TLabel', ('DejaVu Serif', 11, 'bold'), INK),
            ('PaperError.TLabel', ('DejaVu Sans', 9), RED),
            ('Stamp.TLabel', ('DejaVu Serif', 11, 'bold'), RED)):
        style.configure(name, background=PAPER, foreground=color, font=font)
    for name in ('Paper.TEntry', 'Paper.TCombobox'):
        style.configure(name, foreground=INK, fieldbackground='#f7efdE', padding=7,
                        insertcolor=INK, bordercolor='#887757', focusthickness=2,
                        font=('DejaVu Serif', -16))
        style.map(name, fieldbackground=[('readonly', '#f7efde')],
                  foreground=[('readonly', INK)], bordercolor=[('focus', RED)])
    style.configure('Paper.TCheckbutton', background=PAPER, foreground=INK,
                    padding=6, focuscolor=RED)
    style.map('Paper.TCheckbutton', background=[('active', PAPER)])
    style.configure('Paper.Horizontal.TProgressbar', background=RED, troughcolor='#cabb9c',
                    lightcolor=RED, darkcolor=RED, borderwidth=0, thickness=5)
    style.configure('Section.TButton', anchor='w', padding=(12, 12), background=OLIVE)
    style.map('Section.TButton', background=[('selected', '#4a4230'), ('active', '#383727')],
              foreground=[('selected', IVORY)], bordercolor=[('focus', IVORY)])


class FieldError(ValueError):
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


MOUSE_NAMES = {1: 'Left', 2: 'Middle', 3: 'Right', 4: 'Button4', 5: 'Button5'}
# Display labels for graphics settings; saved values stay machine-readable.
GRAPHICS_CHOICES = {
    'render_scale': {1: '1× (800×480)', 2: '2× (1600×960)', 3: '3× (2400×1440)', 4: '4× (3200×1920)'},
    'msaa': {0: 'Off', 2: '2×', 4: '4×', 8: '8×'},
    'texture_filtering': {'original': 'Original', 'trilinear': 'Trilinear', 'anisotropic': 'Anisotropic 16×'},
    'display_filter': {'bilinear': 'Bilinear', 'sharpen': 'Sharpen', 'fxaa': 'FXAA',
                       'pixel': 'Sharp pixels', 'crt': 'CRT scanlines'},
    'aspect_ratio': {'original': 'Original 5:3', '16:9': 'Widescreen 16:9', '21:9': 'Ultrawide 21:9'},
}


def collect_settings(values, edits, binding_edits, sdl):
    """Parse the existing binding syntax and locate errors without writing data."""
    from .settings import validate
    result = dict(values)
    for key, value in edits.items():
        try:
            original = values[key]
            if key in ('window_mode', 'achievement_capture'):
                value = value.casefold()
            elif key == 'laser_shape':
                value = value.casefold().replace(' ', '_')
            elif key == 'presentation_rate':
                value = '0' if value == 'Uncapped' else value.removesuffix(' FPS').removesuffix(' Hz')
            elif key in GRAPHICS_CHOICES:
                value = {label: choice for choice, label in GRAPHICS_CHOICES[key].items()}.get(value, value)
            if isinstance(original, bool):
                value = bool(value)
            elif key in ('sensitivity', 'controller_sensitivity', 'stick_dead_zone', 'laser_size'):
                value = float(value)
            elif isinstance(original, int):
                value = int(value)
            validate({key: value})
        except (ValueError, TypeError) as error:
            raise FieldError(key, str(error)) from error
        result[key] = value
    bindings = {device: {} for device in ('keyboard', 'mouse', 'controller')}
    for (device, action), raw in binding_edits.items():
        try:
            names = [name.strip() for name in raw.split(',') if name.strip()]
            if device == 'keyboard':
                identifiers = [sdl.SDL_GetKeyFromName((',' if name.lower() == 'comma' else name).encode())
                               for name in names]
                if 0 in identifiers:
                    raise ValueError('Unknown keyboard key for ' + action)
            elif device == 'mouse':
                reverse = {name.lower(): code for code, name in MOUSE_NAMES.items()}
                if any(name.lower() not in reverse for name in names):
                    raise ValueError('Unknown mouse button for ' + action)
                identifiers = [reverse[name.lower()] for name in names]
            else:
                identifiers = [name.lower() for name in names]
            bindings[device][action] = identifiers
            validate({'bindings': bindings})
        except (ValueError, TypeError) as error:
            raise FieldError((device, action), str(error)) from error
    result['bindings'] = bindings
    return validate(result)



def completion_time(timestamp_ns, *, short=False, zone=None):
    """Existing nanosecond timestamps, rendered in the host's local zone."""
    import datetime
    instant = datetime.datetime.fromtimestamp(timestamp_ns / 1e9, datetime.timezone.utc)
    local = instant.astimezone(zone)
    months = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
    date = f'{local.day:02d} {months[local.month - 1]} {local.year}'
    if short:
        return date + local.strftime(' · %H:%M')
    offset = int(local.utcoffset().total_seconds())
    sign = '+' if offset >= 0 else '−'
    hours, minutes = divmod(abs(offset) // 60, 60)
    return f'Completion recorded: {date} · {local:%H:%M:%S} UTC{sign}{hours:02d}:{minutes:02d}'


# Catalog rows show every achievement at this size.
CATALOG_ART_SIZE = 72


class AchievementArtwork:
    """Only crop/resize original alpha; cache each display size per window."""
    def __init__(self, assets):
        self.assets = assets
        self.images = {}

    def steps(self, item, size):
        return (self.assets / ('achievement-' + item.id + '.png'), 'RGBA',
                ('trim', 0), ('contain', (size - 8, size - 8)))

    def warm(self, items, size=CATALOG_ART_SIZE):
        return ui_images.warm(prepared_items=[self.steps(item, size) for item in items])

    def draw(self, canvas, item, size, *, clear=True, x=None, y=None):
        if clear:
            canvas.delete('all')
        key = (item.id, size)
        if key not in self.images:
            try:
                icon = ui_images.prepared(*self.steps(item, size))
                if icon is None:
                    raise ValueError('Empty achievement artwork')
                self.images[key] = ImageTk.PhotoImage(icon)
            except (OSError, ValueError):
                self.images[key] = None
        photo = self.images[key]
        if photo:
            canvas.create_image(x if x is not None else size / 2, y if y is not None else size / 2, image=photo)
        else:
            from .achievement_media import draw_icon
            old = set(canvas.find_all())
            draw_icon(canvas, item, True)
            # Isolate fallback geometry so the paper and text are never scaled.
            new = set(canvas.find_all()) - old if not clear else set(canvas.find_all())
            for identity in new:
                canvas.scale(identity, 0, 0, size / 64, size / 64)
                canvas.move(identity, (x or size/2)-size/2, (y or size/2)-size/2)




from .case_dialog import CaseDialog, PaperCanvas, PaperPane as CasePaperPane


class SettingsView:
    SECTIONS = ('Display & sensitivity', 'Graphics', 'Laser sight', 'Achievements', 'Keyboard', 'Mouse', 'Controller')

    def __init__(self, app, values, sdl):
        from tkinter import ttk
        from .actions import NATIVE_CODES
        self.app, self.values, self.sdl = app, values, sdl
        self.chrome = CaseDialog(app, 'Settings & controls', self.close,
                                 footer='ⓘ  Changes apply on next launch')
        self.window = self.chrome.window
        self.window.view = self
        self.frame = self.chrome.frame
        self.editors, self.binding_editors, self.fields, self.panes, self.nav = {}, {}, {}, {}, {}
        self.sliders, self.field_info = {}, {}
        self.choice_fields = []
        self.section = self.SECTIONS[0]
        self.notice = tk.StringVar()
        self.cancel_button = self.chrome.action('Cancel', self.close)
        self.save_button = self.chrome.action('Save settings', self.save, primary=True, width=182)
        # Reference order: save first, then cancel.
        self.chrome.footer_buttons.reverse()
        self.notice.trace_add('write', lambda *args: self.update_notice())
        self.navigation = CasePaperPane(self.chrome.body, app.assets, render=self.draw_navigation)
        self.navigation.frame.pack(side='left', fill='both', padx=(0, 12))
        self.navigation.frame.configure(width=370)
        self.navigation.frame.pack_propagate(False)
        self.host = ttk.Frame(self.chrome.body, style='Paper.TFrame')
        self.host.pack(side='left', fill='both', expand=True)
        for index, name in enumerate(self.SECTIONS):
            button = ArtworkButton(self.navigation.content, name, lambda name=name: self.select(name), kind='section')
            button.bind('<Down>', lambda event, i=index: self.navigate((i + 1) % len(self.SECTIONS)))
            button.bind('<Up>', lambda event, i=index: self.navigate((i - 1) % len(self.SECTIONS)))
            button.bind('<FocusIn>', lambda event, button=button: self.navigation.reveal(button))
            self.nav[name] = button
            self.panes[name] = CasePaperPane(self.host, app.assets, render=lambda name=name: self.draw_section(name))
        for key, label, choices in (
                ('window_mode', 'Window mode', ('Windowed', 'Fullscreen')),
                ('window_width', 'Window width', None), ('window_height', 'Window height', None),
                ('presentation_rate', 'Presentation rate', ('20 FPS', '30 FPS', '60 FPS', '90 FPS', '120 FPS', '144 FPS', '165 FPS', '240 FPS', 'Uncapped')),
                ('sensitivity', 'Mouse sensitivity', None),
                ('controller_sensitivity', 'Look stick sensitivity', None),
                ('stick_dead_zone', 'Stick dead zone', None), ('invert_y', 'Invert look Y', None)):
            self.add_field(self.SECTIONS[0], key, label, values[key], choices)
        for key, label in (('render_scale', 'Render scale'), ('msaa', 'Anti-aliasing (MSAA)'),
                           ('texture_filtering', 'Texture filtering'), ('display_filter', 'Display filter'),
                           ('aspect_ratio', 'Aspect ratio')):
            self.add_field('Graphics', key, label, values[key], tuple(GRAPHICS_CHOICES[key].values()))
        for key, label, choices in (
                ('laser_shape', 'Sight shape', ('Original', 'Circle', 'Predator', 'Black Matter')),
                ('laser_color', 'Laser color', None), ('laser_size', 'Sight size', None)):
            self.add_field('Laser sight', key, label, values[key], choices)
        self.laser_picker = ArtworkButton(self.panes['Laser sight'].content, 'Choose color', self.choose_laser_color,
                                         kind='paper-outline')
        self.laser_reset = ArtworkButton(self.panes['Laser sight'].content, 'Reset sight', self.reset_laser,
                                        kind='paper-outline')
        for control in (self.laser_picker, self.laser_reset):
            control.bind('<FocusIn>', lambda event: self.panes['Laser sight'].reveal(event.widget), add='+')
        self.laser_preview = tk.Canvas(self.panes['Laser sight'].content, background='#17131e',
                                       highlightthickness=0, width=280, height=170)
        self.laser_phase = 0
        self.laser_job = None
        for key in ('laser_shape', 'laser_color', 'laser_size'):
            self.editors[key].trace_add('write', lambda *args: self.update_laser_preview())
        self.laser_preview.bind('<Destroy>', self.stop_laser_preview)
        self.animate_laser_preview()
        for key, label, choices in (
                ('achievement_capture', 'Unlock capture', ('off', 'screenshot', 'clip', 'both')),
                ('achievement_clip_seconds', 'Replay length (seconds)', tuple(str(n) for n in range(5, 16)))):
            self.add_field('Achievements', key, label, values[key], choices)
        for device in ('keyboard', 'mouse', 'controller'):
            for action in NATIVE_CODES:
                identifiers = values['bindings'][device].get(action, [])
                if device == 'keyboard':
                    names = [sdl.SDL_GetKeyName(code).decode() for code in identifiers]
                    names = ['Comma' if name == ',' else name for name in names]
                elif device == 'mouse':
                    names = [MOUSE_NAMES[code] for code in identifiers]
                else:
                    names = identifiers
                self.add_field(device.capitalize(), (device, action), action.capitalize(), ', '.join(names))
        self.initial = self.snapshot()
        self.select(self.section)
        self.chrome.body.bind('<Configure>', self.layout)
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.window.bind(sequence, self.scroll)
        self.window.bind('<Control-s>', lambda event: self.save())

    def update_notice(self):
        self.chrome.footer = self.notice.get() or 'ⓘ  Changes apply on next launch'
        self.chrome.schedule()

    def layout(self, event):
        self.navigation.frame.configure(width=max(190, round(event.width * .30)))
        self.navigation.content.schedule()

    def scroll(self, event):
        widget = event.widget
        while widget is not None:
            if widget is self.navigation.frame:
                return self.navigation.scroll(event)
            widget = getattr(widget, 'master', None)
        return self.panes[self.section].scroll(event)

    def draw_navigation(self):
        canvas = self.navigation.content
        w = canvas.winfo_width()
        narrow = w < 270
        h = max(548 if narrow else 570, 300+len(self.SECTIONS)*48)
        canvas.surface(h)
        canvas.art('settings', w/2 if narrow else 100, 83, 108 if narrow else 134)
        canvas.text(28, 156, 'SETTINGS\n& CONTROLS' if narrow else 'SETTINGS &\nCONTROLS',
                    20 if narrow else 31, weight='bold', width=w-52)
        canvas.text(28, 240, 'Settings apply to the\nnext game launch.' if narrow else
                    'Settings apply to the next game launch.', 12, family='DejaVu Sans Mono', width=w-52)
        for index, (name, button) in enumerate(self.nav.items()):
            y = 300+index*48
            button.selected = name == self.section
            canvas.window(button, 18, y, w-36, 46)
            # Continue the parchment behind the focusable native action.
            button.scale = .75 if narrow else 1
            button.draw()
            canvas.rule(y+47, 18, w-18)
        self.navigation.extent(h)

    def add_field(self, section, key, label, value, choices=None):
        from tkinter import ttk
        pane = self.panes[section]
        if key == 'window_mode':
            value = value.capitalize()
        elif key == 'laser_shape':
            from .laser import SHAPE_LABELS
            value = SHAPE_LABELS[value]
        elif key == 'presentation_rate':
            value = str(value)+' FPS' if value else 'Uncapped'
        elif key in GRAPHICS_CHOICES:
            value = GRAPHICS_CHOICES[key][value]
        variable = tk.BooleanVar(value=value) if isinstance(value, bool) else tk.StringVar(value=str(value))
        if isinstance(value, bool):
            control = ttk.Checkbutton(pane.content, variable=variable, style='Paper.TCheckbutton')
        elif choices:
            display = tk.StringVar(value=self.app.tr(variable.get()))
            control = ttk.Combobox(pane.content, textvariable=display,
                                   values=tuple(self.app.tr(choice) for choice in choices), state='readonly',
                                   style='Paper.TCombobox', width=12)
            control.bind('<<ComboboxSelected>>', lambda event, variable=variable, choices=choices:
                         variable.set(choices[event.widget.current()]))
            def changed(*args, variable=variable, display=display, choices=choices):
                reverse = {self.app.tr(choice): choice for choice in choices}
                value = reverse.get(display.get(), display.get())
                if value in choices and value != variable.get():
                    variable.set(value)
            display.trace_add('write', changed)
            variable.trace_add('write', lambda *args, variable=variable, display=display:
                               display.set(self.app.tr(variable.get())))
            self.choice_fields.append((control, display, variable, choices))
        else:
            control = ttk.Entry(pane.content, textvariable=variable, style='Paper.TEntry', width=12)
        error = ttk.Label(pane.content, style='PaperError.TLabel', wraplength=360)
        error.bind('<Configure>', lambda event, error=error: error.configure(wraplength=max(80, event.width)))
        table = self.binding_editors if isinstance(key, tuple) else self.editors
        table[key] = variable
        self.field_info[key] = label
        self.fields[key] = (section, control, error, control)
        control.bind('<FocusIn>', lambda event, control=control: pane.reveal(control))
        if key in ('sensitivity', 'controller_sensitivity', 'stick_dead_zone'):
            self.sliders[key] = SensitivitySlider(pane.content, variable,
                                                 maximum=.9 if key == 'stick_dead_zone' else 10,
                                                 minimum=0 if key == 'stick_dead_zone' else .05)
            self.sliders[key].bind('<FocusIn>', lambda event, key=key: pane.reveal(self.sliders[key]))

    def translate_choices(self):
        for control, display, variable, choices in self.choice_fields:
            control.configure(values=tuple(self.app.tr(choice) for choice in choices))
            display.set(self.app.tr(variable.get()))

    def choose_laser_color(self):
        from tkinter import colorchooser
        from .settings import validate
        color = self.editors['laser_color'].get()
        try:
            validate({'laser_color': color})
        except ValueError:
            color = '#ff0000'
        _, selected = colorchooser.askcolor(color=color, parent=self.window, title=self.app.tr('Laser color'))
        if selected:
            self.editors['laser_color'].set(selected)

    def reset_laser(self):
        self.editors['laser_shape'].set('Original')
        self.editors['laser_color'].set('#ff0000')
        self.editors['laser_size'].set('1.0')

    def update_laser_preview(self):
        from PIL import ImageTk
        from .laser import sight_image
        from .settings import validate
        canvas = self.laser_preview
        canvas.delete('all')
        try:
            shape = self.editors['laser_shape'].get().casefold().replace(' ', '_')
            color = self.editors['laser_color'].get()
            scale = float(self.editors['laser_size'].get())
            validate({'laser_shape': shape, 'laser_color': color, 'laser_size': scale})
        except (ValueError, TypeError):
            canvas.create_text(140, 85, text=self.app.tr('Review the highlighted field.'), fill='#f5dfbe', width=260)
            return
        self.laser_photo = ImageTk.PhotoImage(sight_image(shape, color, round(48*scale), self.laser_phase/20))
        canvas.create_line(16, 85, 160, 85, fill=color, width=2)
        canvas.create_image(170, 85, image=self.laser_photo)

    def animate_laser_preview(self):
        if self.section == 'Laser sight':
            self.update_laser_preview()
        self.laser_phase = (self.laser_phase+1) % 20
        self.laser_job = self.laser_preview.after(100, self.animate_laser_preview)

    def stop_laser_preview(self, event):
        if self.laser_job:
            self.laser_preview.after_cancel(self.laser_job)
            self.laser_job = None

    def draw_section(self, name):
        pane = self.panes[name]
        canvas = pane.content
        w = canvas.winfo_width()
        narrow = w < 580
        left, right = 32, w-32
        header_size = 25 if narrow else 36
        keys = [key for key, (section, *rest) in self.fields.items() if section == name]
        rows = []
        y = 142 if name == self.SECTIONS[0] else 148
        for index, key in enumerate(keys):
            if key == 'sensitivity':
                y += 82
            section, control, error, _ = self.fields[key]
            error_height = 42 if error.cget('text') else 0
            rows.append((key, y, error_height))
            y += (78 if narrow else 43) + error_height
        fields_end = y
        help_text = {
            'Graphics': 'Render scale multiplies the internal resolution; MSAA smooths geometry edges. Texture filtering adds mipmaps to reduce shimmer. Widescreen widens 3D views while the HUD and menus keep their original 5:3 layout; the screen edges may show objects appearing late. Changes apply on next launch.',
            'Laser sight': 'Choose a color or enter #RRGGBB. Predator uses three dots. Black Matter animates a cosmic pattern with your color as its accent. Size: 0.5 to 3.0. Changes apply on next launch.',
            'Achievements': 'Save the moment you unlock an achievement. Screenshots are saved by default. Clips are silent, at 5 frames per second, and include up to the selected replay length before the unlock. Clip capture uses extra memory. Recovered achievements do not create captures.',
            'Keyboard': 'Examples: W, Up, Return, Escape, Space, F1, Comma. Tab, F3 and F12 are reserved desktop controls.',
            'Mouse': 'Buttons: Left, Middle, Right, Button4, Button5.',
            'Controller': 'Buttons: a, b, x, y, start, back, guide, leftshoulder, rightshoulder, leftstick, rightstick, dpup, dpdown, dpleft, dpright, lefttrigger, righttrigger. Left stick moves; right stick looks.'}.get(name, '')
        height = max(570, y+410 if name == 'Laser sight' else y+160 if help_text else y+34)
        canvas.surface(height)
        canvas.text(left, 40, name, header_size, weight='bold', width=w-64)
        canvas.art('paperclip', 76, 14, 26, 48)
        if w > 740:
            canvas.stamp(w-68, 64, 70)
        if name == self.SECTIONS[0]:
            canvas.text(left, 105, 'Display', 23, color=RED, weight='bold')
            canvas.rule(120, left+85, right)
        else:
            canvas.text(left, 106, 'Customize your aim' if name == 'Laser sight' else 'Capture preferences' if name == 'Achievements' else
                        'Sharper, smoother rendering' if name == 'Graphics' else
                        'Comma-separated names; leave blank to unbind.', 13, family='DejaVu Sans Mono', width=w-64)
        field_x = left if narrow else left+round((w-64)*.37)
        field_w = right-field_x
        for key, y, error_height in rows:
            _, control, error, _ = self.fields[key]
            if key == 'sensitivity':
                canvas.text(left, y-48, 'Sensitivity', 23, color=RED, weight='bold')
                canvas.rule(y-32, left+130, right)
                canvas.text(field_x if not narrow else left, y-81,
                            'Higher FPS interpolates motion; gameplay stays 20 Hz.', 12, family='DejaVu Sans Mono', width=field_w)
            canvas.text(left, y+7, self.field_info[key], 14, family='DejaVu Sans Mono', width=field_x-left-10 if not narrow else w-64)
            cy = y+30 if narrow else y
            width = 32 if key == 'invert_y' else field_w
            if key in self.sliders:
                slider_w = max(30, field_w-83)
                canvas.window(self.sliders[key], field_x, cy, slider_w, 30)
                canvas.window(control, right-68, cy, 68, 30)
            else:
                canvas.window(control, field_x, cy, width, 30)
            if error_height:
                canvas.window(error, field_x, cy+32, field_w, error_height)
        y = fields_end  # the row loop above reuses `y` for each field
        if name == 'Laser sight':
            canvas.window(self.laser_picker, left, y+10, min(180, (w-74)/2), 38)
            canvas.window(self.laser_reset, left+min(190, (w-64)/2), y+10, min(180, (w-74)/2), 38)
            canvas.window(self.laser_preview, left, y+65, min(280, w-64), 170)
            y += 245
        if help_text:
            canvas.rule(y+12, left, right)
            canvas.text(left, y+28, help_text, 14, color=PAPER_MUTED, width=w-64)
        pane.extent(height)

    def navigate(self, index):
        self.select(self.SECTIONS[index])
        self.nav[self.section].focus_set()
        return 'break'

    def select(self, name):
        for section, pane in self.panes.items():
            pane.frame.pack_forget()
        self.section = name
        self.panes[name].frame.pack(fill='both', expand=True)
        self.navigation.content.schedule()
        self.panes[name].content.schedule()
    def snapshot(self):
        return {key: variable.get() for key, variable in {**self.editors, **self.binding_editors}.items()}

    def save(self):
        from .settings import Settings
        for section, control, error, row in self.fields.values():
            error.configure(text='')
        self.notice.set('')
        try:
            result = collect_settings(self.values, {key: var.get() for key, var in self.editors.items()},
                                      {key: var.get() for key, var in self.binding_editors.items()}, self.sdl)
            latest = Settings.load()
            for key in ('game_language', 'launcher_language'):
                result[key] = latest[key]
            Settings.save(result)
        except FieldError as error:
            section, control, label, row = self.fields[error.field]
            label.configure(text=str(error))
            self.select(section)
            self.panes[section].content.redraw()
            control.focus_set()
            self.panes[section].reveal(row)
            self.notice.set('Review the highlighted field.')
            return
        except (ValueError, OSError, TypeError) as error:
            self.notice.set('Could not save settings: ' + str(error))
            return
        self.app.status.set('Settings saved')
        self.window.destroy()

    def can_close(self):
        from tkinter import messagebox
        return self.snapshot() == self.initial or messagebox.askyesno(
            self.app.tr('Discard settings changes?'), self.app.tr('Discard your unsaved changes?'), parent=self.window)

    def close(self):
        if self.can_close():
            self.window.destroy()



class SensitivitySlider(tk.Canvas):
    """Focusable continuous control sharing the entry's validated string value."""
    def __init__(self, parent, variable, *, minimum, maximum):
        super().__init__(parent, background=PAPER, highlightthickness=0, takefocus=True, cursor='hand2')
        self.surface = None
        self.variable, self.minimum, self.maximum = variable, minimum, maximum
        self.trace = variable.trace_add('write', lambda *args: self.draw())
        self.bind('<Configure>', lambda event: self.draw())
        self.bind('<FocusIn>', lambda event: self.draw(), add='+')
        self.bind('<FocusOut>', lambda event: self.draw())
        self.bind('<Button-1>', self.pointer)
        self.bind('<B1-Motion>', self.pointer)
        for key, direction in (('Left', -1), ('Down', -1), ('Right', 1), ('Up', 1)):
            self.bind('<'+key+'>', lambda event, direction=direction: self.step(direction))
        self.bind('<Home>', lambda event: self.set(self.minimum))
        self.bind('<End>', lambda event: self.set(self.maximum))
        self.bind('<Destroy>', self.cleanup, add='+')

    def value(self):
        import math
        try:
            value = float(self.variable.get())
            return min(self.maximum, max(self.minimum, value)) if math.isfinite(value) else self.minimum
        except ValueError:
            return self.minimum

    def draw(self):
        self.delete('all')
        if self.surface:
            self.create_image(0, 0, image=self.surface, anchor='nw')
        w, h = self.winfo_width(), self.winfo_height()
        x = 8+(w-16)*(self.value()-self.minimum)/(self.maximum-self.minimum)
        self.create_rectangle(8, h/2-3, max(8, w-8), h/2+3, fill='#cabb9c', outline='#887757')
        self.create_rectangle(8, h/2-3, x, h/2+3, fill=RED, outline='')
        self.create_rectangle(x-6, h/2-9, x+6, h/2+9, fill=RED, outline='#887757')
        if self.focus_get() is self:
            self.create_rectangle(1, 1, w-2, h-2, outline=RED, dash=(3, 3))

    def set(self, value):
        self.variable.set(str(round(min(self.maximum, max(self.minimum, value)), 2)))
        return 'break'

    def pointer(self, event):
        self.focus_set()
        return self.set(self.minimum+(self.maximum-self.minimum)*(event.x-8)/max(1, self.winfo_width()-16))

    def step(self, direction):
        return self.set(self.value()+direction*(.01 if self.maximum < 1 else .05))

    def cleanup(self, event):
        if event.widget is self:
            self.variable.trace_remove('write', self.trace)


class AchievementRow(PaperCanvas):
    def __init__(self, parent, view, item, index):
        super().__init__(parent, view.app.assets, takefocus=True, cursor='hand2', height=94, load_paper=False)
        self.view, self.item = view, item
        self.selected = False
        self.render = self.draw
        self.bind('<Button-1>', lambda event: self.focus_set())
        self.bind('<FocusIn>', self.focused)
        self.bind('<FocusOut>', lambda event: self.schedule())
        for key, target in (('Down', index+1), ('Up', index-1), ('Home', 0), ('End', len(view.visible)-1)):
            self.bind('<'+key+'>', lambda event, target=target: view.move(target))
        self.bind('<Return>', lambda event: view.select(item.id))
        self.bind('<space>', lambda event: view.select(item.id))

    def focused(self, event):
        if self.view.restoring_focus == self.item.id:
            self.view.restoring_focus = None
        else:
            self.view.select(self.item.id, reveal=True)
        self.schedule()

    def draw(self):
        w, h = self.surface(94)
        selected = self.item.id == self.view.selected
        self.selected = selected
        if selected:
            self.highlight(h)
            self.text(w-14, h/2, '›', 30, color=RED, anchor='center')
        else:
            self.rule(h-1, 0, w)
        self.view.art.draw(self, self.item, CATALOG_ART_SIZE, clear=False, x=52, y=47)
        earned = self.item.id in self.view.unlocked
        current, target = self.item.progress(self.view.records, self.view.unlocked)
        wide = w > 650
        title_w = w-150 if not wide else w*.52-110
        self.text(112, 15, self.item.title, 17, weight='bold', width=title_w)
        self.text(112, 40, 'Unlocked' if earned else 'Locked', 13, color=RED if earned else INK, family='DejaVu Sans Mono')
        description = completion_time(self.view.unlocked[self.item.id], short=True) if earned else self.item.description
        self.text(112, 62, description, 12, width=w-150)
        if wide:
            px = w*.66
            self.progress(px, 33, w*.28, target if earned else current, target)
            self.text(px+w*.28, 52, f'{target if earned else current} / {target}', 12, anchor='ne')
        if self.focus_get() is self:
            self.create_rectangle(7, 4, w-7, h-5, outline=RED, dash=(3, 3))


class AchievementsView:
    def __init__(self, app, root):
        from tkinter import ttk
        from .achievements import AchievementStore
        self.app, self.root = app, root
        self.store = AchievementStore(root)
        self.chrome = CaseDialog(app, 'Achievements', self.close, minimum=(600, 420),
                                 footer='● Local')
        self.window, self.frame, self.body = self.chrome.window, self.chrome.frame, self.chrome.body
        self.window.view = self
        self.art = AchievementArtwork(app.assets)
        from .achievements import ACHIEVEMENTS
        # Decode the catalog artwork in parallel before the rows draw it.
        for future in self.art.warm(ACHIEVEMENTS):
            future.result()
        self.selected = None
        self.restoring_focus = None
        self.records, self.unlocked = None, {}
        self.rows, self.visible = {}, []
        self.job, self.mode = None, None
        self.wheel_job = None
        self.summary = tk.StringVar()
        self.search = tk.StringVar()
        self.filter = tk.StringVar(value='All')
        self.close_button = self.chrome.action('Close', self.close, width=70)
        self.refresh_button = self.chrome.action('Refresh', self.refresh, width=80)
        self.export_selected_button = self.chrome.action('Export selected', lambda: self.export(True), width=135)
        self.export_all_button = self.chrome.action('Export all', lambda: self.export(False), width=105)
        self.chrome.footer_buttons.reverse()
        self.catalog = CasePaperPane(self.body, app.assets, render=self.draw_catalog)
        self.detail = CasePaperPane(self.body, app.assets, render=self.draw_detail)
        self.search_entry = ttk.Entry(self.catalog.content, textvariable=self.search, style='Paper.TEntry')
        self.search_hint = self.app.translated_widget(tk.Label(self.search_entry, text='Search achievements…', background='#f7efde',
                                    foreground=PAPER_MUTED, font=('DejaVu Serif', -14), cursor='xterm'))
        self.search_hint.bind('<Button-1>', lambda event: self.search_entry.focus_set())
        self.search_entry.bind('<FocusIn>', lambda event: (self.catalog.canvas.yview_moveto(0), self.update_search_hint()))
        self.search_entry.bind('<FocusOut>', lambda event: self.update_search_hint())
        self.search_entry.bind('<Down>', lambda event: self.move(0))
        self.filters = {}
        for label in ('All', 'Unlocked', 'Locked'):
            self.filters[label] = ArtworkButton(self.catalog.content, label,
                                                lambda label=label: self.filter.set(label), kind='segment')
        self.detail_buttons = []
        self.body.bind('<Configure>', self.layout)
        self.search.trace_add('write', self.filter_changed)
        self.filter.trace_add('write', self.filter_changed)
        self.window.bind('<Control-f>', lambda event: self.search_entry.focus_set())
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.window.bind(sequence, self.scroll)
        self.window.bind('<Destroy>', self.cleanup, add='+')
        self.refresh()

    def close(self):
        self.window.destroy()
        self.app.window.lift()

    def busy_changed(self):
        busy = self.app.child is not None
        self.export_selected_button.configure(state='normal' if not busy and self.records is not None and self.selected else 'disabled')
        self.export_all_button.configure(state='normal' if not busy and self.records is not None else 'disabled')
        self.refresh_button.configure(state='disabled' if busy else 'normal')

    def export(self, selected):
        from tkinter import filedialog, messagebox
        import json
        if self.app.child or self.records is None or (selected and not self.selected):
            return
        destination = filedialog.asksaveasfilename(parent=self.window, title=self.app.tr('Export achievement captures'),
            defaultextension='.zip', initialfile='re4-achievements.zip', filetypes=[(self.app.tr('Capture archive'), '*.zip')])
        if not destination:
            return
        arguments = ['--achievement', self.selected] if selected else []
        def complete(code):
            if not self.window.winfo_exists():
                return
            if code:
                messagebox.showerror(self.app.tr('Export failed'), self.app.tr(self.app.last_output or 'View launcher logs for details.'), parent=self.window)
            else:
                try:
                    result = json.loads(self.app.last_output)
                    count = len(result['missing_captures'])
                except (ValueError, KeyError, TypeError):
                    messagebox.showerror(self.app.tr('Export result unavailable'), self.app.tr('View launcher logs for details.'), parent=self.window)
                    return
                messagebox.showinfo(self.app.tr('Captures exported'), self.app.tr(f"Exported {result['files']} media files." +
                    (f' {count} missing references are listed in achievements.json.' if count else '')), parent=self.window)
            self.busy_changed()
        self.app.start('export-achievements', destination, *arguments, '--game', self.root, on_complete=complete)
        self.busy_changed()

    def layout(self, event):
        stacked = self.window.winfo_width() < 880
        if stacked:
            self.catalog.frame.configure(height=max(96, min(230, event.height//2)))
        if self.mode == stacked:
            return
        self.mode = stacked
        self.catalog.frame.grid_forget()
        self.detail.frame.grid_forget()
        self.body.columnconfigure(0, weight=3 if stacked else 6, uniform='' if stacked else 'papers')
        self.body.columnconfigure(1, weight=0 if stacked else 4, uniform='' if stacked else 'papers')
        self.body.rowconfigure(0, weight=0 if stacked else 1, minsize=96 if stacked else 0)
        self.body.rowconfigure(1, weight=1 if stacked else 0)
        self.catalog.frame.grid(row=0, column=0, sticky='nsew', padx=(0, 0 if stacked else 12))
        self.detail.frame.grid(row=1 if stacked else 0, column=0 if stacked else 1, sticky='nsew', pady=(10 if stacked else 0, 0))
        self.catalog.frame.pack_propagate(not stacked)

    def scroll(self, event):
        if event.widget.winfo_toplevel() is not self.window:
            return
        for pane in (self.catalog, self.detail):
            canvas = pane.canvas
            x, y = event.x_root - canvas.winfo_rootx(), event.y_root - canvas.winfo_rooty()
            if not (0 <= x < canvas.winfo_width() and 0 <= y < canvas.winfo_height()):
                continue
            if pane is self.detail:
                return pane.scroll(event)
            if not self.visible:
                return
            first = self.rows[self.visible[0].id]
            last = self.rows[self.visible[-1].id]
            if not (first.winfo_y() <= canvas.canvasy(y) < last.winfo_y() + last.winfo_height()):
                return
            steps = pane.wheel_steps(event)
            if steps:
                index = next((i for i, item in enumerate(self.visible) if item.id == self.selected), 0)
                limit = (len(self.visible) - 1) // 4 * 4
                index = max(0, min(limit, index // 4 * 4 + steps * 4))
                if self.selected != self.visible[index].id:
                    self.selected = self.visible[index].id
                    # Keep row widgets alive while queued input still targets them.
                    if self.wheel_job is None:
                        self.wheel_job = self.window.after(30, self.apply_wheel_selection)
            return 'break'

    def apply_wheel_selection(self):
        self.wheel_job = None
        self.select(self.selected)
        row = self.rows[self.selected]
        index = next(i for i, item in enumerate(self.visible) if item.id == self.selected)
        self.catalog.canvas.yview_moveto(0 if index == 0 else
            max(0, row.winfo_y() - 24) / self.catalog.content.winfo_height())
        if self.window.focus_get() in self.rows.values():
            self.restoring_focus = self.selected
            row.focus_set()

    def reset_wheel(self):
        if self.wheel_job is not None:
            self.window.after_cancel(self.wheel_job)
            self.wheel_job = None
        self.catalog.wheel_remainder = 0

    def scroll_panes(self, event):
        widget = event.widget
        while widget is not None:
            if widget is self.detail.frame:
                return self.detail.scroll(event)
            widget = getattr(widget, 'master', None)
        return self.catalog.scroll(event)

    def filter_changed(self, *args):
        self.update_search_hint()
        if self.records is not None:
            self.populate()

    def update_search_hint(self):
        if self.search.get() or self.window.focus_get() is self.search_entry:
            self.search_hint.place_forget()
        else:
            self.search_hint.place(x=8, rely=.5, anchor='w')

    def refresh(self):
        from .achievements import ACHIEVEMENTS
        self.reset_wheel()
        try:
            self.records, self.unlocked = self.store.load()
        except (OSError, ValueError) as error:
            self.records, self.unlocked, self.store.media = None, {}, {}
            self.summary.set('Could not read achievements: '+str(error))
            self.visible, self.selected = [], None
            self.clear_rows()
            self.catalog.content.schedule()
            self.select(None)
            return
        text = f'{len(self.unlocked)} / {len(ACHIEVEMENTS)} unlocked'
        if not self.store.path.exists():
            text += '\nPlay once to recover existing progress. New achievements unlock when the game saves.'
        elif not self.unlocked:
            text += '\nNo completions recorded yet.'
        self.summary.set(text)
        self.populate(retain_scroll=True)

    def clear_rows(self):
        for row in self.rows.values():
            row.destroy()
        self.rows = {}

    def populate(self, retain_scroll=False):
        from .achievements import ACHIEVEMENTS
        self.reset_wheel()
        scroll = self.catalog.canvas.yview()[0] if retain_scroll else 0
        focused = next((key for key, row in self.rows.items() if self.window.focus_get() is row), None)
        self.clear_rows()
        query, mode = self.search.get().strip().casefold(), self.filter.get()
        self.visible = [item for item in ACHIEVEMENTS
                        if (not query or query in (item.title+' '+item.description+' '+
                                                  self.app.tr(item.title)+' '+self.app.tr(item.description)).casefold())
                        and (mode == 'All' or (item.id in self.unlocked) == (mode == 'Unlocked'))]
        if self.selected not in {item.id for item in self.visible}:
            self.selected = self.visible[0].id if self.visible else None
        for index, item in enumerate(self.visible):
            self.rows[item.id] = AchievementRow(self.catalog.content, self, item, index)
        self.select(self.selected)
        self.catalog.content.redraw()
        if focused in self.rows and self.selected in self.rows:
            self.restoring_focus = self.selected
            self.rows[self.selected].focus_set()
        if self.job:
            self.window.after_cancel(self.job)
        self.job = self.window.after_idle(lambda: self.restore_scroll(scroll))

    def draw_catalog(self):
        c = self.catalog.content
        w = c.winfo_width()
        narrow = w < 610
        compact = bool(self.mode)
        start = 90 if compact else 240 if narrow else 208
        height = max(570, start+len(self.visible)*94+24)
        c.surface(height)
        if not compact:
            c.text(40, 30, 'ACHIEVEMENT CASE FILE', 25 if narrow else 31, weight='bold', width=w-80)
        if w > 660 and not compact:
            c.stamp(w-70, 78, 76)
        c.text(24 if compact else 40, 12 if compact else 92,
               self.summary.get().split('\n')[0] if compact else self.summary.get(), 13,
               family='DejaVu Sans Mono', width=w-48 if compact else w-80)
        self.catalog.extent(height)
        search_w = round((w-70)*.5) if compact else w-64 if narrow else round((w-70)*.55)
        c.window(self.search_entry, 24 if compact else 32, 40 if compact else 154, search_w, 34)
        self.update_search_hint()
        if not self.search.get() and self.window.focus_get() is not self.search_entry:
            # A real label next to the entry makes the search purpose persistent.
            if not compact:
                c.text(32, 133, 'Search achievements', 12, color=PAPER_MUTED)
        fx, fy = (36+search_w, 40) if compact else (32, 196) if narrow else (48+search_w, 154)
        fw = (w-fx-24)/3 if compact else (w-64)/3 if narrow else (w-fx-32)/3
        for index, (name, button) in enumerate(self.filters.items()):
            button.selected = self.filter.get() == name
            button.scale = .85
            c.window(button, fx+index*fw, fy, fw, 34)
        c.rule(start-8, 22, w-22)
        for index, item in enumerate(self.visible):
            c.window(self.rows[item.id], 22, start+index*94, w-44, 94)
        if not self.visible:
            c.text(36, start+26, 'Records unavailable. Repair the record and refresh.' if self.records is None else
                   'No achievements match this search and filter.', 18, color=RED if self.records is None else INK, width=w-72)
        self.catalog.update_region()

    def restore_scroll(self, fraction):
        self.job = None
        self.catalog.canvas.update_idletasks()
        self.catalog.update_region()
        self.catalog.canvas.yview_moveto(fraction)

    def move(self, index):
        self.reset_wheel()
        self.restoring_focus = None
        if self.visible:
            self.rows[self.visible[max(0, min(index, len(self.visible)-1))].id].focus_set()
        return 'break'

    def select(self, identity, reveal=False):
        if self.wheel_job is not None:
            self.reset_wheel()
        self.selected = identity
        self.busy_changed()
        for row in self.rows.values():
            if row.selected != (row.item.id == identity):
                row.schedule()
        if reveal and identity in self.rows:
            self.catalog.reveal(self.rows[identity])
        for button in self.detail_buttons:
            button.destroy()
        self.detail_buttons = []
        self.detail.content.redraw()
        self.detail.canvas.yview_moveto(0)

    def draw_detail(self):
        from tkinter import ttk
        from .achievements import ACHIEVEMENTS
        from .achievement_media import media_path
        c = self.detail.content
        w = c.winfo_width()
        item = next((item for item in ACHIEVEMENTS if item.id == self.selected), None)
        for button in self.detail_buttons:
            button.destroy()
        self.detail_buttons = []
        if item is None:
            c.surface(570)
            c.text(36, 48, 'Select an achievement to inspect its record.', 22, width=w-72)
            self.detail.extent(570)
            return
        earned = item.id in self.unlocked
        current, target = item.progress(self.records, self.unlocked)
        if self.mode:
            self.draw_compact_detail(item, earned, current, target)
            return
        # Scale only the art and headline; body text keeps a readable native size.
        art_size = min(275, max(192, w*.52))
        y = 180+art_size
        height = max(570, y+(300 if earned else 155))
        c.surface(height)
        c.text(44, 46, 'EARNED' if earned else 'LOCKED', 23, color=RED, weight='bold')
        c.art('paperclip', 76, 14, 26, 48)
        title = c.text(44, 81, item.title, 29 if w > 430 else 24, weight='bold', width=w-88)
        bounds = c.bbox(title)
        art_y = max(160, bounds[3]+20)+art_size/2
        self.art.draw(c, item, round(art_size), clear=False, x=w/2, y=art_y)
        y = art_y+art_size/2+26
        c.rule(y, 40, w-40)
        description = c.text(44, y+16, item.description, 17, width=w-88)
        y = c.bbox(description)[3]+24
        c.progress(44, y, w-88, target if earned else current, target, 18)
        c.text(44, y+28, f'Progress: {target if earned else current} / {target}', 13, family='DejaVu Sans Mono')
        y += 68
        if earned:
            timestamp = c.text(44, y, completion_time(self.unlocked[item.id]), 13, width=w-88)
            y = c.bbox(timestamp)[3]+14
            message = c.text(44, y, 'Recovered achievements use the detection timestamp because the original completion time is unavailable.', 12, color=PAPER_MUTED, width=w-88)
            y = c.bbox(message)[3]+18
            media = self.store.media.get(item.id, {})
            if not media:
                message = c.text(44, y, 'No capture was saved for this completion.', 13, color=PAPER_MUTED, width=w-88)
                y = c.bbox(message)[3]+16
            for kind, label in (('image', 'View screenshot'), ('clip', 'Play clip')):
                if kind not in media:
                    continue
                try:
                    if not media_path(self.root, media[kind]).is_file():
                        raise ValueError('Missing capture')
                except (OSError, ValueError):
                    message = c.text(44, y, ('Screenshot' if kind == 'image' else 'Clip')+' unavailable: capture file is missing or unsafe.', 13, color=RED, width=w-88)
                    y = c.bbox(message)[3]+12
                    continue
                button = self.app.translated_widget(ttk.Button(c, text=label, command=lambda name=media[kind]: self.open_capture(name)))
                self.detail_buttons.append(button)
                c.window(button, 44, y, min(220, w-88), 34)
                button.bind('<FocusIn>', lambda event, button=button: self.detail.reveal(button))
                y += 44
        else:
            message = c.text(44, y, 'Complete the requirement to earn this achievement.', 12, family='DejaVu Sans Mono', width=w-88)
            y = c.bbox(message)[3]+32
        self.detail.extent(max(570, y+30))

    def draw_compact_detail(self, item, earned, current, target):
        """Keep the record readable beside a small icon in short stacked panes."""
        from tkinter import ttk
        from .achievement_media import media_path
        c = self.detail.content
        w = c.winfo_width()
        c.surface(340)
        c.text(24, 16, 'EARNED' if earned else 'LOCKED', 15, color=RED, weight='bold')
        title = c.text(24, 40, item.title, 21, weight='bold', width=w-164)
        self.art.draw(c, item, 96, clear=False, x=w-72, y=66)
        y = max(78, c.bbox(title)[3]+12)
        description = c.text(24, y, item.description, 14, width=w-164)
        y = max(126, c.bbox(description)[3]+18)
        c.progress(24, y, w-48, target if earned else current, target, 12)
        c.text(24, y+20, f'Progress: {target if earned else current} / {target}', 12)
        y += 52
        if earned:
            label = c.text(24, y, completion_time(self.unlocked[item.id]), 12, width=w-48)
            y = c.bbox(label)[3]+14
            label = c.text(24, y, 'Recovered achievements use the detection timestamp because the original completion time is unavailable.', 12,
                           color=PAPER_MUTED, width=w-48)
            y = c.bbox(label)[3]+14
            media = self.store.media.get(item.id, {})
            if not media:
                c.text(24, y, 'No capture was saved for this completion.', 12, color=PAPER_MUTED, width=w-48)
                y += 36
            for kind, text in (('image', 'View screenshot'), ('clip', 'Play clip')):
                if kind not in media:
                    continue
                try:
                    if not media_path(self.root, media[kind]).is_file():
                        raise ValueError('Missing capture')
                except (OSError, ValueError):
                    label = c.text(24, y, text+' unavailable: capture file is missing or unsafe.', 12, color=RED, width=w-48)
                    y = c.bbox(label)[3]+12
                    continue
                button = self.app.translated_widget(ttk.Button(c, text=text, command=lambda name=media[kind]: self.open_capture(name)))
                self.detail_buttons.append(button)
                c.window(button, 24, y, 190, 34)
                button.bind('<FocusIn>', lambda event, button=button: self.detail.reveal(button))
                y += 44
        else:
            c.text(24, y, 'Complete the requirement to earn this achievement.', 12, color=PAPER_MUTED, width=w-48)
            y += 48
        self.detail.extent(max(250, y+24))
    def open_capture(self, filename):
        from tkinter import messagebox, ttk
        from .achievement_media import media_path
        import subprocess
        try:
            path = media_path(self.root, filename)
            if not path.is_file():
                raise ValueError('Capture file is missing')
            if path.suffix == '.mp4':
                subprocess.Popen(['xdg-open', str(path)], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                with Image.open(path) as source:
                    picture = source.convert('RGB')
                picture.thumbnail((1000, 650))
                viewer = tk.Toplevel(self.window)
                viewer.launcher = self.app
                viewer.translation_title = 'Achievement screenshot'
                viewer.title(self.app.tr(viewer.translation_title))
                viewer.configure(background=OLIVE)
                viewer.capture_image = ImageTk.PhotoImage(picture)
                ttk.Label(viewer, image=viewer.capture_image).pack(padx=12, pady=12)
                self.app.translated_widget(ttk.Button(viewer, text='Close', command=viewer.destroy)).pack(pady=(0, 12))
                viewer.bind('<Escape>', lambda event: viewer.destroy())
                viewer.bind('<Destroy>', lambda event: setattr(viewer, 'capture_image', None)
                            if event.widget is viewer else None, add='+')
        except (OSError, ValueError) as error:
            messagebox.showerror(self.app.tr('Capture unavailable'), self.app.tr(str(error)), parent=self.window)

    def cleanup(self, event):
        if event.widget is self.window:
            self.reset_wheel()
            if self.job:
                self.window.after_cancel(self.job)
                self.job = None
            self.art.images.clear()
            self.rows.clear()


BACKUP_LABELS = {'manual': 'Manual snapshot', 'saved': 'Game save', 'before-save': 'Before save',
                 'before-restore': 'Recovery snapshot', 'imported': 'Imported backup'}


def snapshot_date(item):
    import datetime
    instant = datetime.datetime.fromtimestamp(item['created_ns']/1e9)
    return instant.strftime('%d %b %Y · %H:%M:%S')


class BackupRow(PaperCanvas):
    def __init__(self, parent, view, item, index):
        super().__init__(parent, view.app.assets, takefocus=True, cursor='hand2', height=88, load_paper=False)
        self.view, self.item = view, item
        self.render = self.draw
        self.bind('<Button-1>', lambda event: self.focus_set())
        self.bind('<FocusIn>', lambda event: view.select(item['id'], reveal=True))
        self.bind('<FocusOut>', lambda event: self.schedule())
        for key, target in (('Down', index+1), ('Up', index-1), ('Home', 0), ('End', len(view.snapshots)-1)):
            self.bind('<'+key+'>', lambda event, target=target: view.move(target))
        self.bind('<Return>', lambda event: view.select(item['id']))
        self.bind('<space>', lambda event: view.select(item['id']))

    def draw(self):
        w, h = self.surface(88)
        if self.item['id'] == self.view.selected:
            self.highlight(h)
            self.text(w-18, h/2, '›', 30, color=RED, anchor='center')
        else:
            self.rule(h-1, 0, w)
        # Draw an original ribbon spool directly as native vector geometry.
        self.spool(50, 46)
        self.text(102, 22, snapshot_date(self.item), 17, family='DejaVu Sans Mono')
        self.text(102, 50, BACKUP_LABELS.get(self.item['label'], self.item['label']), 13, family='DejaVu Sans Mono', width=w-145)
        if w > 640:
            self.create_rectangle(w-228, 25, w-83, 54, outline='#a49370')
            self.text(w-155, 39, self.item['label'], 13, family='DejaVu Sans Mono', anchor='center')
        if self.focus_get() is self:
            self.create_rectangle(7, 4, w-7, h-5, outline=RED, dash=(3, 3))

    def spool(self, x, y):
        self.art('ribbon-spools', x, y, 80, 72)
        if self.photos.get(('ribbon-spools', 80, 72)):
            return
        self.create_polygon(x-28, y-17, x+20, y-9, x+29, y+21, x-23, y+12,
                            fill='#24231d', outline='#756249', width=2, smooth=True)
        for dx, dy in ((-18, -5), (18, 5)):
            self.create_oval(x+dx-13, y+dy-11, x+dx+13, y+dy+11, fill='#74674b', outline=INK, width=2)
            self.create_oval(x+dx-7, y+dy-6, x+dx+7, y+dy+6, fill='#c5b18c', outline=INK)


class BackupsView:
    def __init__(self, app, root):
        from tkinter import ttk
        self.app, self.root = app, root
        self.chrome = CaseDialog(app, 'Save backups', self.close, minimum=(640, 520), footer='●  Local save snapshots')
        self.window, self.frame, self.body = self.chrome.window, self.chrome.frame, self.chrome.body
        self.window.view = self
        self.snapshots, self.rows, self.selected = [], {}, None
        self.loaded, self.mode = False, None
        self.notice = 'Loading snapshots…'
        self.close_button = self.chrome.action('Close', self.close)
        self.refresh_button = self.chrome.action('Refresh', self.refresh)
        self.chrome.footer_buttons.reverse()
        self.catalog = CasePaperPane(self.body, app.assets, render=self.draw_catalog)
        self.detail = CasePaperPane(self.body, app.assets, render=self.draw_detail)
        self.create_button = ArtworkButton(self.catalog.content, 'SNAPSHOT NOW', self.create, kind='primary')
        self.import_button = ArtworkButton(self.catalog.content, 'IMPORT BACKUP', self.import_backup, kind='paper-outline')
        self.export_button = ArtworkButton(self.detail.content, 'EXPORT', self.export, kind='paper-outline')
        self.restore_button = ArtworkButton(self.detail.content, 'RESTORE', self.restore, kind='primary')
        self.delete_button = ArtworkButton(self.detail.content, 'Delete snapshot', self.delete, kind='danger')
        self.include_media = tk.BooleanVar(value=False)
        self.media_option = self.app.translated_widget(ttk.Checkbutton(self.detail.content, text='Include achievement media',
                                            variable=self.include_media, style='Paper.TCheckbutton'))
        self.body.bind('<Configure>', self.layout)
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.window.bind(sequence, self.scroll)
        self.refresh()

    # Share responsive paper placement and per-pane wheel routing.
    layout = AchievementsView.layout
    scroll = AchievementsView.scroll_panes

    def close(self):
        self.window.destroy()
        self.app.window.lift()

    def busy_changed(self):
        if not self.window.winfo_exists():
            return
        busy = self.app.child is not None
        for button in (self.create_button, self.import_button, self.refresh_button):
            button.configure(state='disabled' if busy else 'normal')
        for button in (self.export_button, self.restore_button, self.delete_button):
            button.configure(state='normal' if not busy and self.loaded and self.selected else 'disabled')
        self.media_option.configure(state='normal' if not busy and self.loaded and self.selected else 'disabled')
        self.chrome.footer = self.app.status.get() if busy else self.notice
        self.chrome.schedule()

    def run(self, command, *args, refresh=False):
        if self.app.child is not None or not self.window.winfo_exists():
            return
        def complete(code):
            if not self.window.winfo_exists():
                return
            if code:
                self.notice = 'Operation failed. View launcher logs for details, then try again.'
                self.busy_changed()
            elif refresh:
                self.refresh()
            else:
                self.notice = self.app.status.get()
                self.busy_changed()
        self.app.start(command, *args, '--game', self.root, on_complete=complete)
        if self.app.child is None:
            self.notice = 'Could not start the operation. Try again.'
            self.busy_changed()

    def refresh(self):
        if self.app.child is not None or not self.window.winfo_exists():
            return
        self.notice = 'Loading snapshots…'
        self.app.start('backups', '--game', self.root, on_complete=self.load)
        if self.app.child is None:
            self.notice = 'Could not start loading snapshots. Try again.'
        self.busy_changed()

    def load(self, code):
        if not self.window.winfo_exists():
            return
        if code:
            self.loaded = False
            self.notice = 'Could not load snapshots. View launcher logs, then refresh.'
            self.busy_changed()
            return
        import json
        try:
            result = json.loads(self.app.last_output)
            if not isinstance(result, list):
                raise ValueError('Expected a snapshot list')
            for item in result:
                identity = item['id']
                if not isinstance(identity, str) or len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
                    raise ValueError('Invalid snapshot identifier')
                if not isinstance(item['label'], str) or not isinstance(item['files'], dict):
                    raise ValueError('Invalid snapshot metadata')
                snapshot_date(item)
            focused = next((key for key, row in self.rows.items() if self.window.focus_get() is row), None)
            for row in self.rows.values():
                row.destroy()
            self.snapshots, self.rows, self.loaded = result, {}, True
            if self.selected not in {item['id'] for item in result}:
                self.selected = result[0]['id'] if result else None
            for index, item in enumerate(result):
                self.rows[item['id']] = BackupRow(self.catalog.content, self, item, index)
            self.notice = '●  Local save snapshots' if result else 'No snapshots yet. Choose Snapshot now to back up your saves.'
            self.catalog.content.redraw()
            self.detail.content.redraw()
            if focused in self.rows:
                self.rows[focused].focus_set()
        except (ValueError, KeyError, TypeError, OverflowError, OSError) as error:
            self.loaded = False
            self.app.append('Cannot read backup listing: '+str(error)+'\n')
            self.notice = 'Could not read snapshots. View launcher logs, then refresh.'
        self.busy_changed()

    def select(self, identity, reveal=False):
        self.selected = identity
        for row in self.rows.values():
            row.schedule()
        if reveal and identity in self.rows:
            self.catalog.reveal(self.rows[identity])
        self.detail.content.redraw()
        self.detail.canvas.yview_moveto(0)
        self.busy_changed()

    def move(self, index):
        if self.snapshots:
            self.rows[self.snapshots[max(0, min(index, len(self.snapshots)-1))]['id']].focus_set()
        return 'break'

    def draw_catalog(self):
        c = self.catalog.content
        w = c.winfo_width()
        narrow = w < 580
        compact = bool(self.mode)
        start = 140 if compact else 310 if narrow else 300
        height = max(570, start+len(self.snapshots)*88+24)
        c.surface(height)
        if compact:
            c.art('backups', 51, 42, 48)
            c.text(90, 16, 'SAVE BACKUPS', 23, weight='bold')
            c.text(90, 48, 'All your saves · Stop the game before managing backups.', 12, width=w-116)
        else:
            c.art('backups', 116 if not narrow else 86, 94, 172 if not narrow else 115, 154)
            c.text(220 if not narrow else 160, 47, 'SAVE BACKUPS', 30 if not narrow else 24, weight='bold', width=w-(252 if not narrow else 190))
            c.text(220 if not narrow else 32, 109 if not narrow else 181,
                   'Each snapshot contains all your saves.\nStop the game before managing backups.', 13,
                   family='DejaVu Sans Mono', width=w-(252 if not narrow else 64))
            if w > 740:
                c.stamp(w-72, 76, 75)
        by = 78 if compact else 226 if narrow else 203
        bw = (w-76)/2
        for index, button in enumerate((self.create_button, self.import_button)):
            button.scale = .85 if narrow else 1
            c.window(button, 32+index*(bw+12), by, bw, 34 if compact else 48)
        c.text(32, start-24 if compact else start-30, f'{len(self.snapshots)} snapshots' if self.loaded else 'Loading snapshots…', 14, family='DejaVu Sans Mono')
        for index, item in enumerate(self.snapshots):
            c.window(self.rows[item['id']], 22, start+index*88, w-44, 88)
        if self.loaded and not self.snapshots:
            c.rule(start, 32, w-32)
            c.text(32, start+26, 'Your saves, kept together.', 23, weight='bold', width=w-64)
            c.text(32, start+72, 'Create your first snapshot before your next session. Import a backup to move saves from another installation.', 15, width=w-64)
        self.catalog.extent(height)

    def draw_detail(self):
        c = self.detail.content
        w = c.winfo_width()
        item = next((item for item in self.snapshots if item['id'] == self.selected), None)
        c.surface(224 if self.mode else 570)
        if item is None:
            self.media_option.place_forget()
            c.text(42, 48, 'Save snapshots', 30, weight='bold', width=w-84)
            c.art('backups', w/2, 263, min(285, w-80))
            c.text(42, 448, 'Select a snapshot to export, restore or delete it.', 17, width=w-84)
            self.detail.extent(570)
            return
        if self.mode:
            c.text(24, 8, BACKUP_LABELS.get(item['label'], item['label']), 22, weight='bold', width=w-160)
            c.text(24, 34, snapshot_date(item), 13, family='DejaVu Sans Mono', width=w-160)
            c.art('backups', w-70, 43, 86, 72)
            c.window(self.media_option, 24, 54, w-140, 24)
            bw = (w-60)/2
            for index, button in enumerate((self.export_button, self.restore_button)):
                c.window(button, 24+index*(bw+12), 84, bw, 34)
            c.window(self.delete_button, 24, 130, bw, 34)
            c.text(36+bw, 131, 'A recovery copy is kept before restoring.', 12, color=PAPER_MUTED, width=bw)
            c.text(24, 180, f'All saves in one snapshot · {len(item["files"])} files', 12, family='DejaVu Sans Mono', width=w-48)
            self.detail.extent(224)
            return
        c.text(42, 48, BACKUP_LABELS.get(item['label'], item['label']), 30, weight='bold', width=w-84)
        c.art('paperclip', 76, 14, 26, 48)
        c.text(42, 117, snapshot_date(item), 15, family='DejaVu Sans Mono', width=w-84)
        c.art('backups', w/2, 288, min(350, w-78), 262)
        c.art('ribbon-spools', w*.76, 372, min(128, w*.25), 100)
        c.rule(420, 40, w-40)
        count = len(item['files'])
        c.text(42, 425, f'All saves in one snapshot · {count} '+('file' if count == 1 else 'files'), 13,
               family='DejaVu Sans Mono', width=w-84)
        c.window(self.media_option, 42, 445, w-84, 28)
        bw = (w-96)/2
        for index, button in enumerate((self.export_button, self.restore_button)):
            c.window(button, 42+index*(bw+12), 480, bw, 42)
        c.window(self.delete_button, 42, 538, bw, 36)
        c.text(54+bw, 540, 'A recovery copy is kept before restoring.', 12, color=PAPER_MUTED, width=bw)
        self.detail.extent(604)

    def create(self):
        self.run('backup', refresh=True)

    def import_backup(self):
        from tkinter import filedialog
        if self.app.child:
            return
        source = filedialog.askopenfilename(parent=self.window, title=self.app.tr('Import backup'), filetypes=[(self.app.tr('Save backup'), '*.zip')])
        if source:
            self.run('import-backup', source, refresh=True)

    def export(self):
        from tkinter import filedialog
        if not self.selected or self.app.child:
            return
        destination = filedialog.asksaveasfilename(parent=self.window, title=self.app.tr('Export backup'), defaultextension='.zip',
                                                   initialfile='re4-saves-'+self.selected[:12]+'.zip', filetypes=[(self.app.tr('Save backup'), '*.zip')])
        if destination:
            arguments = ('--include-media',) if self.include_media.get() else ()
            self.run('export-backup', self.selected, destination, *arguments)

    def restore(self):
        from tkinter import messagebox
        if self.selected and not self.app.child and messagebox.askyesno(self.app.tr('Restore saves'),
                self.app.tr('Replace current saves with this snapshot? A recovery copy will be kept.'), parent=self.window):
            self.run('restore-backup', self.selected, refresh=True)

    def delete(self):
        from tkinter import messagebox
        item = next((item for item in self.snapshots if item['id'] == self.selected), None)
        if item and not self.app.child and messagebox.askyesno(self.app.tr('Delete snapshot'),
                self.app.tr('Delete {label} from {date}?').format(
                    label=self.app.tr(BACKUP_LABELS.get(item['label'], item['label'])), date=snapshot_date(item))+
                '\n\n'+self.app.tr('Current saves are kept. This snapshot cannot be recovered.'), parent=self.window):
            self.run('delete-backup', self.selected, refresh=True)
