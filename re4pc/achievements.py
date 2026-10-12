"""Local achievements derived from the supported mobile engine's saved records.

The native hashes are checked before hooks are installed. These offsets were
audited against Bio4_UserData getters; no proprietary code or assets are copied.
"""
import json
import os
import struct
import tempfile
import time
import threading
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path

FILENAME = 'launcher-achievements.json'
LOAD_SYMBOL = '_ZN13Bio4_UserData4LoadEl'
STORY_MISSIONS = 22
MERCENARY_MISSIONS = 44
DIFFICULTIES = ('Beginner', 'Normal', 'Professional', 'Hell', 'Extreme')
MAX_RECORD_BYTES = 64 * 1024
BUY_SYMBOL = '_ZN23Bio4_CTTask_ShopBuyConf13_Set_BuyParamEv'
UPGRADE_SYMBOL = '_ZN27Bio4_CTTask_ShopCustSelConf14_Set_CustParamEv'
SET_LEVEL_SYMBOL = '_ZN15Bio4_WeaponNode8SetLevelEls'


@dataclass(frozen=True)
class Progress:
    ranks: tuple = ((-1,) * 5,) * STORY_MISSIONS
    story: tuple = (False,) * STORY_MISSIONS
    mercenary: tuple = (False,) * MERCENARY_MISSIONS
    purchased_weapons: tuple = ()
    upgrades: int = 0

    def as_dict(self):
        return {'ranks': [list(row) for row in self.ranks],
                'story': list(self.story), 'mercenary': list(self.mercenary),
                'purchased_weapons': list(self.purchased_weapons), 'upgrades': self.upgrades}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError('Invalid achievement progress')
        ranks, story, mercenary = (value.get(key) for key in ('ranks', 'story', 'mercenary'))
        if (not isinstance(ranks, list) or len(ranks) != STORY_MISSIONS
                or any(not isinstance(row, list) or len(row) != 5
                       or any(type(rank) is not int or not -1 <= rank <= 4 for rank in row)
                       for row in ranks)
                or not isinstance(story, list) or len(story) != STORY_MISSIONS
                or not isinstance(mercenary, list) or len(mercenary) != MERCENARY_MISSIONS
                or any(type(flag) is not bool for flag in story + mercenary)):
            raise ValueError('Invalid achievement progress')
        weapons, upgrades = value.get('purchased_weapons', []), value.get('upgrades', 0)
        if (not isinstance(weapons, list) or len(weapons) > 256
                or any(type(weapon) is not int or not 0 <= weapon <= 255 for weapon in weapons)
                or len(set(weapons)) != len(weapons)
                or type(upgrades) is not int or not 0 <= upgrades <= 1000000):
            raise ValueError('Invalid weapon achievement progress')
        return cls(tuple(tuple(row) for row in ranks), tuple(story), tuple(mercenary),
                   tuple(sorted(weapons)), upgrades)

    @classmethod
    def from_native(cls, arm, user):
        # GetRank(mission, difficulty): user + 0xd6 + mission*5 + difficulty.
        # GetMissionClearFlag(mode, mission): 0x7c (story), 0x174 (mercenary).
        # Mission zero is training and never counts toward campaign completion.
        data = arm.read(user, 0x1a1)
        ranks = tuple(struct.unpack_from('5b', data, 0xd6 + mission * 5)
                      for mission in range(1, STORY_MISSIONS + 1))
        story = data[0x7d:0x7d + STORY_MISSIONS]
        mercenary = data[0x175:0x175 + MERCENARY_MISSIONS]
        if any(flag not in (0, 1) for flag in story + mercenary):
            raise ValueError('Invalid native mission flags')
        return cls.from_dict({'ranks': [list(row) for row in ranks],
                              'story': [bool(flag) for flag in story],
                              'mercenary': [bool(flag) for flag in mercenary]})


@dataclass(frozen=True)
class Achievement:
    id: str
    title: str
    description: str
    kind: str
    target: int = 1
    mission: int = 0

    def progress(self, records, unlocked=()):
        if self.kind == 'mission':
            index = self.mission - 1
            count = int(records.story[index] or any(rank >= 0 for rank in records.ranks[index]))
        elif self.kind == 'campaign':
            count = max(sum(row[difficulty] >= 0 for row in records.ranks) for difficulty in range(5))
        elif self.kind == 'extreme':
            count = sum(row[4] >= 0 for row in records.ranks)
        elif self.kind == 's_rank':
            count = sum(any(rank == 4 for rank in row) for row in records.ranks)
        elif self.kind == 'all_s':
            count = max(sum(row[difficulty] == 4 for row in records.ranks) for difficulty in range(5))
        elif self.kind == 'all_difficulties_s':
            count = sum(rank == 4 for row in records.ranks for rank in row)
        elif self.kind == 'mercenary':
            count = sum(records.mercenary)
        elif self.kind == 'purchase':
            count = len(records.purchased_weapons)
        elif self.kind == 'upgrade':
            count = records.upgrades
        elif self.kind == 'platinum':
            count = sum(item.id in unlocked for item in ACHIEVEMENTS if item.kind != 'platinum')
        else:
            raise ValueError('Unknown achievement rule')
        return min(count, self.target), self.target


# Classic RE4 titles use equivalent mobile encounters; unsupported console
# events (Del Lago, bottle caps, costumes) are deliberately absent.
ACHIEVEMENTS = (
    Achievement('village', 'It Begins With a Ring', 'Complete Bloodthirsty, the village encounter.', 'mission', mission=1),
    Achievement('gigante', 'A Rock and a Hard Place', "Defeat El Gigante in The Giant’s Den.", 'mission', mission=4),
    Achievement('ashley', 'Secure Ashley', 'Complete Rescue Ashley.', 'mission', mission=5),
    Achievement('verdugo', 'A Terrifying Assassin', 'Defeat Verdugo in The Strongest Assassin.', 'mission', mission=12),
    Achievement('salazar', 'The Castellan Falls', 'Defeat Salazar in Strange Castellan.', 'mission', mission=14),
    Achievement('krauser', 'The Ties That Bind', 'Defeat Krauser in The Price of Power.', 'mission', mission=20),
    Achievement('saddler', "We’re Going Home", 'Defeat Saddler in Throwdown.', 'mission', mission=22),
    Achievement('campaign', 'Mission Complete', 'Complete all 22 story missions on one difficulty.', 'campaign', target=22),
    Achievement('extreme', 'A Heart of Steel', 'Complete all 22 story missions on Extreme, the highest difficulty.', 'extreme', target=22),
    Achievement('first_s', 'A Cut Above', 'Earn an S rank in a story mission.', 's_rank'),
    Achievement('all_s', 'S Rank Agent', 'Earn S ranks in all 22 story missions on one difficulty.', 'all_s', target=22),
    Achievement('strongest', 'The Strongest Agent', 'Earn S ranks in all 22 story missions on all five difficulties.', 'all_difficulties_s', target=110),
    Achievement('mercenary', 'Hired Gun', 'Clear your first Mercenary mission.', 'mercenary'),
    Achievement('mercenary_master', 'Mercenary Master', 'Clear all 44 Mercenary missions.', 'mercenary', target=44),
    Achievement('first_purchase', 'What Are Ya Buying?', 'Buy a weapon from the Merchant.', 'purchase'),
    Achievement('collector', 'Arms Collector', 'Buy three different weapons from the Merchant.', 'purchase', target=3),
    Achievement('arsenal', 'Gun Fanatic', 'Buy five different weapons from the Merchant.', 'purchase', target=5),
    Achievement('first_upgrade', 'My Preferred Piece', 'Purchase your first weapon tune-up.', 'upgrade'),
    Achievement('tuned', 'Custom Made', 'Purchase five weapon tune-ups.', 'upgrade', target=5),
    Achievement('expert', 'High-Caliber', 'Purchase ten weapon tune-ups.', 'upgrade', target=10),
    Achievement('platinum', 'Legend of the Village', 'Unlock every other launcher achievement.', 'platinum', target=20),
)
IDS = frozenset(item.id for item in ACHIEVEMENTS)


class AchievementStore:
    def __init__(self, root):
        self.path = Path(root) / 'saves' / FILENAME
        self.lock = threading.RLock()
        self.media = {}

    def load(self):
        try:
            with self.path.open('rb') as stream:
                raw = stream.read(MAX_RECORD_BYTES + 1)
        except FileNotFoundError:
            self.media = {}
            return Progress(), {}
        if len(raw) > MAX_RECORD_BYTES:
            raise ValueError('Achievement record is too large')
        try:
            record = json.loads(raw)
        except (ValueError, UnicodeError) as error:
            raise ValueError('Cannot read achievement records') from error
        if (not isinstance(record, dict) or type(record.get('version')) is not int
                or record['version'] != 1):
            raise ValueError('Unsupported achievement record version')
        unlocked = record.get('unlocked')
        if (not isinstance(unlocked, dict) or not set(unlocked) <= IDS
                or any(type(timestamp) is not int or not 0 < timestamp < 2 ** 63
                       for timestamp in unlocked.values())):
            raise ValueError('Invalid achievement unlock records')
        media = record.get('media', {})
        if not isinstance(media, dict) or not set(media) <= set(unlocked):
            raise ValueError('Invalid achievement media records')
        for captures in media.values():
            if not isinstance(captures, dict) or set(captures) - {'image', 'clip'}:
                raise ValueError('Invalid achievement media records')
            for kind, name in captures.items():
                if (not isinstance(name, str) or Path(name).name != name or len(name) > 120
                        or not name.startswith('unlock-')
                        or not name.endswith('.png' if kind == 'image' else '.mp4')
                        or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-.' for c in name)):
                    raise ValueError('Invalid achievement media filename')
        self.media = media
        return Progress.from_dict(record.get('progress')), unlocked

    def update(self, progress):
        with self.lock:
            return self._update(progress)

    def _update(self, progress):
        previous, unlocked = self.load()
        new = []
        for item in ACHIEVEMENTS:
            count, total = item.progress(progress, unlocked)
            if count == total and item.id not in unlocked:
                unlocked[item.id] = time.time_ns()
                new.append(item.id)
        if previous == progress and not new and self.path.exists():
            return new
        self._write(progress, unlocked)
        return new

    def attach_media(self, identifiers, captures):
        with self.lock:
            progress, unlocked = self.load()
            for identifier in identifiers:
                if identifier in unlocked:
                    self.media[identifier] = dict(captures)
            self._write(progress, unlocked)

    def _write(self, progress, unlocked):
        record = {'version': 1, 'progress': progress.as_dict(), 'unlocked': unlocked, 'media': self.media}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.achievements-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(record, stream, indent=2, sort_keys=True)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)


class AchievementTracker:
    """Recover existing progress on native load; record only completed saves.

Read guest memory directly at the return hook, never re-enter ARM execution.
The runtime holds the installation lock; launcher reads atomic JSON snapshots.
"""
    def __init__(self, arm, root):
        from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
        from unicorn import UC_HOOK_CODE
        self.arm, self.store = arm, AchievementStore(root)
        self.loading = None
        self.pending_weapons = set()
        self.pending_upgrades = 0
        self.new_unlocks = deque()
        address = arm.symbols[LOAD_SYMBOL]
        if not address & 1:
            raise RuntimeError('Unsupported native load instruction mode')
        start = address & ~1
        decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
        epilogue = next((instruction.address for instruction in decoder.disasm(
            arm.read(start, arm.symbol_sizes[LOAD_SYMBOL]), start)
            if instruction.mnemonic == 'pop' and 'pc' in instruction.op_str), None)
        if epilogue is None:
            raise RuntimeError('Cannot find audited native load completion')
        self.hooks = [arm.uc.hook_add(UC_HOOK_CODE, self._enter, begin=start, end=start),
                      arm.uc.hook_add(UC_HOOK_CODE, self._leave, begin=epilogue, end=epilogue)]
        if BUY_SYMBOL in arm.symbols:
            # Only the real purchase path reaches the instruction after Regist;
            # failed conditions bypass it, and failed registration returns null.
            buy = (arm.symbols[BUY_SYMBOL] & ~1) + 0x58
            instructions = list(decoder.disasm(arm.read(buy - 4, 4), buy - 4))
            if len(instructions) != 1 or instructions[0].mnemonic != 'bl':
                raise RuntimeError('Unsupported native weapon purchase layout')
            self.hooks.append(arm.uc.hook_add(UC_HOOK_CODE, self._purchase, begin=buy, end=buy))
        if UPGRADE_SYMBOL in arm.symbols and SET_LEVEL_SYMBOL in arm.symbols:
            self.upgrade_return = (arm.symbols[UPGRADE_SYMBOL] & ~1) + 0xc4
            level = arm.symbols[SET_LEVEL_SYMBOL] & ~1
            self.hooks.append(arm.uc.hook_add(UC_HOOK_CODE, self._upgrade, begin=level, end=level))

    def _weapon_id(self, node):
        parameter = self.arm.u32(node + 8)
        category, identifier = self.arm.read(parameter + 0xc, 2)
        return identifier if category == 0 else None

    def _purchase(self, uc, address, size, context):
        from unicorn.arm_const import UC_ARM_REG_R0
        node = uc.reg_read(UC_ARM_REG_R0)
        if node:
            identifier = self._weapon_id(node)
            if identifier is not None:
                self.pending_weapons.add(identifier)

    def _upgrade(self, uc, address, size, context):
        from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2
        if uc.reg_read(UC_ARM_REG_LR) & ~1 != self.upgrade_return:
            return
        node, skill, new = (uc.reg_read(register) for register in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        if skill > 15 or self._weapon_id(node) is None:
            return
        old = struct.unpack('<h', self.arm.read(node + 14 + skill * 2, 2))[0]
        if (new & 0xffff) > old:
            self.pending_upgrades += 1

    def _enter(self, uc, address, size, context):
        from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1
        self.loading = (uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1))

    def _leave(self, uc, address, size, context):
        from unicorn.arm_const import UC_ARM_REG_R0
        loading, self.loading = self.loading, None
        if loading and uc.reg_read(UC_ARM_REG_R0) == 1:
            if loading[1] & 0x20:
                self.pending_weapons.clear()
                self.pending_upgrades = 0
            self.capture(*loading, recovered=True)

    def capture(self, user, sections, recovered=False):
        # Mission records belong to section 0x20. A Coin Shoot-only save
        # (0x10) must not publish unrelated in-memory story progress.
        if not sections & 0x20:
            return
        from .runtime_log import log
        try:
            progress = Progress.from_native(self.arm, user)
            with self.store.lock:
                previous, _ = self.store.load()
                progress = replace(progress,
                    purchased_weapons=tuple(sorted(set(previous.purchased_weapons) | self.pending_weapons)),
                    upgrades=min(1000000, previous.upgrades + self.pending_upgrades))
                new = self.store.update(progress)
            self.pending_weapons.clear()
            self.pending_upgrades = 0
            if new and not recovered:
                self.new_unlocks.extend(new)
            for item in ACHIEVEMENTS:
                if item.id in new:
                    log.info('Achievement unlocked: %s', item.title)
        except (OSError, ValueError, RuntimeError) as error:
            # Optional launcher records must never stop a native save/load.
            # Preserve malformed records instead of silently replacing them.
            log.warning('Could not update local achievements: %s', error)
