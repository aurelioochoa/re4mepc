"""Validated, atomic per-user desktop settings; explicit options win on load."""
import json
import math
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path
from .actions import DEFAULT_BINDINGS, NATIVE_CODES, CONTROLLER_INPUTS, RESERVED_KEYS
from .timing import PRESENTATION_RATES

DEFAULTS = {'version': 1, 'bindings': DEFAULT_BINDINGS, 'sensitivity': 1.0,
            'controller_sensitivity': 1.0, 'invert_y': False, 'stick_dead_zone': 0.18,
            'window_mode': 'windowed', 'window_width': 800, 'window_height': 480,
            'presentation_rate': 20, 'achievement_capture': 'screenshot',
            'achievement_clip_seconds': 10, 'game_language': 'en',
            'launcher_language': 'en', 'laser_color': '#ff0000',
            'laser_shape': 'original', 'laser_size': 1.0}


def settings_path():
    value = os.environ.get('XDG_CONFIG_HOME')
    config = Path(value) if value and Path(value).is_absolute() else Path.home() / '.config'
    return config / 're4mepc' / 'settings.json'


def validate(values):
    if not isinstance(values, dict):
        raise ValueError('Settings must be an object')
    unknown = set(values) - set(DEFAULTS)
    if unknown:
        raise ValueError('Unknown settings: ' + ', '.join(sorted(unknown)))
    result = deepcopy(DEFAULTS)
    result.update(deepcopy(values))
    if type(result['version']) is not int or result['version'] != 1:
        raise ValueError('Unsupported settings version')
    for name, minimum, maximum in (('sensitivity', 0.05, 10), ('controller_sensitivity', 0.05, 10),
                                   ('stick_dead_zone', 0.0, 0.9), ('laser_size', 0.5, 3.0)):
        number = result[name]
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not minimum <= number <= maximum:
            raise ValueError(f'{name} must be between {minimum} and {maximum}')
    if type(result['invert_y']) is not bool:
        raise ValueError('invert_y must be boolean')
    if not isinstance(result['laser_color'], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', result['laser_color']):
        raise ValueError('laser_color must be a hex color like #ff0000')
    result['laser_color'] = result['laser_color'].lower()
    if result['laser_shape'] not in ('original', 'circle', 'predator', 'black_matter'):
        raise ValueError('laser_shape must be original, circle, predator or black_matter')
    if result['window_mode'] not in ('windowed', 'fullscreen'):
        raise ValueError('window_mode must be windowed or fullscreen')
    from .languages import GAME_LANGUAGES, LAUNCHER_LANGUAGES
    for name, choices in (('game_language', GAME_LANGUAGES), ('launcher_language', LAUNCHER_LANGUAGES)):
        if not isinstance(result[name], str) or result[name] not in choices:
            raise ValueError(name + ' must be one of: ' + ', '.join(choices))
    if result['achievement_capture'] not in ('off', 'screenshot', 'clip', 'both'):
        raise ValueError('achievement_capture must be off, screenshot, clip or both')
    seconds = result['achievement_clip_seconds']
    if type(seconds) is not int or not 5 <= seconds <= 15:
        raise ValueError('achievement_clip_seconds must be an integer between 5 and 15')
    for name in ('window_width', 'window_height'):
        if type(result[name]) is not int or not 240 <= result[name] <= 16384:
            raise ValueError(f'{name} must be an integer between 240 and 16384')
    if type(result['presentation_rate']) is not int or result['presentation_rate'] not in PRESENTATION_RATES:
        raise ValueError('presentation_rate must be 20, 30, 60, 90, 120, 144, 165, 240 or 0 (uncapped)')
    bindings = result['bindings']
    if not isinstance(bindings, dict) or set(bindings) != {'keyboard', 'mouse', 'controller'}:
        raise ValueError('bindings must contain keyboard, mouse and controller')
    for device, table in bindings.items():
        if not isinstance(table, dict) or set(table) - set(NATIVE_CODES):
            raise ValueError(f'Invalid {device} action bindings')
        seen = set()
        for action, identifiers in table.items():
            if not isinstance(identifiers, list):
                raise ValueError(f'{device}.{action} must be a list')
            for identifier in identifiers:
                valid = (isinstance(identifier, str) and identifier in CONTROLLER_INPUTS) if device == 'controller' else type(identifier) is int and (1 <= identifier <= 5 if device == 'mouse' else 0 <= identifier <= 0x7fffffff and not 0x20000000 <= identifier < 0x20010000)
                if device == 'keyboard' and identifier in RESERVED_KEYS:
                    raise ValueError('Tab, F3 and F12 are reserved desktop controls')
                if not valid or identifier in seen:
                    raise ValueError(f'Invalid or duplicate {device} binding: {identifier!r}')
                seen.add(identifier)
    return result


class Settings:
    @staticmethod
    def load(path=None, overrides=None):
        target = Path(path) if path is not None else settings_path()
        try:
            values = json.loads(target.read_text())
        except FileNotFoundError:
            values = {}
        result = validate(values)
        if overrides:
            result.update({key: value for key, value in overrides.items() if value is not None})
            result = validate(result)
        return result

    @staticmethod
    def save(values, path=None):
        values = validate(values)
        target = Path(path) if path is not None else settings_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.settings-', suffix='.tmp', dir=target.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(values, stream, indent=2, sort_keys=True)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return values
