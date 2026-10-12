#!/usr/bin/env python3
"""Capture native dialogs using synthetic records and original fixture media only."""
import argparse
import datetime
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def capture(window, path, geometry):
    window.geometry(geometry + '+20+20')
    window.lift()
    window.update()
    end = time.monotonic() + .15
    while time.monotonic() < end:
        window.update()
        time.sleep(.01)
    from PIL import Image
    subprocess.run(['import', '-window', hex(window.winfo_id()), str(path)], check=True)
    with Image.open(path) as source:
        image = source.convert('RGB')
    image.save(path)


def fixtures(root):
    from PIL import Image, ImageDraw
    from re4pc.achievements import AchievementStore, Progress
    folder = root / 'synthetic game'
    media = folder / 'achievement-media'
    media.mkdir(parents=True)
    image = Image.new('RGB', (640, 384), '#27271b')
    draw = ImageDraw.Draw(image)
    draw.rectangle((50, 50, 590, 334), outline='#e7d8b9', width=3)
    draw.text((80, 160), 'Synthetic capture fixture / no gameplay media', fill='#e7d8b9')
    image.save(media / 'unlock-fixture.png')
    # A real tiny clip allows the external opener path to be checked with mocks.
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-loop', '1',
                    '-i', str(media / 'unlock-fixture.png'), '-t', '0.4', '-pix_fmt', 'yuv420p',
                    str(media / 'unlock-fixture.mp4')], check=True)
    stamp = int(datetime.datetime(2026, 10, 12, 19, 32, 8, tzinfo=datetime.timezone.utc).timestamp() * 1e9)
    story = (True,) + (False,) * 21
    store = AchievementStore(folder)
    store._write(Progress(story=story, purchased_weapons=(1, 2, 3), upgrades=6),
                 {'village': stamp, 'first_purchase': stamp, 'collector': stamp,
                  'first_upgrade': stamp, 'tuned': stamp})
    store.attach_media(['village'], {'image': 'unlock-fixture.png', 'clip': 'unlock-fixture.mp4'})
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artwork', action='store_true', help='Capture all inventory artwork at catalog/detail sizes')
    parser.add_argument('--check', action='store_true', help='Check published host-only previews and provenance')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/dialog-previews')
    args = parser.parse_args()
    if args.artwork:
        import tkinter as tk
        from tkinter import ttk
        from re4pc.achievements import ACHIEVEMENTS
        from re4pc.launcher_ui import AchievementArtwork, dialog_styles, PAPER
        args.output.mkdir(parents=True, exist_ok=True)
        window = tk.Tk()
        dialog_styles(window)
        window.configure(background=PAPER)
        artwork = AchievementArtwork(ROOT / 're4pc/ui_assets')
        try:
            for offset in range(0, len(ACHIEVEMENTS), 6):
                for child in window.winfo_children():
                    child.destroy()
                for index, item in enumerate(ACHIEVEMENTS[offset:offset + 6]):
                    panel = ttk.Frame(window, style='Paper.TFrame', padding=10)
                    panel.grid(row=index // 3, column=index % 3, sticky='nsew')
                    ttk.Label(panel, text=item.id, style='PaperTitle.TLabel').pack(anchor='w', pady=(0, 10))
                    for size in (72, 192):
                        canvas = tk.Canvas(panel, width=size, height=size, background=PAPER, highlightthickness=0)
                        canvas.pack(anchor='center', pady=8)
                        artwork.draw(canvas, item, size)
                        assert artwork.images[(item.id, size)] is not None, item.id
                for column in range(3):
                    window.columnconfigure(column, weight=1)
                for row in range(2):
                    window.rowconfigure(row, weight=1)
                capture(window, args.output / f'achievement-artwork-{offset // 6 + 1}.png', '900x700')
            print('ARTWORK_REVIEW_PASS')
        finally:
            window.destroy()
        return
    if args.check:
        from PIL import Image
        expected = {'settings-preview.png': (1280, 720), 'settings-minimum-preview.png': (640, 520),
                    'achievements-preview.png': (1280, 720), 'achievements-minimum-preview.png': (600, 420),
                    'backups-preview.png': (1280, 720), 'backups-minimum-preview.png': (640, 520)}
        for name, size in expected.items():
            with Image.open(ROOT / 'docs' / name) as image:
                assert image.size == size, name
        provenance = (ROOT / 'docs/launcher-assets.md').read_text()
        from re4pc.achievements import ACHIEVEMENTS
        assert all('achievement-' + item.id + '.png' in provenance for item in ACHIEVEMENTS)
        assert 'paper.png' in provenance and 'Synthetic' in (ROOT / 'docs/dialogs.md').read_text()
        print('DIALOG_PREVIEW_PASS')
        return
    import tkinter as tk
    from re4pc.launcher import Launcher
    from re4pc.settings import Settings
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='re4-dialog-fixtures-') as directory:
        fixture_root = Path(directory)
        game = fixtures(fixture_root)
        state = fixture_root / 'backup-state'
        from re4pc.backups import SaveStore
        with SaveStore(game, state / 're4mepc/backups') as store:
            store.saves.mkdir(exist_ok=True)
            for index, label in enumerate(('before-save', 'saved', 'manual')):
                (store.saves / 'fixture-slot').write_bytes(('synthetic save ' + str(index)).encode())
                store.snapshot(label)
        window = tk.Tk()
        try:
            window.geometry('1000x600+0+0')
            app = Launcher(window, game)
            with patch('re4pc.settings.Settings.load', return_value=Settings.load(fixture_root / 'settings.json')):
                settings = app.settings()
            capture(settings.window, args.output / 'settings-preview.png', '1280x720')
            settings.select('Keyboard')
            settings.fields[('keyboard', 'forward')][1].focus_force()
            capture(settings.window, args.output / 'settings-minimum-preview.png', '640x520')
            settings.window.destroy()
            achievements = app.achievements()
            capture(achievements.window, args.output / 'achievements-preview.png', '1280x720')
            capture(achievements.window, args.output / 'achievements-minimum-preview.png', '600x420')
            from tkinter import ttk
            actions = [child for child in achievements.detail.content.winfo_children() if isinstance(child, ttk.Button)]
            actions[0].focus_force()
            capture(achievements.window, args.output / 'achievements-minimum-scrolled.png', '600x420')
            achievements.search.set('no matching achievement')
            capture(achievements.window, args.output / 'achievements-filter-empty.png', '1040x760')
            achievements.search.set('')
            achievements.store.path.write_bytes(b'corrupt fixture')
            achievements.refresh()
            capture(achievements.window, args.output / 'achievements-record-error.png', '1040x760')
            achievements.window.destroy()
            with patch.dict(os.environ, {'XDG_STATE_HOME': str(state)}):
                backups = app.backups()
                end = time.monotonic() + 10
                while app.child is not None and time.monotonic() < end:
                    window.update()
                    time.sleep(.02)
                assert app.child is None and backups.loaded and len(backups.snapshots) == 3
                capture(backups.window, args.output / 'backups-preview.png', '1280x720')
                capture(backups.window, args.output / 'backups-minimum-preview.png', '640x520')
                backups.window.destroy()
            print('DIALOG_CAPTURE_PASS')
        finally:
            window.destroy()


if __name__ == '__main__':
    main()
