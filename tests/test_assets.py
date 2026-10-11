import json
import hashlib
import os
from unittest.mock import patch
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from re4pc.assets import import_apk, LIBRARIES, REQUIRED, validate


def synthetic_elf():
    elf=bytearray(52);elf[:7]=b'\x7fELF\x01\x01\x01';struct.pack_into('<H',elf,18,40)
    return bytes(elf)


def fixture(path, unsafe=False, missing=False):
    elf=synthetic_elf()
    with zipfile.ZipFile(path,'w') as z:
        for library in LIBRARIES: z.writestr('lib/armeabi/'+library,elf)
        manifest=[]
        for i,name in enumerate(REQUIRED):
            if missing and i==0: continue
            asset=f'bundle_file_{i:03}.bin'
            manifest.append({'assetName':asset,'path':'/storage/emulated/0/Android/data/game/files/data/monhun/'+name+'.png'})
            z.writestr('assets/'+asset,b'synthetic asset '+name.encode())
        if unsafe: manifest[0]['path']='/data/../../escape'
        z.writestr('assets/bundle_file_list.json',json.dumps(manifest))

class AssetTests(unittest.TestCase):
    def setUp(self):
        # Production has no bypass: tests substitute hashes only in-process.
        compatible={name:hashlib.sha256(synthetic_elf()).hexdigest() for name in LIBRARIES}
        self.hashes=patch('re4pc.assets.COMPATIBLE_LIBRARIES',compatible)
        self.hashes.start()
        self.addCleanup(self.hashes.stop)

    def test_manifest_restores_original_names_and_complete_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);apk=root/'input.apk';fixture(apk)
            result=import_apk(apk,root/'game')
            self.assertEqual(validate(result),result)
            for name in REQUIRED:
                self.assertEqual((result/'data/monhun'/name).read_bytes(),b'synthetic asset '+name.encode())
            manifest=json.loads((result/'import.json').read_text())
            self.assertEqual(len(manifest['files']),len(REQUIRED)+len(LIBRARIES))
            self.assertTrue((result/'saves').is_dir())

    def test_traversal_rejected_without_partial_install(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);apk=root/'input.apk';fixture(apk,unsafe=True)
            with self.assertRaisesRegex(ValueError,'Unsafe'): import_apk(apk,root/'game')
            self.assertFalse((root/'game').exists())
            self.assertFalse((root/'escape').exists())

    def test_missing_required_asset_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);apk=root/'input.apk';fixture(apk,missing=True)
            with self.assertRaisesRegex(ValueError,'Missing'): import_apk(apk,root/'game')
            self.assertFalse((root/'game').exists())

    def test_existing_game_data_and_saves_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);apk=root/'input.apk';fixture(apk)
            game=root/'game';game.mkdir();save=game/'save.dat';save.write_bytes(b'keep save')
            with self.assertRaisesRegex(ValueError,'already exists'): import_apk(apk,game)
            self.assertEqual(save.read_bytes(),b'keep save')

    def test_incompatible_library_rejected_before_asset_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);apk=root/'input.apk';fixture(apk)
            with patch('re4pc.assets.COMPATIBLE_LIBRARIES',{name:'0'*64 for name in LIBRARIES}):
                with self.assertRaisesRegex(ValueError,'Incompatible'):
                    import_apk(apk,root/'game')
            self.assertFalse((root/'game').exists())
            self.assertFalse(list(root.glob('.re4-import-*')))

    def test_repackaged_apk_with_same_libraries_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);apk=root/'input.apk';fixture(apk)
            before=hashlib.sha256(apk.read_bytes()).hexdigest()
            with zipfile.ZipFile(apk,'a') as archive:
                archive.writestr('META-INF/synthetic.txt','synthetic packaging change')
            self.assertNotEqual(before,hashlib.sha256(apk.read_bytes()).hexdigest())
            validate(import_apk(apk,root/'game'))

    def test_missing_library_and_malformed_archive_are_clear_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);apk=root/'input.apk'
            with zipfile.ZipFile(apk,'w') as archive: archive.writestr('assets/fake','synthetic')
            with self.assertRaisesRegex(ValueError,'Missing ARM32'): import_apk(apk,root/'game')
            apk.write_bytes(b'not a zip')
            with self.assertRaisesRegex(ValueError,'Invalid or incomplete APK'): import_apk(apk,root/'game')
            self.assertFalse((root/'game').exists())

    def test_missing_import_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'import your APK'): validate(Path(directory)/'absent')

    def test_broken_destination_symlink_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);apk=root/'input.apk';fixture(apk)
            destination=root/'game';destination.symlink_to(root/'missing')
            with self.assertRaisesRegex(ValueError,'already exists'): import_apk(apk,destination)
            self.assertTrue(destination.is_symlink())

    def test_destination_created_during_import_is_not_overwritten(self):
        from re4pc.filesystem import rename_new
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);apk=root/'input.apk';fixture(apk)
            destination=root/'game'
            def raced(source,target):
                destination.mkdir()
                return rename_new(source,target)
            with patch('re4pc.assets.rename_new',side_effect=raced):
                with self.assertRaisesRegex(ValueError,'already exists'): import_apk(apk,destination)
            self.assertEqual(list(destination.iterdir()),[])

    def test_unsafe_manifest_forms_are_rejected(self):
        from re4pc.assets import manifest_target
        for entry in [
            {'assetName':'../escape','path':'/data/monhun/name'},
            {'assetName':'a\\b','path':'/data/monhun/name'},
            {'assetName':'ok','path':'/data/../../escape'},
            {'assetName':'ok','path':'/data'},
            {'assetName':'ok','path':'/saves/name'},
            {'assetName':'ok','path':'/data/monhun/.png'},
            {'assetName':'ok','path':'/data/monhun/name\\escape'},
        ]:
            with self.subTest(entry=entry):
                with self.assertRaisesRegex(ValueError,'Unsafe'): manifest_target(entry)

    def test_duplicate_destination_and_missing_manifest_member(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);apk=root/'input.apk'
            for manifest in [
                [{'assetName':'ok','path':'/data/monhun/a'}]*2,
                [{'assetName':'missing','path':'/data/monhun/a'}],
            ]:
                with zipfile.ZipFile(apk,'w') as archive:
                    for library in LIBRARIES: archive.writestr('lib/armeabi/'+library,synthetic_elf())
                    archive.writestr('assets/ok',b'synthetic')
                    archive.writestr('assets/bundle_file_list.json',json.dumps(manifest))
                with self.assertRaisesRegex(ValueError,'Duplicate|Missing'): import_apk(apk,root/'game')
                self.assertFalse((root/'game').exists())

    def test_modified_import_is_rejected_before_runtime_allocation(self):
        from re4pc.game import Game
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);apk=root/'input.apk';fixture(apk)
            game=import_apk(apk,root/'game')
            (game/'lib'/LIBRARIES[0]).write_bytes(synthetic_elf()+b'changed')
            with patch('re4pc.game.ArmRuntime') as runtime:
                with self.assertRaisesRegex(ValueError,'Incompatible'): Game(game)
                runtime.assert_not_called()

    def test_other_bundled_data_directories_are_restored(self):
        from re4pc.assets import manifest_target
        self.assertEqual(manifest_target({'assetName':'logo','path':'/Android/data/app/files/data/bmptest/synthetic.bmp.png'}),
                         ('assets/logo','data/bmptest/synthetic.bmp'))
        self.assertEqual(manifest_target({'assetName':'readme','path':'/Android/data/app/files/data/readme.txt.png'}),
                         ('assets/readme','data/readme.txt'))

    def test_direct_assets_and_armeabi_v7a_are_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);apk=root/'input.apk'
            with zipfile.ZipFile(apk,'w') as archive:
                for library in LIBRARIES: archive.writestr('lib/armeabi-v7a/'+library,synthetic_elf())
                for name in REQUIRED: archive.writestr('assets/'+name+'.png',b'synthetic resource')
            validate(import_apk(apk,root/'game'))

    def test_non_arm_library_header_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);apk=root/'input.apk'
            with zipfile.ZipFile(apk,'w') as archive:
                for library in LIBRARIES: archive.writestr('lib/armeabi/'+library,b'not an ELF library')
            with self.assertRaisesRegex(ValueError,'ARM32 ELF'): import_apk(apk,root/'game')
            self.assertFalse((root/'game').exists())
