import time
from utilities.common.common_utility import debug_print

debug_print("Starting startup timer...", color="cyan")

PROCESS_BOOT_TS = time.perf_counter()
STARTUP_TIME_MS = None
