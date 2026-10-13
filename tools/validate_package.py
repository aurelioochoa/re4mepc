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
                   '-v', str(captures)+':/capture inputs:ro', '-e', 'CAPTURE_SNAPSHOT='+capture_identity]
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
                  'checks':'both GUI launchers + engine160 ticks + shared saves/settings + gallery exports + save/media bundle and legacy roundtrips; no Python/compiler; paths with spaces',
                  'qualification_scope':'automated smoke; full campaign and physical-device gates remain separate'}
        reports.append(report)
        (output/'results.json').write_text(json.dumps(reports, indent=2)+'\n')
        print('TARGET_PACKAGE_PASS',target,flush=True)
    print('PACKAGE_VALIDATION_PASS',output/'results.json',flush=True)


if __name__ == '__main__':
    main()
