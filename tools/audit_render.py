"""Derive a symbol-level rendering audit without publishing engine instructions."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
from capstone.arm import ARM_OP_IMM
from elftools.elf.elffile import ELFFile
from re4pc.assets import COMPATIBLE_LIBRARIES, validate_libraries
from re4pc.paths import game_dir

AUDIT_SYMBOLS = (
    '_ZN9Bio4_Main11onDrawFrameEP7_JNIEnvP8_jobjectS3_',
    '_ZN14Bio4_FrameWork6doMainEPv',
    '_ZN14Bio4_FrameWork10_execStateElPv',
    '_ZN14Bio4_FrameWork10_drawStateElPv',
    '_ZN14Bio4_FrameWork17_execState_ResCtlEPv',
    '_ZN14Bio4_FrameWork17_drawState_ResCtlEPv',
    '_ZN19CMN_GameTaskManager5FrameEPv',
    '_ZN19CMN_GameTaskManager6RenderEPv',
    '_ZN14GM_TaskManager5FrameEPv',
    '_ZN14GM_TaskManager6RenderEPv',
    '_ZN11GM_CtrlMain4MainEP14Bio4_FrameWork',
    '_ZN11GM_CtrlMain4DrawEP14Bio4_FrameWork',
    '_ZN13GM_MisConduct5FrameEP11GM_CtrlMain',
    '_ZN13GM_MisConduct4DrawEP11GM_CtrlMain',
    '_ZN16GM_CtrlLyt_Input5FrameEP14Bio4_FrameWork',
    '_ZN16GM_CtrlLyt_Input4DrawEP14Bio4_FrameWork',
    '_ZN10ERP_Camera15Set_LookAt_BindEv',
    '_ZN18GM_CtrlMain_Camera4MainEP11GM_CtrlMain',
    '_ZN13Bio4_UserData4SaveEl',
)


def audit(root):
    validate_libraries(root)
    path = Path(root) / 'lib/libbio4af.so'
    rows = []
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        functions = {s.name: s for s in elf.get_section_by_name('.dynsym').iter_symbols()
                     if s['st_size'] and s['st_info']['type'] == 'STT_FUNC'}
        by_address = {s['st_value'] & ~1: name for name, s in functions.items()}
        for name in AUDIT_SYMBOLS:
            if name not in functions:
                rows.append({'symbol': name, 'status': 'unresolved'})
                continue
            symbol = functions[name]
            address = symbol['st_value'] & ~1
            section = elf.get_section(symbol['st_shndx'])
            offset = address - section['sh_addr']
            code = section.data()[offset:offset + symbol['st_size']]
            decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB if symbol['st_value'] & 1 else CS_MODE_ARM)
            decoder.detail = True
            calls, indirect, stores = [], 0, 0
            for instruction in decoder.disasm(code, address):
                if instruction.mnemonic.startswith(('str', 'stm')):
                    stores += 1
                if instruction.mnemonic in ('bl', 'blx'):
                    if instruction.operands and instruction.operands[0].type == ARM_OP_IMM:
                        target = instruction.operands[0].imm & ~1
                        calls.append(by_address.get(target, 'unknown direct target (PLT/local)'))
                    else:
                        indirect += 1
                # Literal pools and jump tables need control-flow recovery;
                # these counts are static lower bounds, never a purity proof.
                if instruction.mnemonic == 'pop' and 'pc' in instruction.op_str:
                    break
            rows.append({'symbol': name, 'status': 'inspected', 'bytes': len(code),
                         'direct_calls': calls, 'indirect_calls': indirect,
                         'store_instructions_lower_bound': stores})
    return {'schema_version': 1, 'engine_hashes': COMPATIBLE_LIBRARIES,
            'presentation_gate': 'closed', 'supported_rates': [20],
            'reason': 'State dispatch, virtual rendering and rendering-side mutation are not isolated or equivalence-verified',
            'counts_are_lower_bounds': True, 'functions': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=game_dir())
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.game)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('RENDER_AUDIT_PASS: presentation gate closed; report:', args.output)


if __name__ == '__main__':
    main()
