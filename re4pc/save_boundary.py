"""Back up complete saves at the supported engine's serialization boundary."""
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1
from contextlib import nullcontext

SAVE_SYMBOL = '_ZN13Bio4_UserData4SaveEl'


class SaveBoundary:
    """Save returns only after its file object's destructor closes the stream.

    Engine hashes are validated before this hook is installed. Derive its sole
    return from the symbol rather than accepting a return in an unknown layout.
    No snapshot is published as successful after an interrupted native call.
    """
    def __init__(self, arm, store, on_saved=None):
        self.arm, self.store = arm, store
        self.on_saved = on_saved
        self.save_args = None
        self.active = False
        self.completed = self.failed = 0
        address = arm.symbols[SAVE_SYMBOL]
        if not address & 1:
            raise RuntimeError('Unsupported native save instruction mode')
        start = address & ~1
        size = arm.symbol_sizes[SAVE_SYMBOL]
        decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
        # The supported function ends in one shared epilogue; stop before its
        # literal pool. The hash gate makes branches to other returns impossible.
        epilogue = next((instruction.address for instruction in
                         decoder.disasm(arm.read(start, size), start)
                         if instruction.mnemonic == 'pop' and 'pc' in instruction.op_str), None)
        if epilogue is None:
            raise RuntimeError('Cannot find audited native save completion')
        self.hooks = [arm.uc.hook_add(UC_HOOK_CODE, self._enter, begin=start, end=start),
                      arm.uc.hook_add(UC_HOOK_CODE, self._leave, begin=epilogue, end=epilogue)]

    def _enter(self, uc, address, size, context):
        try:
            if self.active:
                raise RuntimeError('Unexpected nested native save')
            diagnostics = self.arm.diagnostics
            with diagnostics.phase('save_backup', 'snapshot before native save') if diagnostics else nullcontext():
                self.store.before_write()
            self.active = True
            self.save_args = (uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1))
        except BaseException as error:
            self.arm.pending_error = error
            uc.emu_stop()

    def _leave(self, uc, address, size, context):
        try:
            if not self.active:
                raise RuntimeError('Native save completed outside transaction')
            success = uc.reg_read(UC_ARM_REG_R0) == 1
            # The native transaction is complete even if publishing its backup
            # fails. Do not attempt a second after_write during shutdown.
            self.active = False
            diagnostics = self.arm.diagnostics
            try:
                if success and self.on_saved:
                    self.on_saved(*self.save_args)
                with diagnostics.phase('save_backup', 'publish complete native save') if diagnostics else nullcontext():
                    self.store.after_write(success)
            except BaseException:
                self.failed += 1
                raise
            if success:
                self.completed += 1
            else:
                self.failed += 1
        except BaseException as error:
            self.arm.pending_error = error
            uc.emu_stop()

    def abort(self):
        if self.active:
            self.store.after_write(False)
            self.active = False
            self.failed += 1
