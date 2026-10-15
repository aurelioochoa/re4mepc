"""Validate both releases on clean Linux images with host Mesa and Xvfb.

Images contain graphics/display support but no Python or compiler. Game data is
an isolated user-supplied fixture mounted separately from the release. Reports
are external to the source checkout. This is an automated smoke check, not a
complete campaign or physical-controller certification.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from re4pc.paths import game_dir, isolated_game, test_output
from re4pc.achievements import AchievementStore, Progress
from re4pc.backups import _canonical, _digest

BASES = {
    'ubuntu22': ('ubuntu:22.04', 'apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libgl1-mesa-dri libglx-mesa0 libgbm1 libstdc++6 libgcc-s1 xvfb xauth ca-certificates'),
    'ubuntu24': ('ubuntu:24.04', 'apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libgl1-mesa-dri libglx-mesa0 libgbm1 libstdc++6 libgcc-s1 xvfb xauth ca-certificates'),
    'arch': ('archlinux:base', 'pacman -Syu --noconfirm && pacman -S --noconfirm mesa libglvnd xorg-server-xvfb xorg-xauth diffutils')}

# Executed by each package's own interpreter; the clean host has no Python.
LANGUAGE_CHECK = r'''import ctypes as C
import json
import sys
import tkinter as tk
from pathlib import Path
from re4pc.launcher import Launcher, configure_bundled_fonts
from re4pc.languages import LAUNCHER_LANGUAGES, GAME_LANGUAGE_IDS, translate
from re4pc.settings import Settings
import re4pc

runtime, output, engine_check = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] == 'yes'
assert Path(re4pc.__file__).resolve().is_relative_to(runtime.resolve())
assert (runtime/'usr/share/fonts/opentype/ipafont-gothic/ipag.ttf').stat().st_size > 0
assert (runtime/'usr/share/doc/fonts-ipafont-gothic/copyright').stat().st_size > 0
configure_bundled_fonts()

# Require actual Japanese glyph coverage from a bundled font, not a tofu fallback.
fc = C.CDLL('libfontconfig.so.1')
fc.FcNameParse.argtypes = (C.c_char_p,); fc.FcNameParse.restype = C.c_void_p
fc.FcConfigSubstitute.argtypes = (C.c_void_p, C.c_void_p, C.c_int)
fc.FcDefaultSubstitute.argtypes = (C.c_void_p,)
fc.FcFontMatch.argtypes = (C.c_void_p, C.c_void_p, C.POINTER(C.c_int)); fc.FcFontMatch.restype = C.c_void_p
fc.FcPatternGetString.argtypes = (C.c_void_p, C.c_char_p, C.c_int, C.POINTER(C.c_char_p))
fc.FcPatternGetCharSet.argtypes = (C.c_void_p, C.c_char_p, C.c_int, C.POINTER(C.c_void_p))
fc.FcCharSetHasChar.argtypes = (C.c_void_p, C.c_uint); fc.FcCharSetHasChar.restype = C.c_int
fc.FcPatternDestroy.argtypes = (C.c_void_p,)
pattern = fc.FcNameParse(b'sans:lang=ja')
fc.FcConfigSubstitute(None, pattern, 0); fc.FcDefaultSubstitute(pattern)
result = C.c_int()
match = fc.FcFontMatch(None, pattern, C.byref(result))
assert match
font = C.c_char_p(); charset = C.c_void_p()
assert fc.FcPatternGetString(match, b'file', 0, C.byref(font)) == 0
assert Path(font.value.decode()).resolve().is_relative_to(runtime.resolve())
assert fc.FcPatternGetCharSet(match, b'charset', 0, C.byref(charset)) == 0
assert all(fc.FcCharSetHasChar(charset, ord(char)) for char in '日本語プレイ')
font_path = font.value.decode()
fc.FcPatternDestroy(match); fc.FcPatternDestroy(pattern)

def texts(widget):
    found = []
    if isinstance(widget, tk.Canvas):
        found += [widget.itemcget(item, 'text') for item in widget.find_all() if widget.type(item) == 'text']
    for child in widget.winfo_children(): found += texts(child)
    return found

original = dict(Settings.load())
records = []
for code in LAUNCHER_LANGUAGES:
    Settings.save({**original, 'launcher_language': code, 'game_language': 'saved'})
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
    try:
        app = Launcher(root, Path('/game inputs'))
        root.update()
        assert app.launcher_language == code and app.game_language.get() == 'saved'
        assert translate('Import APK', code) in texts(app.import_button)
        control, variable, choices = app.view.language_controls['game_language']
        control.current(tuple(choices).index(code)); control.event_generate('<<ComboboxSelected>>')
        root.update()
        saved = Settings.load()
        assert saved['launcher_language'] == code and saved['game_language'] == code
        restarted_window = tk.Toplevel(root)
        restarted = Launcher(restarted_window, Path('/game inputs'))
        root.update()
        assert restarted.launcher_language == code and restarted.game_language.get() == code
        restarted_window.destroy()
        assert not errors, errors
        record = {'language': code, 'launcher': True, 'preferences_restored': True}
    finally:
        root.destroy()
    if engine_check:
        from re4pc.game import Game
        game = Game(Path('/game inputs'), language=code, skip_videos=True)
        try:
            for _ in range(3):
                game.frame(); game.present()
            user = game.arm.symbols['_ZZN13Bio4_UserData11GetInstanceEvE4inst']
            native_language = game.arm.call('_ZNK13Bio4_UserData9GetLangIdEv', user)
            assert native_language == GAME_LANGUAGE_IDS[code]
        except BaseException:
            game.close()
            raise
        stats = game.run(160, replay_only=True)
        assert stats['frames'] == 160 and stats['draw_calls'] > 100 and not stats['gl_messages']
        record['engine_ticks'] = stats['frames']
        record['native_language_id'] = native_language
    records.append(record)
Settings.save(original)
output.write_text(json.dumps({'runtime': str(runtime), 'japanese_font': font_path, 'languages': records}, indent=2)+'\n')
print('PACKAGED_LANGUAGES_PASS', output)
'''

SCRIPT = r'''set -eu
! command -v python3
! command -v cc
mkdir -p '/tmp/portable release' '/tmp/appimage runtime' '/tmp/user data' '/tmp/user state' '/tmp/user config' '/tmp/user cache'
tar -xzf '/release files/re4mepc-linux-x86_64.tar.gz' -C '/tmp/portable release'
export XDG_DATA_HOME='/tmp/user data' XDG_STATE_HOME='/tmp/user state' XDG_CONFIG_HOME='/tmp/user config' XDG_CACHE_HOME='/tmp/user cache'
export LIBGL_ALWAYS_SOFTWARE=1 SDL_AUDIODRIVER=dummy
export APPIMAGE_EXTRACT_AND_RUN=1 TMPDIR=/tmp
mkdir -p '/tmp/bundle destination' '/tmp/save only destination'
if [ -n "${PREVIOUS_DIST:-}" ]; then
  mkdir -p '/tmp/previous release'
  tar -xzf "$PREVIOUS_DIST/re4mepc-linux-x86_64.tar.gz" -C '/tmp/previous release'
  '/tmp/previous release/re4mepc/AppRun' settings --set invert_y true
  '/tmp/previous release/re4mepc/AppRun' backup --game '/game inputs' > /evidence/previous-backup.json
fi
for format in portable appimage; do
  if [ "$format" = portable ]; then
    artifact='/tmp/portable release/re4mepc/AppRun'
  else
    artifact='/release files/re4mepc-linux-x86_64.AppImage'
  fi
  "$artifact" --help
  "$artifact" launcher --help
  if [ "$format" = portable ] && [ -z "${PREVIOUS_DIST:-}" ]; then
    "$artifact" settings --set invert_y true
  fi
  test -f '/tmp/user config/re4mepc/settings.json'
  xvfb-run -a -e "/evidence/$format-xvfb.log" "$artifact" launcher --smoke-test
  "$artifact" check --game '/game inputs'
  xvfb-run -a -e "/evidence/$format-engine-xvfb.log" "$artifact" run --game '/game inputs' --frames 160 --skip-videos --log-interval 0 --stats "/evidence/$format-stats.json"
  "$artifact" backup --game '/game inputs' > "/evidence/$format-backup.json"
  "$artifact" backups --game '/game inputs' > "/evidence/$format-backups.json"
  "$artifact" settings > "/evidence/$format-settings.json"
  if [ "$format" = portable ]; then
    runtime='/tmp/portable release/re4mepc'
  else
    (cd '/tmp/appimage runtime' && "$artifact" --appimage-extract > /evidence/appimage-extract.log)
    runtime='/tmp/appimage runtime/squashfs-root'
  fi
  xvfb-run -a env PYTHONHOME="$runtime/usr" PYTHONPATH="$runtime/usr/lib/re4mepc:$runtime/usr/lib/python3.10/site-packages" \
    PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 LD_LIBRARY_PATH="$runtime/usr/lib/runtime" \
    TCL_LIBRARY="$runtime/usr/share/tcltk/tcl8.6" TK_LIBRARY="$runtime/usr/share/tcltk/tk8.6" \
    FONTCONFIG_FILE="$runtime/usr/share/fontconfig/fonts.conf" PATH="$runtime/usr/bin:$PATH" \
    "$runtime/usr/bin/python3" /evidence/language-check.py "$runtime" "/evidence/$format-languages.json" "$CHECK_ENGINE_LANGUAGES"
  "$artifact" export-achievements --help
  "$artifact" export-backup --help
  "$artifact" backup --game '/capture inputs' > "/evidence/$format-capture-backup.json"
  "$artifact" export-achievements "/evidence/$format-gallery.zip" --achievement village --achievement gigante --game '/capture inputs' > "/evidence/$format-gallery.json"
  "$artifact" export-backup "$CAPTURE_SNAPSHOT" "/evidence/$format-bundle.zip" --include-media --game '/capture inputs'
  "$artifact" import-backup "/evidence/$format-bundle.zip" --game '/tmp/bundle destination'
  test ! -d '/tmp/bundle destination/saves' || cmp '/capture inputs/saves/slot' '/tmp/bundle destination/saves/slot'
  "$artifact" restore-backup "$CAPTURE_SNAPSHOT" --game '/tmp/bundle destination'
  cmp '/capture inputs/saves/slot' '/tmp/bundle destination/saves/slot'
  cmp '/capture inputs/saves/launcher-achievements.json' '/tmp/bundle destination/saves/launcher-achievements.json'
  cmp '/capture inputs/achievement-media/unlock-package.png' '/tmp/bundle destination/achievement-media/unlock-package.png'
  cmp '/capture inputs/achievement-media/unlock-package.mp4' '/tmp/bundle destination/achievement-media/unlock-package.mp4'
  "$artifact" export-backup "$CAPTURE_SNAPSHOT" "/evidence/$format-save-only.zip" --game '/capture inputs'
  "$artifact" import-backup "/evidence/$format-save-only.zip" --game '/tmp/save only destination'
  "$artifact" restore-backup "$CAPTURE_SNAPSHOT" --game '/tmp/save only destination'
  cmp '/capture inputs/saves/slot' '/tmp/save only destination/saves/slot'
  test ! -e '/tmp/save only destination/achievement-media'
  printf 'PACKAGE_FORMAT_PASS %s\n' "$format"
done
printf 'CLEAN_PACKAGE_SMOKE_PASS\n'
'''


def run(command, log):
    with log.open('wb') as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError('Package validation failed; inspect ' + str(log))


def capture_fixture(directory):
    """Only authored synthetic saves and media; never modify imported inputs."""
    from PIL import Image
    from re4pc.paths import ffmpeg_binary
    root = directory/'capture-inputs'
    media = root/'achievement-media'
    media.mkdir(parents=True)
    Image.new('RGB', (16, 16), 'red').save(media/'unlock-package.png')
    subprocess.run([ffmpeg_binary(), '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                    '-i', 'color=c=red:s=16x16:r=5', '-t', '0.4', '-an', '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', str(media/'unlock-package.mp4')], check=True, timeout=15)
    records = AchievementStore(root)
    records.update(Progress(story=(True,)*22))
    records.attach_media(('village', 'gigante'), {'image':'unlock-package.png', 'clip':'unlock-package.mp4'})
    (root/'saves/slot').write_bytes(b'authored synthetic portable save fixture\n')
    inventory = {p.name: {'bytes':p.stat().st_size, 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                 for p in sorted((root/'saves').iterdir())}
    return root, _digest(_canonical(inventory))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=Path(__file__).resolve().parents[1]/'dist')
    parser.add_argument('--game', type=Path, default=game_dir())
    parser.add_argument('--output', type=Path)
    parser.add_argument('--previous-dist', type=Path, help='Preceding frozen packages for upgrade persistence checks')
    parser.add_argument('--targets', nargs='+', choices=BASES, default=list(BASES))
    args = parser.parse_args()
    output = test_output('package-validation', args.output)
    artifacts = [args.dist/'re4mepc-linux-x86_64.AppImage', args.dist/'re4mepc-linux-x86_64.tar.gz']
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in artifacts}
    previous_hashes = ({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
        (args.previous_dist/'re4mepc-linux-x86_64.AppImage', args.previous_dist/'re4mepc-linux-x86_64.tar.gz')}
        if args.previous_dist else None)
    reports = []
    for target in args.targets:
        evidence = output/target
        evidence.mkdir(exist_ok=True)
        fixture = isolated_game(args.game, evidence)
        (evidence/'language-check.py').write_text(LANGUAGE_CHECK)
        captures, capture_identity = capture_fixture(evidence)
        image, install = BASES[target]
        tag = 're4mepc-validation:' + target
        with tempfile.TemporaryDirectory(prefix='re4-validate-') as temporary:
            context = Path(temporary)
            (context/'Dockerfile').write_text('FROM '+image+'\nRUN '+install+'\nRUN ! command -v python3 && ! command -v cc\n')
            run(['docker', 'build', '-t', tag, str(context)], evidence/'image-build.log')
        import os
        command = ['docker', 'run', '--rm', '--user', str(os.getuid())+':'+str(os.getgid()),
                   '-v', str(args.dist.resolve())+':/release files:ro',
                   '-v', str(fixture)+':/game inputs', '-v', str(evidence)+':/evidence',
                   '-v', str(captures)+':/capture inputs:ro', '-e', 'CAPTURE_SNAPSHOT='+capture_identity,
                   '-e', 'CHECK_ENGINE_LANGUAGES='+('yes' if target == 'ubuntu22' else 'no')]
        if args.previous_dist:
            command += ['-v',str(args.previous_dist.resolve())+':/preceding releases:ro', '-e','PREVIOUS_DIST=/preceding releases']
        command += [tag, '/bin/sh', '-c', SCRIPT]
        run(command, evidence/'launch.log')
        for form in ('portable', 'appimage'):
            stats = json.loads((evidence/(form+'-stats.json')).read_text())
            assert stats['frames']==160 and stats['draw_calls']>100
            assert not stats['gl_messages']
            settings = json.loads((evidence/(form+'-settings.json')).read_text())
            assert settings['invert_y'] is True
            assert json.loads((evidence/(form+'-backups.json')).read_text())
            languages = json.loads((evidence/(form+'-languages.json')).read_text())['languages']
            assert {item['language'] for item in languages} == {'en', 'es', 'fr', 'de', 'it', 'ja'}
            assert all(item['launcher'] and item['preferences_restored'] for item in languages)
            if target == 'ubuntu22':
                assert all(item['engine_ticks'] == 160 for item in languages)
            assert json.loads((evidence/(form+'-capture-backup.json')).read_text())['id'] == capture_identity
            gallery = json.loads((evidence/(form+'-gallery.json')).read_text())
            assert gallery['files'] == 2 and not gallery['missing_captures']
            with zipfile.ZipFile(evidence/(form+'-gallery.zip')) as archive:
                assert len(archive.infolist()) == 3
                metadata = json.loads(archive.read('achievements.json'))
                assert {r['id'] for r in metadata['achievements']} == {'village','gigante'}
                for name in ('unlock-package.png','unlock-package.mp4'):
                    assert archive.read('media/'+name) == (captures/'achievement-media'/name).read_bytes()
        first_snapshot = json.loads((evidence/'portable-backup.json').read_text())['id']
        assert any(item['id'] == first_snapshot for item in json.loads((evidence/'appimage-backups.json').read_text()))
        if args.previous_dist:
            previous = json.loads((evidence/'previous-backup.json').read_text())['id']
            assert any(item['id'] == previous for item in json.loads((evidence/'appimage-backups.json').read_text()))
        # Qualification belongs to immutable artifact bytes, not just a filename.
        assert hashes == {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in artifacts}, 'Artifacts changed during validation'
        if args.previous_dist:
            assert previous_hashes == {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                (args.previous_dist/'re4mepc-linux-x86_64.AppImage',args.previous_dist/'re4mepc-linux-x86_64.tar.gz')}, 'Preceding artifacts changed during upgrade validation'
        report = {'target': target, 'image_id': subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',tag], text=True).strip(),
                  'artifacts_sha256': hashes, 'previous_artifacts_sha256': previous_hashes,
                  'checks':'both GUI launchers in six languages + bundled Japanese glyph coverage + engine160 ticks + shared saves/settings + gallery exports + save/media bundle and legacy roundtrips; no Python/compiler; paths with spaces',
                  'engine_languages_checked': target == 'ubuntu22',
                  'qualification_scope':'automated smoke; full campaign and physical-device gates remain separate'}
        reports.append(report)
        (output/'results.json').write_text(json.dumps(reports, indent=2)+'\n')
        print('TARGET_PACKAGE_PASS',target,flush=True)
    print('PACKAGE_VALIDATION_PASS',output/'results.json',flush=True)


if __name__ == '__main__':
    main()
