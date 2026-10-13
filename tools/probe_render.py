"""Observe extra native Draw calls in isolated Unicorn fixtures, at equal ticks.

This is an audit, not an independent rendering prototype. Full memory snapshots,
instruction output and screenshots stay outside the checkout. Host/GPU state
cannot be restored by copying guest memory; the fixture is discarded afterwards.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1
from re4pc.assets import COMPATIBLE_LIBRARIES
from re4pc.game import Game
from re4pc.paths import game_dir, isolated_game, test_output
from tools.benchmark import Replay, source_identity, stage_number

CANDIDATES = ('_ZN13GM_MisConduct4DrawEP11GM_CtrlMain',
              '_ZN11GM_CtrlMain4DrawEP14Bio4_FrameWork',
              '_ZN14GM_TaskManager6RenderEPv')


def state(game):
    arm, pc = game.arm, game.pc
    player = pc.player
    obj = arm.u32(player)
    body = arm.u32(obj+0x120)
    mission = arm.call('_ZN13GM_MisConduct8Get_InstEv')
    param = arm.call('_ZN12GM_CtrlParam8Get_InstEv')
    return {'ticks': game.frames, 'stage': stage_number(game),
            'position_hash': hashlib.sha256(arm.read(body+0x88,12)).hexdigest(),
            'player_state_hash': hashlib.sha256(arm.read(player+0x36,4)).hexdigest(),
            'mission_ticks': arm.u32(mission),
            'mission_seconds': arm.call('_ZN12GM_CtrlParam15Get_MisTotalSecEv',param),
            'ammunition': arm.call('_ZN16Bio4_AttacheCase16GetLoadBulletNumEl',param,arm.read(player+0x5e,1)[0]),
            'input_controller_hash': hashlib.sha256(arm.read(pc.controller,0x44)).hexdigest(),
            'saves': {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in game.save_store.saves.iterdir() if p.is_file()}}


def probe(source, output, symbol):
    root = isolated_game(source, output)
    game = Game(root, hidden=True, skip_videos=True)
    observed = []
    hooks = []
    replay = Replay(game)
    try:
        address = game.arm.symbols[symbol] & ~1
        def entry(uc, address, size, context):
            observed[:] = [uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1)]
        hooks.append(game.arm.uc.hook_add(UC_HOOK_CODE,entry,begin=address,end=address))
        replay.village()
        replay.close()
        replay.advance(20)
        if not observed:
            return {'symbol':symbol,'status':'not observed; no guessed call arguments'}
        before_state = state(game)
        before = game.arm.read(game.arm.base, game.arm.SIZE)
        calls = game.arm.calls.copy()
        draws, textures = game.graphics.draws, game.graphics.textures
        writes = []
        def write(uc, access, address, size, value, context):
            if len(writes)<4096:
                writes.append((address-game.arm.base,size))
        hooks.append(game.arm.uc.hook_add(UC_HOOK_MEM_WRITE,write))
        game.arm.call(symbol,*observed)
        game.arm.uc.hook_del(hooks.pop())
        after = game.arm.read(game.arm.base,game.arm.SIZE)
        pages = [offset for offset in range(0,len(before),4096) if before[offset:offset+4096]!=after[offset:offset+4096]]
        # Hashes and addresses describe effects without publishing engine bytes.
        services = {name:count-calls[name] for name,count in game.arm.calls.items() if count!=calls[name]}
        after_state = state(game)
        game.graphics.screenshot(output/'after-extra-draw.png')
        return {'symbol':symbol,'status':'observed','before':before_state,'after':after_state,
                'changed_observed_state': [key for key in before_state if before_state[key]!=after_state[key]],
                'guest_changed_pages':len(pages),'changed_page_offsets':pages[:64],
                'guest_store_events_capped':len(writes),'store_ranges':writes[:64],
                'host_service_calls':services,'additional_draw_calls':game.graphics.draws-draws,
                'additional_texture_uploads':game.graphics.textures-textures,
                'limitations':['Guest writes include stack/scratch state; page changes alone do not prove gameplay coupling.',
                    'Native C helpers can write shared memory outside Unicorn write hooks; full guest comparison covers those writes.',
                    'Graphics/audio/driver resources and asynchronous host effects are not covered by guest-memory equality.',
                    'Equal selected state fields do not establish collision, damage, interaction, object lifecycle or interpolation equivalence.']}
    finally:
        replay.close()
        for hook in hooks:game.arm.uc.hook_del(hook)
        game.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,default=game_dir())
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    output = test_output('render-probe',args.output)
    checkout=Path(__file__).resolve().parents[1]
    if output.resolve()==checkout or checkout in output.resolve().parents:
        parser.error('Keep isolated engine fixtures outside the checkout')
    report={'schema_version':1,'source':source_identity(),'engine_hashes':COMPATIBLE_LIBRARIES,
            'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'presentation_hz':20,'prototype_built':False,'candidates':[]}
    for index,symbol in enumerate(CANDIDATES):
        directory=output/str(index);directory.mkdir()
        try:row=probe(args.game,directory,symbol)
        except (RuntimeError,ValueError,KeyError) as error:row={'symbol':symbol,'status':'failed','error':str(error)}
        report['candidates'].append(row)
        (output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
        print('RENDER_PROBE',symbol,row['status'],flush=True)
    print('RENDER_AUDIT_RECORDED: presentation gate remains closed',output/'results.json',flush=True)


if __name__=='__main__':main()
