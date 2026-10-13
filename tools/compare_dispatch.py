"""Two independent batches of five paired dispatch-candidate experiments.

The candidate removes a redundant register-argument list copy. It is installed
only in this test process; timing eligibility never automatically changes source.
"""
import sys, json, hashlib, time, statistics, struct, argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from re4pc.arm import ArmRuntime
from unicorn import UcError
from unicorn.arm_const import UC_ARM_REG_SP
from re4pc.paths import isolated_game, game_dir, test_output
from tools.benchmark import run_case, checkpoint, source_identity


def candidate_args(self,count=4):
    if count<0:raise ValueError('Negative argument count')
    if self._callback_args is None:
        status=self.uc._do_reg_read_batch(self._arg_registers,self._arg_pointers,min(count,4))
        if status:raise UcError(status)
        result=self._arg_values[:min(count,4)]
    else:
        result=self._callback_args[:min(count,4)]
    if count>4:
        sp=self.uc.reg_read(UC_ARM_REG_SP)
        result+=struct.unpack('<'+'I'*(count-4),self.read(sp,4*(count-4)))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,default=game_dir())
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    output=test_output('dispatch-candidate',args.output)
    checkout=Path(__file__).resolve().parents[1]
    if output.resolve()==checkout or checkout in output.resolve().parents:parser.error('Keep engine fixtures outside the checkout')
    original=ArmRuntime.args
    report={'schema_version':1,'source':source_identity(),'candidate':'remove redundant Python list copy after ctypes register-buffer slicing',
            'candidate_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'profiled':False,'records':[],'accepted':False,'target':'loading_max_work_ms',
            'background':'desktop background activity uncontrolled; variability gates apply'}
    # Exercise both direct ARM register reads and imported callbacks, including
    # stack arguments and errors, before any timing run.
    arm=ArmRuntime()
    try:
        from re4pc.arm import REGS
        for reg,value in zip(REGS,(11,22,33,44)):arm.uc.reg_write(reg,value)
        arm.write(arm.uc.reg_read(UC_ARM_REG_SP),struct.pack('<II',55,66))
        for cached in (None,[11,22,33,44]):
            arm._callback_args=cached
            for count in (0,1,4,5,6):
                a=original(arm,count);b=candidate_args(arm,count)
                assert a==b and type(a)==type(b)
            for function in (original,candidate_args):
                try:function(arm,-1)
                except ValueError as e:assert str(e)=='Negative argument count'
                else:raise AssertionError('Negative count accepted')
        report['argument_equivalence']='register, cached callback, 0/1/4/5/6 arguments and negative count passed'
    finally:arm.close()
    root=isolated_game(args.game,output)
    reference_graphics=None
    try:
        for batch in (1,2):
            for pair in range(1,6):
                order=('baseline','candidate') if pair%2 else ('candidate','baseline')
                for variant in order:
                    ArmRuntime.args=original if variant=='baseline' else candidate_args
                    directory=output/f'batch-{batch}-pair-{pair}-{variant}'
                    directory.mkdir()
                    case=run_case(root,directory,'disabled',True,200,native_destination=3,expected_graphics=reference_graphics)
                    if reference_graphics is None:reference_graphics=(case['stats']['graphics']['renderer'],case['stats']['graphics']['version'])
                    case.update(batch=batch,pair=pair,variant=variant)
                    report['records'].append(case)
                    checkpoint(output/'results.json',report)
                    print('PAIRED_CASE',batch,pair,variant,round(case['loading_max_work_ms'],3),flush=True)
        gates=[]
        for batch in (1,2):
            base=[r for r in report['records'] if r['batch']==batch and r['variant']=='baseline']
            candidate=[r for r in report['records'] if r['batch']==batch and r['variant']=='candidate']
            improvements=[1-next(r for r in candidate if r['pair']==b['pair'])['loading_max_work_ms']/b['loading_max_work_ms'] for b in base]
            variability=(max(r['loading_max_work_ms'] for r in base)-min(r['loading_max_work_ms'] for r in base))/statistics.median(r['loading_max_work_ms'] for r in base)
            effect=statistics.median(improvements)
            regression=statistics.median(r['gameplay_work_ms']['p95'] for r in candidate)/statistics.median(r['gameplay_work_ms']['p95'] for r in base)-1
            gates.append({'batch':batch,'paired_median_improvement':effect,'baseline_range_fraction':variability,
                          'gameplay_p95_regression':regression,'timing_pass':effect>=.1 and effect>variability and regression<=.05})
        report['batches']=gates
        report['accepted']=False # Source is retained only after every non-timing gate, never by this experiment alone.
        report['timing_gate_passed']=all(row['timing_pass'] for row in gates)
        report['outcome']='timing eligible, independent controls/save/render/clock/diagnostics gates still required' if report['timing_gate_passed'] else 'rejected: timing/variability/gameplay gate did not qualify'
        checkpoint(output/'results.json',report)
    finally:ArmRuntime.args=original
    print('PAIRED_EXPERIMENT_RECORDED',output/'results.json',flush=True)


if __name__=='__main__':
    main()
