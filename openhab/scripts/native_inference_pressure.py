"""Production inference admission from RAM and kernel worker isolation.

Host swap residency and traffic belong to the host, not this zero-swap worker.
Use the common publication monitor for available RAM, sustained pressure, hard
worker limits and new OOM events. Development fitting policy is independent.
"""
from household_cycle_pressure import PublicationHeadroom


class NativeInferenceHeadroom(PublicationHeadroom):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.refused = False

    def check(self):
        if self.refused:
            raise ValueError('native inference headroom previously refused')
        try:
            super().check()
        except (OSError, UnicodeError, ValueError, OverflowError):
            self.refused = True
            raise

    def preflight(self):
        # Hard isolation is already enforced by the kernel. Admit from current
        # RAM/pressure; subsequent checks monitor the whole invocation.
        self.check()
