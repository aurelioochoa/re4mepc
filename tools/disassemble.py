"""Inspect ARM symbols without executing proprietary binaries."""
import sys
from pathlib import Path
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_ARM

with Path(sys.argv[1]).open('rb') as stream:
    elf = ELFFile(stream)
    symbols = elf.get_section_by_name('.dynsym')
    for symbol in symbols.iter_symbols():
        if not any(term in symbol.name for term in sys.argv[2:]) or not symbol['st_size']:
            continue
        if symbol['st_info']['type'] != 'STT_FUNC':
            continue
        print('\n', symbol.name, hex(symbol['st_value']), symbol['st_size'])
        address = symbol['st_value'] & ~1
        section = elf.get_section(symbol['st_shndx'])
        code = section.data()[address-section['sh_addr']:address-section['sh_addr']+symbol['st_size']]
        disasm = Cs(CS_ARCH_ARM, CS_MODE_THUMB if symbol['st_value'] & 1 else CS_MODE_ARM)
        for instruction in disasm.disasm(code, address):
            print(f'{instruction.address:08x} {instruction.mnemonic:8} {instruction.op_str}')
