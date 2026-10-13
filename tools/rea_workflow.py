"""Validate the pinned REA provider against supported ELF/Capstone mappings.

All reference instructions, REA output and snapshots must stay outside the
checkout. This tool is a development dependency; the host never imports it.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
from elftools.elf.elffile import ELFFile
from re4pc.assets import COMPATIBLE_LIBRARIES, validate_libraries
from re4pc.paths import game_dir

SAMPLES = {
    'libbio4af.so': ('JNI_OnLoad', '_ZN14Bio4_FrameWork6doMainEPv', '__aeabi_f2uiz'),
    'libmc_eruption_for_android_jni.so': ('JNI_OnLoad', '__aeabi_idiv0', '__aeabi_fcmpeq'),
}


def references(path, names):
    with Path(path).open('rb') as stream:
        elf = ELFFile(stream)
        if elf['e_machine'] != 'EM_ARM' or elf.elfclass != 32 or not elf.little_endian:
            raise ValueError('Expected a little-endian ARM32 ELF')
        symbols = {s.name: s for s in elf.get_section_by_name('.dynsym').iter_symbols()}
        result = []
        for name in names:
            symbol = symbols[name]
            thumb = bool(symbol['st_value'] & 1)
            address = symbol['st_value'] & ~1
            section = elf.get_section(symbol['st_shndx'])
            code = section.data()[address-section['sh_addr']:address-section['sh_addr']+symbol['st_size']]
            decoded = list(Cs(CS_ARCH_ARM, CS_MODE_THUMB if thumb else CS_MODE_ARM).disasm(code, address))[:8]
            if not decoded or decoded[0].address != address:
                raise ValueError('Capstone could not decode the function entry')
            result.append({'symbol': name, 'elf_value': symbol['st_value'], 'address': address,
                'elf_image_base': min(segment['p_vaddr'] for segment in elf.iter_segments() if segment['p_type']=='PT_LOAD'),
                'file_offset': section['sh_offset'] + address-section['sh_addr'],
                'host_module_offset': 0x200000 if path.name == 'libbio4af.so' else 0,
                'isa': 'Thumb' if thumb else 'ARM',
                'instructions': [{'address': i.address, 'size': i.size, 'mnemonic': i.mnemonic,
                                  'operands': i.op_str} for i in decoded]})
        return result


def _mnemonic(value):
    value = value.lower().split('.')[0]
    return {'movs':'mov', 'adds':'add', 'subs':'sub', 'ands':'and', 'lsls':'lsl',
            'lsrs':'lsr', 'asrs':'asr', 'eors':'eor', 'orrs':'orr', 'muls':'mul',
            'bcs':'bhs', 'bcc':'blo'}.get(value, value)


def _shift_alias(row, expected):
    """Capstone's ARM shift alias and Ghidra's MOV must name the same operands."""
    match = re.match(r'^(?:0x)?[0-9a-fA-F]+:\s*(movs?)\s+(r\d+),\s*(r\d+),\s*(lsl|lsr|asr|ror)\s+#(0x[0-9a-fA-F]+|\d+)$', row, re.I)
    wanted = re.match(r'^(r\d+),\s*(r\d+),\s*#(0x[0-9a-fA-F]+|\d+)$', expected.get('operands', ''), re.I)
    return bool(match and wanted and _mnemonic(expected['mnemonic']) == match[4].lower()
                and expected['mnemonic'].endswith('s') == match[1].lower().endswith('s')
                and (match[2], match[3]) == (wanted[1], wanted[2]) and int(match[5],0) == int(wanted[3],0))


def verify_instructions(evidence, reference, digest, image=None):
    if evidence['subject']['digest']['sha256'] != digest:
        raise ValueError('REA inspected different artifact bytes')
    result = evidence['normalized_result']
    delta = 0
    if image is not None:
        if image['subject']['digest']['sha256'] != digest:
            raise ValueError('REA load image has a different artifact identity')
        loaded = image['normalized_result'].get('observations', image['normalized_result'])
        delta = int(loaded['image_base'], 16) - reference['elf_image_base']
        address = reference['address'] + delta
        mapping = next((m for m in loaded['mappings'] if m['initialized'] and m['file_offset'] is not None
                        and int(m['start'], 16) <= address <= int(m['end'], 16)), None)
        if mapping is None or mapping['file_offset'] + address-int(mapping['start'],16) != reference['file_offset']:
            raise ValueError('Ghidra source-file mapping does not match ELF section offset')
        backing = loaded['source_files'][mapping['source_file_index']]
        if backing['original_sha256'] != digest:
            raise ValueError('Ghidra file backing has a different artifact identity')
    if int(result['procedure']['address'], 16) != reference['address'] + delta:
        raise ValueError('REA function entry does not match ELF/Capstone')
    rows = result['instructions'][:len(reference['instructions'])]
    if len(rows) != len(reference['instructions']):
        raise ValueError('REA instruction window is incomplete')
    for row, expected in zip(rows, reference['instructions']):
        match = re.match(r'^(?:0x)?([0-9a-fA-F]+):\s*(\S+)', row)
        if not match or int(match[1], 16) != expected['address'] + delta:
            raise ValueError('REA instruction boundaries do not match Capstone')
        actual = _mnemonic(match[2])
        wanted = _mnemonic(expected['mnemonic'])
        # Capstone prints aliases for these ARM stack operations.
        if actual != wanted and (actual, wanted) not in (('stmdb','push'), ('ldmia','pop')) and not _shift_alias(row, expected):
            raise ValueError('REA decoder mnemonic does not match Capstone: ' + actual + '/' + wanted)
    return {'symbol': reference['symbol'], 'address': reference['address'],
            'provider_address': reference['address'] + delta, 'provider_image_delta': delta,
            'isa': reference['isa'], 'checked_instructions': len(rows), 'verified': True}


def run_cli(rea, arguments, output, environment, reuse=False):
    operations = {'instructions':'read_function_instructions', 'function':'analyze_function',
                  'decompile':'procedure_pseudo_code', 'inspect-native-load-image':'inspect_native_load_image'}
    if reuse and arguments[0] in operations:
        candidates = []
        try:
            candidates.append(json.loads(output.read_text()))
        except (OSError, ValueError):
            pass
        if '--snapshot' in arguments:
            snapshot = Path(arguments[arguments.index('--snapshot')+1])
            if snapshot.exists():
                candidates += json.loads(snapshot.read_text())['evidence_bundle']['records']
        target = Path(arguments[1]).resolve()
        parameters = {} if arguments[0]=='inspect-native-load-image' else {'procedure':arguments[2]}
        for value in candidates:
            if (value.get('operation') == operations[arguments[0]] and value.get('parameters') == parameters
                    and value.get('subject', {}).get('digest', {}).get('sha256') == COMPATIBLE_LIBRARIES.get(target.name)
                    and value.get('provider') == {'id':'ghidra','name':'Ghidra','version':'12.1.4'}):
                output.write_text(json.dumps(value)+'\n')
                return value
    with output.open('wb') as stream, output.with_suffix('.stderr').open('wb') as errors:
        process = subprocess.run([str(rea), *arguments, '--json'], stdout=stream, stderr=errors,
                                 env=environment, timeout=900)
    if process.returncode:
        raise RuntimeError('REA command failed; inspect ' + str(output))
    return json.loads(output.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=game_dir())
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rea', default='rea')
    parser.add_argument('--ghidra', type=Path, required=True)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--package-artifact', action='append', type=Path, default=[])
    parser.add_argument('--resume', action='store_true', help='Reuse saved load-image observations after checking their artifact/provider identity')
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output == checkout or checkout in output.parents:
        parser.error('Store REA output outside the source checkout')
    output.mkdir(parents=True, exist_ok=True)
    validate_libraries(args.game)
    environment = dict(os.environ, GHIDRA_INSTALL_DIR=str(args.ghidra.resolve()), JAVA_HOME=str(args.java_home.resolve()))
    report = {'schema_version': 1, 'gate_passed': False, 'engine_hashes': COMPATIBLE_LIBRARIES,
              'packages_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.package_artifact},
              'mappings': [], 'failures': []}
    try:
        version = subprocess.check_output([args.rea, '--version'], text=True, env=environment).strip()
        properties = (args.ghidra/'Ghidra/application.properties').read_text()
        java = subprocess.run([str(args.java_home/'bin/java'), '-version'], text=True, capture_output=True, env=environment, check=True).stderr
        if version != '6.4.0' or 'application.version=12.1.4' not in properties or not re.search(r'version "21\.', java):
            raise ValueError('Workflow requires REA 6.4.0, Ghidra 12.1.4 and JDK 21')
        report['versions'] = {'rea': version, 'ghidra': '12.1.4', 'java': java.splitlines()[0]}
        doctor = run_cli(args.rea, ['doctor', '--provider', 'ghidra'], output/'doctor.json', environment)
        if not doctor['healthy']:
            raise RuntimeError('REA Ghidra readiness failed')
        for library, names in SAMPLES.items():
            target = args.game/'lib'/library
            directory = output/library
            directory.mkdir(exist_ok=True)
            reference = references(target, names)
            (directory/'capstone-reference.json').write_text(json.dumps(reference, indent=2)+'\n')
            image_path = directory/'load-image.json'
            image = (json.loads(image_path.read_text()) if args.resume and image_path.exists() else
                     run_cli(args.rea, ['inspect-native-load-image', str(target.resolve()), '--provider', 'ghidra'], image_path, environment))
            if image['subject']['digest']['sha256'] != COMPATIBLE_LIBRARIES[library] or image['provider'] != {'id':'ghidra','name':'Ghidra','version':'12.1.4'}:
                raise ValueError('Load image identity/provider mismatch')
            loaded = image['normalized_result'].get('observations', image['normalized_result'])
            report.setdefault('load_image_limitations', {})[library] = image['normalized_result'].get('limitations', [])
            delta = int(loaded['image_base'], 16) - reference[0]['elf_image_base']
            for index, entry in enumerate(reference):
                try:
                    evidence = run_cli(args.rea, ['instructions', str(target.resolve()), hex(entry['address'] + delta),
                        '--provider', 'ghidra', '--snapshot', str(directory/'snapshot.json')],
                        directory/f'instructions-{index}.json', environment, args.resume)
                    row = verify_instructions(evidence, entry, COMPATIBLE_LIBRARIES[library], image)
                    report['mappings'].append(dict(row, library=library,
                        host_address_formula='shared_memory_base + module_offset + (ELF_value & ~1)'))
                    print('REA_MAPPING_PASS', library, entry['symbol'], entry['isa'], flush=True)
                except (RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
                    report['failures'].append({'library': library, 'symbol': entry['symbol'], 'error': str(error)})
            # A dossier and explicit pseudocode query validate higher level APIs.
            for command in ('function', 'decompile'):
                run_cli(args.rea, [command, str(target.resolve()), hex(reference[0]['address'] + delta),
                    '--provider', 'ghidra', '--snapshot', str(directory/'snapshot.json')],
                    directory/(command+'.json'), environment, args.resume)
        report['gate_passed'] = not report['failures'] and len(report['mappings']) == sum(map(len, SAMPLES.values()))
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
        report['failures'].append({'error': str(error)})
    finally:
        (output/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print('REA_WORKFLOW_PASS' if report['gate_passed'] else 'REA_WORKFLOW_INCOMPLETE', output/'summary.json')
    return 0 if report['gate_passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
