# utilities/helpers/task_manager/manager.py
#
# Revision notes:
#
#  1.  COMPLETED TASK PRUNING — TTL-based prune runs inside the scheduler
#      loop every cycle. Completed / failed / cancelled one-off tasks are
#      removed after COMPLETED_TASK_TTL seconds (default 300s). Recurring
#      tasks are never pruned.
#
#  2.  _log FIXED — color/tag always passed so log output is
#      level-distinguishable regardless of debug_print availability.
#
#  3.  add_recurring — convenience method for periodic background jobs.
#
#  4.  HEALTH SUBSYSTEM — HealthStatus updated on every scheduler tick.
#      is_healthy() returns False if scheduler has stalled or never started.
#
#  5.  LOCK-FREE TASK DISPATCH (root cause of the startup stall) —
#      Previously, add_task() called _start_task_async() while still
#      holding self._lock. _start_task_async() calls loop.create_task(),
#      which is synchronous and safe, but the await inside add_task kept
#      the lock held for the full duration. Meanwhile the scheduler loop
#      was blocked trying to acquire that same lock, causing the
#      "Scheduler loop started" log to appear late and startup to stall.
#      Fix: the lock is held only for the dict write. Task dispatch and
#      condition notification happen after the lock is released.
#
#  6.  NO asyncio.Condition FOR WAKEUP — asyncio.Condition.wait() is
#      notoriously tricky: it releases the underlying lock, but acquiring
#      the condition itself can contend with anyone else also trying to
#      notify. Replaced with a plain asyncio.Event that is set by
#      add_task() to wake the scheduler and immediately cleared by the
#      scheduler at the top of its loop. This eliminates the entire
#      class of condition-lock contention.
#
#  7.  _start_task_async IS NOW LOCK-FREE — it only calls
#      loop.create_task() (thread-safe, no await) and mutates the
#      ScheduledTask fields (single-writer: either the scheduler loop or
#      add_task, never both at the same time after fix #5). No lock needed.
#
#  8.  asyncio.wait_for REMOVED FROM SLEEP — asyncio.wait_for creates a
#      new internal Task to enforce the timeout. Using it on an Event.wait()
#      every scheduler tick creates and destroys a Task every 60 seconds
#      under idle conditions. Replaced with asyncio.wait() with a timeout
#      on a shield, or simply asyncio.sleep with an Event.wait() race via
#      asyncio.wait(). Simplest correct pattern: Event.wait() with a
#      separate sleep Task and asyncio.wait(FIRST_COMPLETED).

import asyncio
import concurrent.futures
import functools
import logging
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
import os

logger = logging.getLogger("task_manager")

try:
    from utilities.common.common_utility import debug_print
except Exception:
    debug_print = None  # type: ignore[assignment]

# ── Tunables ─────────────────────────────────────────────────────────────────

# How long to keep completed/failed/cancelled one-off tasks before pruning.
COMPLETED_TASK_TTL: float = float(os.getenv("TASK_MANAGER_COMPLETED_TTL", "300"))

# If the scheduler loop hasn't heartbeated in this many seconds, is_healthy()
# returns False.
SCHEDULER_STALL_THRESHOLD: float = float(
    os.getenv("TASK_MANAGER_STALL_THRESHOLD", "120")
)

# Maximum time the scheduler sleeps between ticks when there's nothing due.
SCHEDULER_MAX_SLEEP: float = float(os.getenv("TASK_MANAGER_MAX_SLEEP", "60"))


# ── Internal helpers ──────────────────────────────────────────────────────────

def _log(msg: str, *args: Any, level: str = "info") -> None:
    color_map = {"debug": "cyan", "warning": "orange", "error": "red", "info": "yellow"}
    color = color_map.get(level, "yellow")
    if debug_print is not None:
        try:
            debug_print(msg % args if args else msg, color=color, tag="TASKMGR")
            return
        except Exception:
            pass
    getattr(
        logger,
        level if level in ("debug", "warning", "error", "info") else "info",
    )(msg, *args)


# ── Public types ──────────────────────────────────────────────────────────────

class TaskType(Enum):
    ASYNC  = "async"
    THREAD = "thread"


class TaskState(Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


@dataclass
class HealthStatus:
    """
    Snapshot of the TaskManager's operational health.

    is_healthy              — True if scheduler is running and recently ticked.
    last_heartbeat          — UTC ISO-8601 of last scheduler tick; None if never started.
    stall_threshold_seconds — seconds without a heartbeat before is_healthy → False.
    last_error              — most-recent task-level error string, if any.
    task_counts             — per-state counts of all registered tasks.
    total_tasks             — total tasks in registry (post-prune).
    uptime_seconds          — seconds since start() was called, or None.
    scheduler_running       — raw _running flag.
    """
    is_healthy:               bool
    last_heartbeat:           Optional[str]    # ISO-8601 UTC
    stall_threshold_seconds:  float
    last_error:               Optional[str]
    task_counts:              Dict[str, int]
    total_tasks:              int
    uptime_seconds:           Optional[float]
    scheduler_running:        bool


@dataclass
class ScheduledTask:
    id:                str
    func:              Callable[..., Any]
    args:              Tuple           = field(default_factory=tuple)
    kwargs:            Dict[str, Any]  = field(default_factory=dict)
    task_type:         TaskType        = TaskType.ASYNC
    run_once_and_forget: bool          = False
    run_at:            Optional[datetime] = None
    interval:          Optional[float]    = None
    name:              Optional[str]      = None
    max_retries:       int             = 0

    # ── Runtime state (mutated by scheduler / runner only) ────────────────────
    state:       TaskState             = field(default=TaskState.PENDING)
    last_error:  Optional[str]         = None
    attempts:    int                   = 0
    next_run:    Optional[datetime]    = None
    finished_at: Optional[datetime]    = field(default=None)
    _internal_task_ref: Optional[asyncio.Task] = field(
        default=None, repr=False, compare=False
    )
    debug: bool = True

    def to_dict(self) -> dict:
        return {
            "id":                  self.id,
            "name":                self.name,
            "task_type":           self.task_type.value,
            "run_once_and_forget": self.run_once_and_forget,
            "run_at":              self.run_at.isoformat() if self.run_at else None,
            "interval":            self.interval,
            "state":               self.state.value,
            "attempts":            self.attempts,
            "next_run":            self.next_run.isoformat() if self.next_run else None,
            "last_error":          self.last_error,
            "max_retries":         self.max_retries,
            "finished_at":         self.finished_at.isoformat() if self.finished_at else None,
        }


# ── TaskManager ───────────────────────────────────────────────────────────────

class TaskManager:
    """
    Async-native task manager for FastAPI / asyncio applications.

    Usage
    ─────
    One-off immediate:  add_task(..., run_once_and_forget=True)
    Scheduled once:     add_task(..., run_at=<datetime | seconds>)
    Recurring:          add_task(..., interval=<seconds>)  or  add_recurring(...)

    Health:             is_healthy() / get_health_status()

    Design invariants
    ─────────────────
    • self._lock guards only self._tasks (the registry dict). It is held for
      the minimum possible time — dict reads/writes only, never across awaits.

    • Task dispatch (_start_task_async) never holds self._lock. It only calls
      loop.create_task() which is synchronous and reentrant-safe.

    • Scheduler wakeup uses a plain asyncio.Event (_wakeup_event) instead of
      asyncio.Condition, eliminating condition-lock contention entirely.

    • The scheduler sleep is implemented as a race between a sleep Task and
      _wakeup_event.wait(), using asyncio.wait(FIRST_COMPLETED) — no
      asyncio.wait_for, no hidden Task-per-tick overhead.
    """

    def __init__(self, max_workers: int = 8) -> None:
        self._executor     = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._loop:        Optional[asyncio.AbstractEventLoop] = None
        self._tasks:       Dict[str, ScheduledTask]            = {}
        self._bg_tasks:    Set[asyncio.Task]                   = set()
        self._scheduler_task: Optional[asyncio.Task]           = None
        self._running      = False
        self._lock         = asyncio.Lock()

        # Replaces asyncio.Condition — set by add_task, cleared by scheduler.
        self._wakeup_event = asyncio.Event()

        # Health
        self._started_at:          Optional[datetime] = None
        self._last_heartbeat:      Optional[datetime] = None
        self._last_recorded_error: Optional[str]      = None

        _log("TaskManager initialized (max_workers=%s)", max_workers, level="debug")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._running:
            return
        self._loop       = asyncio.get_running_loop()
        self._running    = True
        self._started_at = datetime.now(timezone.utc)
        self._scheduler_task = self._loop.create_task(
            self._scheduler_loop(), name="taskmgr-scheduler"
        )
        _log("TaskManager started", level="info")

    async def shutdown(
        self,
        wait_for_background: bool = True,
        bg_wait_timeout:     float = 10.0,
    ) -> None:
        if not self._running:
            return

        _log("TaskManager shutting down (wait=%s)...", wait_for_background, level="info")

        self._running = False
        self._wakeup_event.set()  # wake the scheduler so it can exit cleanly

        if self._scheduler_task:
            try:
                await asyncio.wait_for(self._scheduler_task, timeout=2.0)
            except Exception:
                self._scheduler_task.cancel()
                try:
                    await self._scheduler_task
                except Exception:
                    pass

        if self._bg_tasks:
            to_wait = list(self._bg_tasks)
            if wait_for_background:
                _log(
                    "Waiting up to %ss for %s bg tasks...",
                    bg_wait_timeout, len(to_wait),
                    level="info",
                )
                for t in to_wait:
                    if not t.done():
                        t.cancel()
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*to_wait, return_exceptions=True),
                        timeout=bg_wait_timeout,
                    )
                except Exception:
                    _log("Timeout waiting for bg tasks", level="warning")
            else:
                for t in to_wait:
                    if not t.done():
                        t.cancel()

        try:
            self._executor.shutdown(wait=False)
        except Exception:
            pass

        self._bg_tasks.clear()
        self._scheduler_task = None
        self._loop           = None
        _log("TaskManager shutdown complete", level="info")

    # ── Scheduler loop ────────────────────────────────────────────────────────

    async def _scheduler_loop(self) -> None:
        _log("Scheduler loop started", level="debug")

        while self._running:
            # ── Heartbeat ─────────────────────────────────────────────────────
            self._last_heartbeat = datetime.now(timezone.utc)
            now = self._last_heartbeat

            # Clear wakeup event at the top of every tick so any set() that
            # arrives while we're processing tasks won't be lost.
            self._wakeup_event.clear()

            # ── Collect due tasks (lock held for read only) ────────────────────
            next_wakeup: Optional[datetime] = None
            due: List[ScheduledTask] = []

            async with self._lock:
                for t in self._tasks.values():
                    # Initialise next_run on first encounter
                    if t.next_run is None:
                        if t.run_at is not None:
                            t.next_run = t.run_at.astimezone(timezone.utc)
                        elif t.interval is not None:
                            t.next_run = now  # start immediately

                    if t.next_run is not None:
                        if t.next_run <= now:
                            due.append(t)
                        elif next_wakeup is None or t.next_run < next_wakeup:
                            next_wakeup = t.next_run

            # ── Dispatch due tasks (NO lock held) ─────────────────────────────
            for scheduled in due:
                if scheduled.interval:
                    # Update next_run BEFORE dispatch so the wakeup recompute
                    # below can track the nearest upcoming recurring tick.
                    updated_next = (
                        now + timedelta(seconds=scheduled.interval)
                    ).astimezone(timezone.utc)
                    scheduled.next_run = updated_next
                    if next_wakeup is None or updated_next < next_wakeup:
                        next_wakeup = updated_next
                else:
                    scheduled.next_run = None

                self._start_task_async(scheduled)   # synchronous create_task, no await

            # ── Prune stale completed tasks ───────────────────────────────────
            await self._prune_completed()

            if not self._running:
                break

            # ── Sleep until next due time or wakeup signal ────────────────────
            if next_wakeup is not None:
                delta = (next_wakeup - datetime.now(timezone.utc)).total_seconds()
                sleep_seconds = max(0.0, min(delta, SCHEDULER_MAX_SLEEP))
            else:
                sleep_seconds = SCHEDULER_MAX_SLEEP

            if sleep_seconds > 0:
                sleep_task  = asyncio.ensure_future(asyncio.sleep(sleep_seconds))
                wakeup_task = asyncio.ensure_future(self._wakeup_event.wait())
                try:
                    done, pending = await asyncio.wait(
                        {sleep_task, wakeup_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                finally:
                    for t in (sleep_task, wakeup_task):
                        if not t.done():
                            t.cancel()

        _log("Scheduler loop exiting", level="debug")

    # ── Pruning ───────────────────────────────────────────────────────────────

    async def _prune_completed(self) -> None:
        """Remove terminal one-off tasks older than COMPLETED_TASK_TTL."""
        terminal = {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}
        cutoff   = datetime.now(timezone.utc) - timedelta(seconds=COMPLETED_TASK_TTL)
        to_prune: List[str] = []

        async with self._lock:
            for tid, t in self._tasks.items():
                if (
                    t.state      in terminal
                    and t.interval  is None      # never prune recurring tasks
                    and t.finished_at is not None
                    and t.finished_at < cutoff
                ):
                    to_prune.append(tid)
            for tid in to_prune:
                del self._tasks[tid]

        if to_prune:
            _log("Pruned %s completed tasks from registry", len(to_prune), level="debug")

    # ── Task dispatch ─────────────────────────────────────────────────────────

    def _start_task_async(self, scheduled: ScheduledTask) -> Optional[asyncio.Task]:
        """
        Dispatch `scheduled` as a background asyncio.Task.

        Deliberately synchronous — only calls loop.create_task() which is
        thread-safe and never blocks. Must NOT hold self._lock when called.
        """
        if scheduled.state == TaskState.RUNNING:
            return None
        if self._loop is None:
            return None

        async def _runner() -> None:
            scheduled.state    = TaskState.RUNNING
            scheduled.attempts += 1
            try:
                if scheduled.task_type == TaskType.ASYNC:
                    coro = scheduled.func(*scheduled.args, **scheduled.kwargs)
                    if asyncio.iscoroutine(coro):
                        await coro
                else:
                    fn = functools.partial(
                        scheduled.func, *scheduled.args, **scheduled.kwargs
                    )
                    await asyncio.get_running_loop().run_in_executor(
                        self._executor, fn
                    )

                scheduled.last_error  = None
                scheduled.finished_at = datetime.now(timezone.utc)
                # Recurring tasks go back to PENDING so the scheduler can
                # re-dispatch them on the next interval tick.
                scheduled.state = (
                    TaskState.PENDING
                    if scheduled.interval is not None
                    else TaskState.COMPLETED
                )

            except asyncio.CancelledError:
                scheduled.state       = TaskState.CANCELLED
                scheduled.finished_at = datetime.now(timezone.utc)
                raise

            except Exception as exc:
                scheduled.last_error  = "".join(
                    traceback.format_exception_only(type(exc), exc)
                ).strip()
                self._last_recorded_error = scheduled.last_error
                scheduled.finished_at     = datetime.now(timezone.utc)

                if scheduled.debug:
                    _log(
                        "Task %s (name=%s) failed: %s",
                        scheduled.id, scheduled.name, scheduled.last_error,
                        level="error",
                    )

                if scheduled.attempts <= scheduled.max_retries:
                    # Exponential back-off retry — wake scheduler to pick it up.
                    scheduled.next_run = datetime.now(timezone.utc) + timedelta(
                        seconds=2 ** scheduled.attempts
                    )
                    scheduled.state = TaskState.PENDING
                    self._wakeup_event.set()
                else:
                    # Max retries exhausted. Recurring tasks stay alive on their
                    # normal interval; one-offs go terminal.
                    scheduled.state = (
                        TaskState.PENDING
                        if scheduled.interval is not None
                        else TaskState.FAILED
                    )

        task = self._loop.create_task(_runner(), name=f"taskmgr-run-{scheduled.id}")
        scheduled._internal_task_ref = task

        def _on_done(fut: asyncio.Future) -> None:
            self._bg_tasks.discard(fut)

        task.add_done_callback(_on_done)
        self._bg_tasks.add(task)

        if scheduled.debug:
            _log(
                "Started task %s (name=%s)", scheduled.id, scheduled.name,
                level="debug",
            )
        return task

    # ── Health API ────────────────────────────────────────────────────────────

    def is_healthy(self) -> bool:
        """
        True iff:
          • start() has been called
          • the scheduler loop is still alive
          • last heartbeat was within SCHEDULER_STALL_THRESHOLD seconds
        """
        if not self._running or self._last_heartbeat is None:
            return False
        age = (datetime.now(timezone.utc) - self._last_heartbeat).total_seconds()
        return age < SCHEDULER_STALL_THRESHOLD

    def get_health_status(self) -> HealthStatus:
        counts: Dict[str, int] = {s.value: 0 for s in TaskState}
        for t in self._tasks.values():
            counts[t.state.value] += 1

        uptime: Optional[float] = None
        if self._started_at:
            uptime = (datetime.now(timezone.utc) - self._started_at).total_seconds()

        return HealthStatus(
            is_healthy=self.is_healthy(),
            last_heartbeat=(
                self._last_heartbeat.isoformat() if self._last_heartbeat else None
            ),
            stall_threshold_seconds=SCHEDULER_STALL_THRESHOLD,
            last_error=self._last_recorded_error,
            task_counts=counts,
            total_tasks=len(self._tasks),
            uptime_seconds=uptime,
            scheduler_running=self._running,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    async def add_task(
        self,
        func:                Callable[..., Any],
        args:                Optional[Tuple]                  = None,
        kwargs:              Optional[Dict[str, Any]]         = None,
        task_type:           TaskType                         = TaskType.ASYNC,
        run_once_and_forget: bool                             = False,
        run_at:              Optional[Union[datetime, float]] = None,
        interval:            Optional[float]                  = None,
        task_id:             Optional[str]                    = None,
        name:                Optional[str]                    = None,
        max_retries:         int                              = 0,
        debug:               bool                             = True,
    ) -> ScheduledTask:
        args   = args   or ()
        kwargs = kwargs or {}

        if task_id is None:
            task_id = str(uuid.uuid4())

        if run_at is not None:
            if isinstance(run_at, (int, float)):
                run_at = datetime.now(timezone.utc) + timedelta(seconds=float(run_at))
            elif isinstance(run_at, datetime):
                run_at = (
                    run_at.replace(tzinfo=timezone.utc)
                    if run_at.tzinfo is None
                    else run_at.astimezone(timezone.utc)
                )
            else:
                raise ValueError("run_at must be a datetime or a number of seconds")

        st = ScheduledTask(
            id=task_id,
            func=func,
            args=tuple(args),
            kwargs=dict(kwargs),
            task_type=task_type,
            run_once_and_forget=run_once_and_forget,
            run_at=run_at,
            interval=interval,
            name=name,
            max_retries=max_retries,
            debug=debug,
        )

        # ── FIX #5: hold the lock ONLY for the dict write ─────────────────────
        dispatch_now = False
        async with self._lock:
            self._tasks[st.id] = st
            if run_once_and_forget and run_at is None:
                if not self._running or self._loop is None:
                    raise RuntimeError(
                        "TaskManager must be started before scheduling "
                        "run_once_and_forget tasks."
                    )
                dispatch_now = True

        # ── Lock released — dispatch or wake scheduler ─────────────────────────
        if dispatch_now:
            self._start_task_async(st)      # synchronous, no lock needed
        else:
            self._wakeup_event.set()        # wake scheduler to re-evaluate

        _log(
            "Added task %s name=%s interval=%s once=%s",
            st.id, st.name, st.interval, st.run_once_and_forget,
            level="debug",
        )
        return st

    async def cancel_task(self, task_id: str) -> bool:
        async with self._lock:
            st = self._tasks.get(task_id)
            if not st:
                return False
            if st._internal_task_ref and not st._internal_task_ref.done():
                st._internal_task_ref.cancel()
            st.state       = TaskState.CANCELLED
            st.next_run    = None
            st.interval    = None
            st.finished_at = datetime.now(timezone.utc)
        return True

    def status(self) -> Dict[str, Any]:
        return {tid: t.to_dict() for tid, t in self._tasks.items()}

    # ── Convenience helpers ───────────────────────────────────────────────────

    async def schedule_once(
        self, func: Callable, delay: float = 0.0, **kwargs: Any
    ) -> ScheduledTask:
        """Schedule a one-off run in `delay` seconds (0 = immediate)."""
        return await self.add_task(
            func=func, run_at=delay, run_once_and_forget=True, **kwargs
        )

    async def schedule_at(
        self, func: Callable, at: datetime, **kwargs: Any
    ) -> ScheduledTask:
        """Schedule a one-off run at a specific UTC datetime."""
        return await self.add_task(
            func=func, run_at=at, run_once_and_forget=False, **kwargs
        )

    async def schedule_interval(
        self,
        func:       Callable,
        interval:   float,
        start_in:   Optional[float] = None,
        **kwargs:   Any,
    ) -> ScheduledTask:
        """Schedule a recurring task every `interval` seconds."""
        return await self.add_task(
            func=func,
            interval=interval,
            run_at=start_in,
            run_once_and_forget=False,
            **kwargs,
        )

    async def add_recurring(
        self,
        func:             Callable,
        interval_seconds: float,
        name:             Optional[str] = None,
        start_immediately: bool         = False,
        debug:            bool          = True,
    ) -> ScheduledTask:
        """Convenience method for recurring background jobs."""
        return await self.add_task(
            func=func,
            interval=interval_seconds,
            name=name,
            run_at=0.0 if start_immediately else None,
            debug=debug,
        )


# ── FastAPI integration ───────────────────────────────────────────────────────

def attach_to_app(
    app,
    manager:     Optional[TaskManager] = None,
    max_workers: int                   = 8,
) -> TaskManager:
    if manager is None:
        manager = TaskManager(max_workers=max_workers)

    @app.on_event("startup")
    async def _start_mgr() -> None:
        await manager.start()

    @app.on_event("shutdown")
    async def _stop_mgr() -> None:
        await manager.shutdown(wait_for_background=True, bg_wait_timeout=10.0)

    setattr(app, "task_manager", manager)
    return manager


# ── Module-level singleton ────────────────────────────────────────────────────

task_manager = TaskManager()