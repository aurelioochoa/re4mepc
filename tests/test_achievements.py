import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from dataclasses import replace

from re4pc.achievements import (ACHIEVEMENTS, IDS, AchievementStore,
                               AchievementTracker, Progress, LOAD_SYMBOL)
from re4pc.arm import ArmRuntime
from re4pc.backups import SaveStore
from re4pc.save_boundary import SaveBoundary, SAVE_SYMBOL


def progress(ranks=None, story=None, mercenary=None):
    return Progress(tuple(tuple(row) for row in (ranks or [[-1] * 5 for _ in range(22)])),
                    tuple(story or [False] * 22), tuple(mercenary or [False] * 44))


def native_data(records):
    data = bytearray(0x1a1)
    # Keep training separate from the 22 story and 44 Mercenary missions.
    data[0xd6:0xdb] = b'\x04' * 5
    data[0x7c] = data[0x174] = 1
    for mission, row in enumerate(records.ranks, 1):
        struct.pack_into('5b', data, 0xd6 + mission * 5, *row)
    data[0x7d:0x7d + 22] = bytes(records.story)
    data[0x175:0x175 + 44] = bytes(records.mercenary)
    return bytes(data)


class AchievementTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = AchievementStore(self.root)
        self.items = {item.id: item for item in ACHIEVEMENTS}

    def earned(self, records):
        unlocked = set()
        for item in ACHIEVEMENTS:
            if item.progress(records, unlocked)[0] == item.target:
                unlocked.add(item.id)
        return unlocked

    def test_empty_progress_training_and_unplayed_ranks_unlock_nothing(self):
        self.assertEqual(self.earned(Progress()), set())
        arm = ArmRuntime()
        self.addCleanup(arm.close)
        user = arm.alloc(0x1a1)
        arm.write(user, native_data(Progress()))
        self.assertEqual(Progress.from_native(arm, user), Progress())
        self.assertEqual(self.store.load(), (Progress(), {}))

    def test_classic_boss_achievements_follow_correct_mobile_missions(self):
        for identifier, mission in [('village', 1), ('gigante', 4), ('ashley', 5),
                                    ('verdugo', 12), ('salazar', 14), ('krauser', 20), ('saddler', 22)]:
            flags = [False] * 22
            flags[mission - 1] = True
            with self.subTest(identifier=identifier):
                self.assertEqual(self.earned(progress(story=flags)), {identifier})
        ranks = [[-1] * 5 for _ in range(22)]
        ranks[0][1] = 0
        self.assertEqual(self.earned(progress(ranks)), {'village'})

    def test_campaign_requires_one_difficulty_and_extreme_is_highest(self):
        ranks = [[-1] * 5 for _ in range(22)]
        for i, row in enumerate(ranks):
            row[i % 5] = 0
        self.assertNotIn('campaign', self.earned(progress(ranks)))
        for row in ranks:
            row[2] = 0
        self.assertIn('campaign', self.earned(progress(ranks)))
        self.assertNotIn('extreme', self.earned(progress(ranks)))
        for row in ranks:
            row[4] = 0
        self.assertIn('extreme', self.earned(progress(ranks)))

    def test_original_all_s_checks_require_every_mission_and_difficulty(self):
        ranks = [[-1] * 5 for _ in range(22)]
        ranks[0][0] = 4
        self.assertIn('first_s', self.earned(progress(ranks)))
        self.assertNotIn('all_s', self.earned(progress(ranks)))
        for row in ranks:
            row[0] = 4
        self.assertIn('all_s', self.earned(progress(ranks)))
        self.assertNotIn('strongest', self.earned(progress(ranks)))
        all_ranks = [[4] * 5 for _ in range(22)]
        self.assertIn('strongest', self.earned(progress(all_ranks)))
        all_ranks[-1][-1] = 3
        self.assertNotIn('strongest', self.earned(progress(all_ranks)))
        self.assertEqual(self.items['strongest'].progress(progress(all_ranks)), (109, 110))

    def test_mercenary_flags_not_scores_or_paid_content_define_completion(self):
        flags = [False] * 44
        flags[0] = True
        self.assertEqual(self.earned(progress(mercenary=flags)), {'mercenary'})
        flags[:] = [True] * 44
        self.assertEqual(self.earned(progress(mercenary=flags)), {'mercenary', 'mercenary_master'})
        complete = progress([[4] * 5 for _ in range(22)], [True] * 22, flags)
        self.assertEqual(self.earned(complete), {item.id for item in ACHIEVEMENTS
                                               if item.kind not in ('purchase', 'upgrade', 'platinum')})
        self.assertEqual(len(IDS), len(ACHIEVEMENTS))

    def test_weapon_goals_and_platinum_require_every_other_achievement(self):
        records = replace(Progress(), purchased_weapons=(0, 1, 2), upgrades=5)
        self.assertEqual(self.earned(records), {'first_purchase', 'collector', 'first_upgrade', 'tuned'})
        complete = replace(progress([[4] * 5 for _ in range(22)], [True] * 22, [True] * 44),
                           purchased_weapons=(0, 1, 2, 3, 4), upgrades=10)
        self.assertEqual(self.earned(complete), IDS)
        self.assertEqual(set(self.store.update(complete)), IDS)
        self.assertEqual(self.store.update(complete), [])
        self.assertEqual(self.items['platinum'].progress(complete, IDS - {'expert'}), (19, 20))

    def test_original_record_version_remains_compatible_and_media_survives_updates(self):
        self.store.update(progress(story=[True] * 22))
        record = json.loads(self.store.path.read_text())
        record.pop('media')
        record['progress'].pop('purchased_weapons')
        record['progress'].pop('upgrades')
        self.store.path.write_text(json.dumps(record))
        records, earned = self.store.load()
        self.assertEqual((records.purchased_weapons, records.upgrades), ((), 0))
        self.store.attach_media(['village'], {'image': 'unlock-123-aabbccdd.png'})
        self.store.update(Progress())
        self.store.load()
        self.assertEqual(self.store.media['village'], {'image': 'unlock-123-aabbccdd.png'})
        record = json.loads(self.store.path.read_text())
        record['media']['village']['image'] = '../unlock-123.png'
        self.store.path.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            self.store.load()

    def test_storage_keeps_unlock_dates_when_progress_is_reset_and_is_installation_specific(self):
        ranks = [[-1] * 5 for _ in range(22)]
        ranks[0][1] = 4
        with patch('re4pc.achievements.time.time_ns', return_value=123456):
            self.assertEqual(set(self.store.update(progress(ranks))), {'village', 'first_s'})
        self.assertEqual(self.store.update(progress(ranks)), [])
        self.store.update(Progress())
        self.assertEqual(self.store.load()[1], {'village': 123456, 'first_s': 123456})
        self.assertEqual(AchievementStore(self.root / 'other').load()[1], {})

    def test_bad_records_are_preserved_and_failed_atomic_write_keeps_previous(self):
        self.store.update(Progress())
        before = self.store.path.read_bytes()
        with patch('re4pc.achievements.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.update(progress(story=[True] * 22))
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(list(self.store.path.parent.glob('.achievements-*')), [])
        for malformed in [b'broken', b'[]', b'{"version":2}', b'x' * 65537]:
            self.store.path.write_bytes(malformed)
            with self.assertRaises(ValueError):
                self.store.update(Progress())
            self.assertEqual(self.store.path.read_bytes(), malformed)
        record = json.loads(before)
        record['progress']['ranks'][0][0] = True
        self.store.path.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            self.store.load()
        for invalid in ({'village': 2 ** 100}, {'village': -1}, {'unknown': 1}, {'village': True}):
            record = json.loads(before)
            record['unlocked'] = invalid
            self.store.path.write_text(json.dumps(record))
            with self.assertRaises(ValueError):
                self.store.load()


class NativeAchievementTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.arm = ArmRuntime()
        self.addCleanup(self.arm.close)
        self.user = self.arm.alloc(0x1a1)
        self.arm.write(self.user, native_data(Progress()))
        for symbol, offset in [(LOAD_SYMBOL, 0x4000), (SAVE_SYMBOL, 0x5000)]:
            address = self.arm.base + offset
            # Synthetic Thumb: push lr; mov r0,1; pop pc.
            self.arm.write(address, b'\x00\xb5\x01\x20\x00\xbd')
            self.arm.symbols[symbol] = address | 1
            self.arm.symbol_sizes[symbol] = 6
        self.tracker = AchievementTracker(self.arm, self.root)

    def test_successful_native_load_recovers_existing_progress_without_a_new_save(self):
        ranks = [[-1] * 5 for _ in range(22)]
        ranks[0][0] = 4
        self.arm.write(self.user, native_data(progress(ranks)))
        self.assertEqual(self.arm.call(LOAD_SYMBOL, self.user, 63), 1)
        self.assertEqual(set(self.tracker.store.load()[1]), {'village', 'first_s'})

    def test_failed_load_and_option_only_load_do_not_record_progress(self):
        self.arm.write(self.user, native_data(progress(story=[True] * 22)))
        for sections in (8, 0x10):
            self.arm.call(LOAD_SYMBOL, self.user, sections)
        self.assertFalse(self.tracker.store.path.exists())
        address = self.arm.symbols[LOAD_SYMBOL] & ~1
        self.arm.write(address + 2, b'\x00\x20')
        self.arm.uc.ctl_remove_cache(address, address + 6)
        self.assertEqual(self.arm.call(LOAD_SYMBOL, self.user, 63), 0)
        self.assertFalse(self.tracker.store.path.exists())

    def test_save_backup_contains_achievements_and_failed_save_does_not_unlock(self):
        with SaveStore(self.root, state_dir=self.root / 'state') as store:
            boundary = SaveBoundary(self.arm, store, self.tracker.capture)
            self.arm.write(self.user, native_data(progress(story=[True] * 22)))
            self.assertEqual(self.arm.call(SAVE_SYMBOL, self.user, 63), 1)
            manifest = next(item for item in store.list_snapshots() if item['label'] == 'saved')
            self.assertIn('launcher-achievements.json', manifest['files'])
            saved = self.tracker.store.path.read_bytes()
            store.restore(manifest['id'])
            self.assertEqual(self.tracker.store.path.read_bytes(), saved)
            address = self.arm.symbols[SAVE_SYMBOL] & ~1
            self.arm.write(address + 2, b'\x00\x20')
            self.arm.uc.ctl_remove_cache(address, address + 6)
            self.arm.write(self.user, native_data(progress([[4] * 5 for _ in range(22)])))
            self.assertEqual(self.arm.call(SAVE_SYMBOL, self.user, 63), 0)
            self.assertEqual(self.tracker.store.path.read_bytes(), saved)
            self.assertEqual((boundary.completed, boundary.failed), (1, 1))

    def test_optional_achievement_disk_failure_does_not_stop_native_save(self):
        with SaveStore(self.root, state_dir=self.root / 'state') as store:
            boundary = SaveBoundary(self.arm, store, self.tracker.capture)
            with patch.object(self.tracker.store, 'update', side_effect=OSError('disk full')):
                self.assertEqual(self.arm.call(SAVE_SYMBOL, self.user, 63), 1)
            self.assertEqual((boundary.completed, boundary.failed), (1, 0))

    def test_coin_shoot_only_save_does_not_award_unsaved_story_progress(self):
        with SaveStore(self.root, state_dir=self.root / 'state') as store:
            SaveBoundary(self.arm, store, self.tracker.capture)
            self.arm.write(self.user, native_data(progress(story=[True] * 22)))
            self.assertEqual(self.arm.call(SAVE_SYMBOL, self.user, 0x10), 1)
            self.assertFalse(self.tracker.store.path.exists())

    def test_weapon_receipts_are_committed_on_save_and_load_discards_pending(self):
        from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_LR
        node, parameter = self.arm.alloc(64), self.arm.alloc(64)
        self.arm.w32(node + 8, parameter)
        self.arm.write(parameter + 0xc, b'\x00\x03')
        self.tracker._purchase(Mock(reg_read=lambda register: node), 0, 0, None)
        self.assertFalse(self.tracker.store.path.exists())
        self.tracker.upgrade_return = 0x1234
        self.arm.write(node + 14, struct.pack('<h', 0))
        registers = {UC_ARM_REG_R0:node, UC_ARM_REG_R1:0, UC_ARM_REG_R2:1, UC_ARM_REG_LR:0x1235}
        self.tracker._upgrade(Mock(reg_read=lambda register:registers[register]), 0, 0, None)
        self.tracker.capture(self.user, 0x20)
        records, earned = self.tracker.store.load()
        self.assertEqual((records.purchased_weapons, records.upgrades), ((3,), 1))
        self.assertEqual(set(earned), {'first_purchase', 'first_upgrade'})
        self.assertEqual(set(self.tracker.new_unlocks), set(earned))
        self.tracker.pending_weapons.add(5)
        self.tracker.pending_upgrades += 1
        self.arm.call(LOAD_SYMBOL, self.user, 63)
        self.assertEqual(self.tracker.store.load()[0], records)
        self.assertEqual(self.tracker.pending_upgrades, 0)

    def test_ammo_null_registration_and_non_merchant_level_changes_do_not_count(self):
        from unicorn.arm_const import UC_ARM_REG_LR
        node, parameter = self.arm.alloc(64), self.arm.alloc(64)
        self.arm.w32(node + 8, parameter)
        self.arm.write(parameter + 0xc, b'\x01\x03')
        self.tracker._purchase(Mock(reg_read=lambda register:0), 0, 0, None)
        self.tracker._purchase(Mock(reg_read=lambda register:node), 0, 0, None)
        self.tracker.upgrade_return = 0x1234
        self.tracker._upgrade(Mock(reg_read=lambda register:0x5678 if register == UC_ARM_REG_LR else node),0,0,None)
        self.assertEqual((self.tracker.pending_weapons, self.tracker.pending_upgrades), (set(), 0))
