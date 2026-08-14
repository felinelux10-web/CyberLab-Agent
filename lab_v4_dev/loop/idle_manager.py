# CyberLab Agent v4.0
# loop/idle_manager.py

import time
from lab_v4_dev.core.config import HARD_LIMITS

class IdleManager:

    def __init__(self):
        self.idle_count = 0

    def sleep(self):
        time.sleep(HARD_LIMITS["idle_sleep_sec"])
        self.idle_count += 1

    def short_sleep(self):
        time.sleep(1)

    def reset(self):
        self.idle_count = 0

    def is_long_idle(self) -> bool:
        return self.idle_count > 12
