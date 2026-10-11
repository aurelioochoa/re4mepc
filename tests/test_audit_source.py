"""Negative controls in disposable Git repositories; never stage real data."""
import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from tools.audit_source import audit, AuditError


class SourceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.git('init','-b','main')
        self.git('config','user.name','Synthetic Test')
        self.git('config','user.email','synthetic@example.invalid')
        self.write('README.md',b'Synthetic source documentation\n')
        self.git('add','README.md')

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.root),*args],stderr=subprocess.PIPE)

    def write(self,name,data):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)

    def test_source_only_index_and_history_pass(self):
        self.write('native/audio.c',b'/* synthetic source */\n')
        self.git('add','native/audio.c');self.git('commit','-m','Synthetic sources')
        with contextlib.redirect_stdout(io.StringIO()) as output: audit(self.root)
        self.assertIn('SOURCE_AUDIT_PASS',output.getvalue())

    def test_forced_ignored_packages_assets_saves_and_captures_are_rejected(self):
        for name in ('game/lib/engine.so','input.apk','logs/capture.png','game/saves/save.dat','assets/resource.h2z'):
            with self.subTest(name=name):
                self.write('.gitignore',b'game/\nlogs/\nassets/\n*.apk\n')
                self.git('add','.gitignore');self.write(name,b'synthetic prohibited data')
                self.git('add','-f',name)
                with self.assertRaisesRegex(AuditError,'Forbidden publication path'): audit(self.root)
                self.git('rm','--cached','--',name)

    def test_forbidden_path_only_in_previous_commit_is_rejected(self):
        self.write('game/save.dat',b'synthetic save');self.git('add','-f','game/save.dat')
        self.git('commit','-m','Synthetic forbidden history')
        self.git('rm','game/save.dat');self.git('commit','-m','Remove from tip')
        with self.assertRaisesRegex(AuditError,'Forbidden publication path'): audit(self.root)

    def test_binary_renamed_as_source_is_rejected_in_index(self):
        self.write('README.md',b'synthetic\0binary')
        self.git('add','README.md')
        with self.assertRaisesRegex(AuditError,'Binary'): audit(self.root)

    def test_binary_only_in_historical_blob_is_rejected(self):
        self.write('README.md',b'\x7fELF\0synthetic')
        self.git('add','README.md');self.git('commit','-m','Synthetic binary history')
        self.write('README.md',b'Clean synthetic docs\n')
        self.git('add','README.md');self.git('commit','-m','Clean tip')
        with self.assertRaisesRegex(AuditError,'Binary'): audit(self.root)

    def test_dangling_binary_blob_is_rejected(self):
        path=self.root/'untracked';path.write_bytes(b'synthetic\0blob')
        self.git('hash-object','-w',str(path))
        with self.assertRaisesRegex(AuditError,'Binary'): audit(self.root)

    def test_symlink_even_with_allowed_source_name_is_rejected(self):
        path=self.root/'setup.sh';path.symlink_to('/tmp/synthetic')
        self.git('add','setup.sh')
        with self.assertRaisesRegex(AuditError,'symlink'): audit(self.root)

    def test_historical_symlink_is_rejected(self):
        path=self.root/'setup.sh';path.symlink_to('/tmp/synthetic')
        self.git('add','setup.sh');self.git('commit','-m','Synthetic symlink')
        self.git('rm','setup.sh');self.git('commit','-m','Remove symlink')
        with self.assertRaisesRegex(AuditError,'symlink'): audit(self.root)

    def test_encoded_payloads_are_rejected(self):
        for payload in (b'ab'*100,b'A'*300,b'\\x01'*40,b'00012345: abcd abcd decoded_instruction\n'):
            with self.subTest(payload=payload[:16]):
                self.write('README.md',payload);self.git('add','README.md')
                with self.assertRaisesRegex(AuditError,'Encoded'): audit(self.root)

    def test_empty_index_is_rejected(self):
        self.git('rm','--cached','README.md')
        with self.assertRaisesRegex(AuditError,'No staged'): audit(self.root)
