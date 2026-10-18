"""Textured native surfaces shared by the launcher case-file windows.

Artwork is presentation only. Text, focus targets, forms and actions remain
real Tk widgets, and each paper has its own scroll region.
"""
import tkinter as tk
from PIL import Image, ImageOps, ImageTk
from .languages import widget_translate

INK = '#211b13'
IVORY = '#eee2c8'
PAPER = '#e7d8b9'
RED = '#78190f'
MUTED = '#65583f'


def font(size=18, family='DejaVu Serif', weight='normal'):
    return family, -round(size), weight


class PaperCanvas(tk.Canvas):
    def create_text(self, *args, **options):
        if 'text' in options:
            options['text'] = widget_translate(self, options['text'])
        return super().create_text(*args, **options)

    def __init__(self, parent, assets, *, render=None, load_paper=True, **options):
        super().__init__(parent, background=PAPER, highlightthickness=0, **options)
        self.render = render
        self.paper = None
        self.photo = None
        self.bitmap = None
        self.photos = {}
        self.sources = {}
        self.backdrop = None
        self.assets = assets
        self.job = None
        self.render_size = None
        if load_paper:
            try:
                path = assets / 'case-paper-v2.png'
                with Image.open(path if path.is_file() else assets / 'paper.png') as image:
                    self.paper = image.convert('RGB')
            except OSError:
                pass
        self.bind('<Configure>', self.schedule)
        self.bind('<Destroy>', self.cleanup, add='+')

    def schedule(self, event=None):
        if event is not None and event.type == tk.EventType.Configure:
            size = (event.width, event.height)
            if size == self.render_size:
                # Scrolling moves this window too. Repainting would detach and
                # recreate all its embedded rows even though their size is fixed.
                return
            self.render_size = size
        if self.job:
            self.after_cancel(self.job)
        self.job = self.after_idle(self.scheduled_redraw)

    def scheduled_redraw(self):
        self.job = None
        self.redraw()

    def redraw(self):
        if self.job:
            self.after_cancel(self.job)
        self.job = None
        if self.render and self.winfo_width() > 100:
            self.render()

    def surface(self, height=None):
        self.delete('all')
        width = max(1, self.winfo_width())
        height = max(1, height or self.winfo_height())
        if getattr(self, 'fills_viewport', False):
            height = max(height, self.master.winfo_height())
        height = round(height)
        if self.backdrop or self.paper:
            paint_height = max(570, self.master.winfo_height()) if getattr(self, 'fills_viewport', False) else height
            if height <= paint_height*1.5:
                paint_height = height
            texture = (self.backdrop or self.paper).resize((width, min(height, paint_height)), Image.Resampling.LANCZOS)
            self.bitmap = Image.new('RGB', (width, height))
            for y in range(0, height, texture.height):
                self.bitmap.paste(texture, (0, y))
            self.photo = ImageTk.PhotoImage(self.bitmap)
            self.create_image(0, 0, image=self.photo, anchor='nw')
        return width, height

    def highlight(self, height):
        if self.bitmap:
            self.photo = ImageTk.PhotoImage(Image.blend(self.bitmap, Image.new('RGB', self.bitmap.size, RED), .12))
            self.create_image(0, 0, image=self.photo, anchor='nw')
        self.create_rectangle(0, 0, 5, height, fill=RED, outline='')
        self.create_rectangle(1, 1, self.winfo_width()-2, height-2, outline='#b37d61')

    def text(self, x, y, text, size=18, *, color=INK, width=None, weight='normal',
             family='DejaVu Serif', anchor='nw'):
        scale = min(1.2, max(1, self.winfo_toplevel().winfo_width()/1280))
        return self.create_text(x, y, text=text, fill=color, font=font(size*scale, family, weight),
                                anchor=anchor, width=width or 0)

    def rule(self, y, x=32, end=None):
        self.create_line(x, y, end or self.winfo_width() - 32, y, fill='#a49370')

    def art(self, name, x, y, width, height=None, *, anchor='center'):
        height = height or width
        key = name, int(width), int(height)
        if key not in self.photos:
            try:
                if name not in self.sources:
                    with Image.open(self.assets / (name + '.png')) as image:
                        source = image.convert('RGBA')
                    bounds = source.getchannel('A').point(lambda a: 255 if a > 8 else 0).getbbox()
                    self.sources[name] = source.crop(bounds) if bounds else source
                image = ImageOps.contain(self.sources[name], (max(1, int(width)), max(1, int(height))),
                                        Image.Resampling.LANCZOS)
                self.photos[key] = ImageTk.PhotoImage(image)
            except OSError:
                self.photos[key] = None
        if self.photos[key]:
            self.create_image(x, y, image=self.photos[key], anchor=anchor)

    def stamp(self, x, y, size=64):
        self.art('case-seal', x, y, size)
        if self.photos.get(('case-seal', int(size), int(size))):
            return
        # Missing-art fallback; decorative, never an achievement state marker.
        import math
        self.create_oval(x-size/2, y-size/2, x+size/2, y+size/2, outline='#9c3a28', width=2, dash=(9, 2))
        points = []
        for i in range(16):
            angle = -math.pi/2 + i*math.pi/8
            radius = size*(.31 if i % 2 == 0 else .09)
            points.extend((x+math.cos(angle)*radius, y+math.sin(angle)*radius))
        self.create_polygon(points, fill='', outline='#9c3a28', width=2)

    def progress(self, x, y, width, current, target, height=14):
        self.create_rectangle(x, y, x+width, y+height, fill='#cabb9c', outline='#887757')
        amount = min(1, max(0, current/max(1, target)))
        if amount:
            self.create_rectangle(x+1, y+1, x+max(2, width*amount)-1, y+height-1, fill=RED, outline='')

    def window(self, widget, x, y, width, height=None):
        options = {'width': max(1, width)}
        if height:
            options['height'] = height
        self.create_window(x, y, window=widget, anchor='nw', **options)
        if isinstance(widget, PaperCanvas) and self.bitmap and height:
            widget.backdrop = self.bitmap.crop((int(x), int(y), int(x+max(1, width)), int(y+height)))
            widget.schedule()
        if hasattr(widget, 'surface') and not callable(widget.surface) and self.bitmap and height:
            # The widget draws its exact patch of the paper, not an opaque box.
            patch = self.bitmap.crop((int(x), int(y), int(x+max(1, width)), int(y+height)))
            widget.surface = ImageTk.PhotoImage(patch)
            widget.draw()

    def cleanup(self, event):
        if event.widget is self:
            if self.job:
                self.after_cancel(self.job)
                self.job = None
            self.photos.clear()
            self.sources.clear()
            self.photo = self.paper = self.bitmap = self.backdrop = None


class PaperPane:
    def __init__(self, parent, assets, *, render=None):
        from tkinter import ttk
        self.frame = ttk.Frame(parent, style='Paper.TFrame')
        self.canvas = tk.Canvas(self.frame, background=PAPER, highlightthickness=0, yscrollincrement=24)
        self.bar = ttk.Scrollbar(self.frame, command=self.canvas.yview)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.canvas.configure(yscrollcommand=self.scrolled)
        self.content = PaperCanvas(self.canvas, assets, render=render)
        self.content.fills_viewport = True
        self.wheel_remainder = 0
        self.identity = self.canvas.create_window(0, 0, anchor='nw', window=self.content)
        self.canvas.bind('<Configure>', self.resize)
        self.content.bind('<Configure>', self.update_region, add='+')

    def resize(self, event):
        self.canvas.itemconfigure(self.identity, width=event.width)

    def update_region(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox(self.identity))

    def extent(self, height):
        self.content.configure(height=round(max(1, height, self.canvas.winfo_height())))
        self.update_region()

    def scrolled(self, first, last):
        self.bar.set(first, last)
        if float(last)-float(first) >= .999:
            self.bar.place_forget()
        elif not self.bar.winfo_manager():
            # Overlay the scroll affordance without changing the text width.
            # Otherwise a wrapping headline can make the scrollbar oscillate.
            self.bar.place(relx=1, x=-10, y=6, relheight=1, height=-12, width=8)

    def wheel_steps(self, event):
        if getattr(event, 'num', None) in (4, 5):
            return -1 if event.num == 4 else 1
        unit = 1 if self.canvas.tk.call('tk', 'windowingsystem') == 'aqua' else 120
        self.wheel_remainder -= getattr(event, 'delta', 0) / unit
        steps = int(self.wheel_remainder)
        self.wheel_remainder -= steps
        return steps

    def scroll(self, event):
        steps = self.wheel_steps(event)
        if steps:
            self.canvas.yview_scroll(steps * 3, 'units')
        return 'break'

    def reveal(self, widget):
        self.canvas.update_idletasks()
        y = widget.winfo_rooty() - self.content.winfo_rooty()
        top = self.canvas.canvasy(0)
        bottom = top + self.canvas.winfo_height()
        if y < top or y + widget.winfo_height() > bottom:
            self.canvas.yview_moveto(max(0, y - 24) / max(1, self.content.winfo_height()))


class CaseDialog:
    def __init__(self, app, title, close, *, geometry='1280x720', minimum=(640, 520), footer=''):
        from .launcher_ui import ArtworkButton, dialog_styles
        from tkinter import ttk
        self.window = app.dialog(title, geometry)
        self.window.minsize(*minimum)
        dialog_styles(self.window)
        self.canvas = tk.Canvas(self.window, background='#171810', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.frame = ttk.Frame(self.canvas)
        self.body = ttk.Frame(self.frame)
        self.body.pack(fill='both', expand=True)
        self.body_id = self.canvas.create_window(18, 64, anchor='nw', window=self.frame)
        self.title, self.footer = title, footer
        self.app = app
        self.footer_buttons = []
        self.background = None
        self.photo = None
        self.job = None
        try:
            with Image.open(app.assets / 'case-file.png') as source:
                # Repeat the existing unlettered olive texture behind native content.
                self.background = source.convert('RGB').crop((1040, 0, 1650, 48))
        except OSError:
            pass
        self.back = ArtworkButton(self.canvas, 'Back to launcher', close, kind='nav')
        self.back.selected = False
        self.canvas.bind('<Configure>', self.schedule)
        self.window.bind('<Destroy>', self.cleanup, add='+')
        self.window.protocol('WM_DELETE_WINDOW', close)
        self.window.bind('<Escape>', lambda event: close())

    def action(self, text, command, *, primary=False, width=125):
        from .launcher_ui import ArtworkButton
        button = ArtworkButton(self.canvas, text, command, kind='primary' if primary else 'outline')
        self.footer_buttons.append((button, width))
        return button

    def schedule(self, event=None):
        if self.job:
            self.window.after_cancel(self.job)
        self.job = self.window.after_idle(self.draw)

    def draw(self):
        self.job = None
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.canvas.delete('chrome')
        if self.background:
            tile = Image.new('RGB', (w, h), '#171810')
            for x in range(0, w, self.background.width):
                for y in range(0, h, self.background.height):
                    tile.paste(self.background, (x, y))
            self.photo = ImageTk.PhotoImage(tile)
            self.canvas.create_image(0, 0, image=self.photo, anchor='nw', tags='chrome')
        self.canvas.create_line(0, 42, w, 42, fill='#74674b', tags='chrome')
        self.canvas.create_text(24, 21, text='r e 4 m e p c', fill=IVORY, font=font(16), anchor='w', tags='chrome')
        self.canvas.create_line(160, 9, 160, 38, fill='#74674b', tags='chrome')
        title = self.app.tr(self.title)
        title_item = self.canvas.create_text(204, 21, text=title, fill=IVORY, font=font(18), anchor='w', tags='chrome')
        title_end = self.canvas.bbox(title_item)[2]
        self.canvas.create_line(196, 39, title_end+6, 39, fill=RED, width=2, tags='chrome')
        self.back.place(x=min(w-180, title_end+16), y=0, width=170, height=40)
        self.canvas.coords(self.body_id, 18, 64)
        self.canvas.itemconfigure(self.body_id, width=max(1, w-36), height=max(1, h-138))
        self.canvas.create_line(20, h-55, w/2-14, h-55, fill='#a49370', tags='chrome')
        self.canvas.create_line(w/2+14, h-55, w-20, h-55, fill='#a49370', tags='chrome')
        self.canvas.create_text(w/2, h-55, text='✦', fill='#b69b62', font=font(17), tags='chrome')
        x = w-20
        for button, width in reversed(self.footer_buttons):
            x -= width
            button.place(x=x, y=h-45, width=width, height=34)
            x -= 10
        self.canvas.create_text(24, h-28, text=self.app.tr(self.footer), fill='#b7ad98', anchor='w',
                                font=font(14), width=max(80, x-40), tags='chrome')
        self.canvas.tag_lower('chrome')

    def cleanup(self, event):
        if event.widget is self.window:
            if self.job:
                self.window.after_cancel(self.job)
                self.job = None
            self.photo = self.background = None
