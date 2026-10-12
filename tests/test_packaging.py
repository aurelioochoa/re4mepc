import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from re4pc.packaging import audit_stage, write_manifest, verify_manifest


class PackagingTests(unittest.TestCase):
    def test_application_staging_includes_generated_artwork_and_only_allowlisted_assets(self):
        from tools.package import ROOT, copy_application
        from re4pc.packaging import APPLICATION_ASSETS
        from PIL import Image
        with tempfile.TemporaryDirectory() as temporary:
            application = Path(temporary) / 'application'
            copy_application(ROOT, application)
            assets = application / 're4pc/ui_assets'
            self.assertEqual({path.name for path in assets.iterdir()}, set(APPLICATION_ASSETS))
            for name in APPLICATION_ASSETS:
                self.assertEqual((assets / name).read_bytes(), (ROOT / 're4pc/ui_assets' / name).read_bytes())
                with Image.open(assets / name) as image:
                    image.verify()

    def test_library_collection_keeps_graphics_support_on_host(self):
        from tools.package import collect_libraries
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            stage=root/'stage'; stage.mkdir()
            (stage/'app').write_bytes(b'\x7fELFsynthetic')
            dependencies=[]
            for name in ('libdrm.so.2','libgbm.so.1','libSDL2-2.0.so.0'):
                path=root/name;path.write_bytes(b'\x7fELFsynthetic')
                dependencies.append(f'{name} => {path} (0x0)')
            with patch('tools.package.subprocess.run', return_value=Mock(stdout='\n'.join(dependencies))):
                self.assertEqual(collect_libraries(stage),['libSDL2-2.0.so.0'])
            self.assertFalse((stage/'usr/lib/runtime/libdrm.so.2').exists())
            self.assertFalse((stage/'usr/lib/runtime/libgbm.so.1').exists())

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.stage = Path(temporary.name)
        for name in ('AppRun', 're4mepc.desktop', 'usr/bin/python3', 'usr/bin/ffmpeg',
                     'usr/lib/re4mepc/re4pc/__main__.py', 'usr/lib/re4mepc/build/libre4audio.so',
                     'usr/lib/re4mepc/build/libre4fast.so'):
            path = self.stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic')

    def test_content_manifest_hashes_every_member(self):
        records = write_manifest(self.stage)
        self.assertEqual(len(records), 7)
        self.assertEqual(len(records['AppRun']['sha256']), 64)
        self.assertEqual(write_manifest(self.stage), records)

    def test_game_payload_and_escaping_links_rejected(self):
        for name in ('game/libbio4af.so', 'usr/lib/libbio4af.so', 'cache/audio.f32', 'usr/assets.h2z'):
            path = self.stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'forbidden')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'release|Imported'):
                audit_stage(self.stage)
            path.unlink()
            if name.startswith(('game/', 'cache/')):
                path.parent.rmdir()
        (self.stage / 'escape').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'escapes'):
            audit_stage(self.stage)

    def test_missing_runtime_fails(self):
        (self.stage / 'usr/bin/ffmpeg').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing release runtime'):
            audit_stage(self.stage)

    def test_game_hash_detection_is_independent_of_filename(self):
        from re4pc.packaging import FORBIDDEN_DIGESTS
        digest = Mock()
        digest.hexdigest.return_value = next(iter(FORBIDDEN_DIGESTS))
        with patch('re4pc.packaging.hashlib.sha256', return_value=digest):
            with self.assertRaisesRegex(ValueError, 'Imported engine bytes'):
                audit_stage(self.stage)

    def test_forbidden_symlink_name_is_rejected_before_link_resolution(self):
        (self.stage / 'libbio4af.so').symlink_to('AppRun')
        with self.assertRaisesRegex(ValueError, 'Imported game content'):
            audit_stage(self.stage)

    def test_manifest_detects_changed_and_unlisted_contents(self):
        write_manifest(self.stage)
        self.assertEqual(len(verify_manifest(self.stage)), 7)
        (self.stage / 'AppRun').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'manifest mismatch'):
            verify_manifest(self.stage)
        write_manifest(self.stage)
        (self.stage / 'unexpected').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'manifest mismatch'):
            verify_manifest(self.stage)


class AchievementArtworkPackageTests(unittest.TestCase):
    def test_catalog_icons_are_distinct_transparent_and_explicitly_packaged(self):
        import hashlib
        from tools.package import ROOT
        from PIL import Image
        from re4pc.achievements import ACHIEVEMENTS
        from re4pc.packaging import APPLICATION_ASSETS
        from tools.audit_source import DOCUMENTATION_IMAGES
        names = {'achievement-' + item.id + '.png' for item in ACHIEVEMENTS}
        self.assertEqual(names, {name for name in APPLICATION_ASSETS if name.startswith('achievement-')})
        self.assertEqual(len(names), 21)
        hashes = set()
        for name in names:
            path = ROOT / 're4pc/ui_assets' / name
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            hashes.add(digest)
            self.assertEqual(DOCUMENTATION_IMAGES['re4pc/ui_assets/' + name], digest)
            with Image.open(path) as image:
                self.assertEqual(image.format, 'PNG')
                self.assertEqual(image.mode, 'RGBA')
                alpha = image.getchannel('A')
                self.assertEqual(alpha.getextrema(), (0, 255))
                # Generated alpha may retain imperceptible 1/255 edge noise.
                # Require substantial fully clear coverage and near-clear corners;
                # opaque backgrounds (including checkerboards) fail both checks.
                self.assertGreater(alpha.histogram()[0] / (image.width * image.height), .2)
                for corner in ((0, 0), (image.width - 1, 0), (0, image.height - 1),
                               (image.width - 1, image.height - 1)):
                    self.assertLessEqual(alpha.getpixel(corner), 2)
                self.assertIsNotNone(alpha.getbbox())
        self.assertEqual(len(hashes), len(names))
        self.assertIn('paper.png', APPLICATION_ASSETS)
        with Image.open(ROOT / 're4pc/ui_assets/paper.png') as image:
            self.assertGreaterEqual(min(image.size), 512)


class FinalDialogAssetTests(unittest.TestCase):
    def test_generated_dialog_assets_and_renderer_are_explicitly_packaged(self):
        import hashlib
        from PIL import Image
        from tools.package import ROOT
        from tools.audit_source import DOCUMENTATION_IMAGES
        from re4pc.packaging import APPLICATION_ASSETS, APPLICATION_MODULES
        self.assertIn('case_dialog.py', APPLICATION_MODULES)
        for name in ('case-seal.png', 'ribbon-spools.png', 'paperclip.png', 'case-paper-v2.png'):
            self.assertIn(name, APPLICATION_ASSETS)
            path = ROOT / 're4pc/ui_assets' / name
            self.assertEqual(DOCUMENTATION_IMAGES['re4pc/ui_assets/' + name], hashlib.sha256(path.read_bytes()).hexdigest())
            with Image.open(path) as image:
                self.assertGreaterEqual(min(image.size), 512)
                if name != 'case-paper-v2.png':
                    self.assertEqual(image.mode, 'RGBA')
                    alpha = image.getchannel('A')
                    self.assertEqual(alpha.getextrema()[0], 0)
                    self.assertGreater(alpha.getextrema()[1], 240)
                    self.assertGreater(alpha.histogram()[0]/(image.width*image.height), .2)
