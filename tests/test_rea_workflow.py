import importlib.util
from pathlib import Path
import unittest
from copy import deepcopy

spec = importlib.util.spec_from_file_location('rea_workflow', Path(__file__).resolve().parents[1]/'tools/rea_workflow.py')
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


class ReaWorkflowTests(unittest.TestCase):
    def test_shift_alias_checks_registers_amount_and_flag_update(self):
        expected={'mnemonic':'lsls','operands':'r2, r0, #1'}
        self.assertTrue(workflow._shift_alias('0x1000: movs r2, r0, lsl #0x1',expected))
        for wrong in ('0x1000: movs r2, r0, lsl #0x2', '0x1000: movs r3, r0, lsl #0x1',
                      '0x1000: mov r2, r0, lsl #0x1', '0x1000: movs r2, r0, lsr #0x1'):
            self.assertFalse(workflow._shift_alias(wrong,expected))

    def test_rebased_provider_coordinates_require_verified_file_mapping(self):
        reference = {'address':4096, 'elf_image_base':0, 'file_offset':36,
                     'symbol':'synthetic', 'isa':'ARM',
                     'instructions':[{'address':4096,'mnemonic':'bx'}]}
        evidence = {'subject':{'digest':{'sha256':'a'*64}}, 'normalized_result':{
            'procedure':{'address':'0x2000'},'instructions':['0x2000: bx lr']}}
        image = {'subject':{'digest':{'sha256':'a'*64}}, 'normalized_result':{
            'image_base':'0x1000','source_files':[{'original_sha256':'a'*64}],
            'mappings':[{'initialized':True,'file_offset':36,'source_file_index':0,'start':'0x2000','end':'0x2fff'}]}}
        row = workflow.verify_instructions(evidence, reference, 'a'*64, image)
        self.assertEqual(row['provider_image_delta'],4096)
        for kind in ('offset','backing','base'):
            bad = deepcopy(image)
            if kind=='offset':bad['normalized_result']['mappings'][0]['file_offset']=37
            if kind=='backing':bad['normalized_result']['source_files'][0]['original_sha256']='b'*64
            if kind=='base':bad['normalized_result']['image_base']='0x2000'
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                workflow.verify_instructions(evidence,reference,'a'*64,bad)

    def test_external_evidence_identity_address_and_decoder_fail_closed(self):
        reference = {'address': 4096, 'symbol': 'synthetic', 'isa': 'Thumb',
                     'instructions': [{'address': 4096, 'mnemonic': 'movs'},
                                      {'address': 4098, 'mnemonic': 'bx'}]}
        evidence = {'subject': {'digest': {'sha256': 'a'*64}}, 'normalized_result': {
            'procedure': {'address': '00001000'}, 'instructions': ['00001000: mov r0,r1', '00001002: bx lr']}}
        self.assertTrue(workflow.verify_instructions(evidence, reference, 'a'*64)['verified'])
        for change in ('hash', 'address', 'decode', 'incomplete', 'boundaries'):
            bad = deepcopy(evidence)
            if change == 'hash': bad['subject']['digest']['sha256'] = 'b'*64
            if change == 'address': bad['normalized_result']['procedure']['address'] = '00002000'
            if change == 'decode': bad['normalized_result']['instructions'][0] = '00001000: add r0,r1'
            if change == 'incomplete': bad['normalized_result']['instructions'].pop()
            if change == 'boundaries': bad['normalized_result']['instructions'][1] = '00001004: bx lr'
            with self.subTest(change=change), self.assertRaises(ValueError):
                workflow.verify_instructions(bad, reference, 'a'*64)
