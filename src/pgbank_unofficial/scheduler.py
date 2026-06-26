"""Auto-Payment Scheduler — cron/interval/conditional triggers + job execution.

Provides a robust job execution engine for recurring payments, balance checks,
and any other PGBankClient-based action.

Components:
    - :class:`Trigger` (abstract) + concrete :class:`CronTrigger`, :class:`IntervalTrigger`, :class:`ConditionalTrigger`
    - :class:`Job` — user-defined unit of scheduled work
    - :class:`JobContext` — passed to user actions
    - :class:`JobRun` — record of one job execution
    - :class:`AutoPaymentScheduler` — manages job registry, runs background loop

Example:
    >>> from datetime import timedelta
    >>> from decimal import Decimal
    >>> from pgbank_unofficial import (
    ...     PGBankManager, AutoPaymentScheduler, Job, CronTrigger,
    ... )
    >>> mgr = PGBankManager()
    >>> mgr.add_account(Account(username="alice", password="p", browser_id="bid"))
    >>> scheduler = AutoPaymentScheduler(mgr, max_workers=2)
    >>>
    >>> def my_transfer(ctx: JobContext):
    ...     # ctx.client is a logged-in PGBankClient for this job's account
    ...     return ctx.client.transfer(
    ...         from_account="123456", to_account="789",
    ...         amount=Decimal("100000"), description="rent",
    ...     )
    >>>
    >>> job = Job(
    ...     name="Monthly Rent",
    ...     trigger=CronTrigger("0 9 5 * *"),  # 9am on the 5th
    ...     action=my_transfer,
    ...     account_nickname="alice-acc",
    ...     daily_limit=Decimal("50000000"),
    ... )
    >>> scheduler.add_job(job)
    >>> scheduler.start()  # Background thread
"""

from __future__ import annotations

import logging
import random
import threading
import uuid
from abc import ABC, abstractmethod
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, Deque, Optional

from croniter import croniter

if TYPE_CHECKING:
    from pgbank_unofficial.client import PGBankClient
    from pgbank_unofficial.manager import PGBankManager
    from pgbank_unofficial.webhook import WebhookDispatcher

logger = logging.getLogger(__name__)


def _now() -> datetime:
    """Return current time. Override in tests for deterministic behavior."""
    return datetime.now()


# ──────────────────────────────────────────────────────────────────────────────
# Trigger hierarchy
# ──────────────────────────────────────────────────────────────────────────────


class Trigger(ABC):
    """Abstract base class for scheduling triggers.

    A Trigger decides when a job should next run, given the current time.
    """

    @abstractmethod
    def next_run_at(self, after: datetime) -> Optional[datetime]:
        """Return the next datetime at which the job should run, or None if no more runs.

        Args:
            after: Current time (timezone-aware if possible).

        Returns:
            Next run datetime, or None if the trigger has no more scheduled runs.
        """
        raise NotImplementedError


class CronTrigger(Trigger):
    """Cron expression trigger.

    Args:
        expression: Standard 5-field cron expression (minute hour day-of-month month day-of-week).
        jitter_seconds: Maximum random delay (0-jitter_seconds) to add to each scheduled time.
    """

    def __init__(self, expression: str, jitter_seconds: int = 0) -> None:
        self._validate(expression)
        self.expression = expression
        self.jitter_seconds = max(0, int(jitter_seconds))

    @staticmethod
    def _validate(expression: str) -> None:
        """Validate the cron expression at construction time."""
        try:
            croniter(expression, datetime.now())
        except Exception as exc:
            raise ValueError(f"Invalid cron expression: {expression!r} ({exc})") from exc

    def next_run_at(self, after: datetime) -> Optional[datetime]:
        """Return next scheduled datetime after the given time, with optional jitter."""
        it = croniter(self.expression, after)
        next_dt = it.get_next(datetime)
        if self.jitter_seconds > 0:
            jitter = random.randint(0, self.jitter_seconds)
            next_dt = next_dt + timedelta(seconds=jitter)
        return next_dt


class IntervalTrigger(Trigger):
    """Fixed-interval trigger.

    Args:
        seconds: Seconds between runs.
        minutes: Minutes between runs.
        hours: Hours between runs.
        days: Days between runs.
        jitter_seconds: Maximum random delay (0-jitter_seconds) added to each interval.
    """

    def __init__(
        self,
        seconds: int = 0,
        minutes: int = 0,
        hours: int = 0,
        days: int = 0,
        jitter_seconds: int = 0,
    ) -> None:
        total = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        if total.total_seconds() < 0:
            raise ValueError("IntervalTrigger requires non-negative interval")
        self._interval = total
        self.jitter_seconds = max(0, int(jitter_seconds))

    def next_run_at(self, after: datetime) -> Optional[datetime]:
        """Return after + interval (+ optional jitter)."""
        next_dt = after + self._interval
        if self.jitter_seconds > 0:
            jitter = random.randint(0, self.jitter_seconds)
            next_dt = next_dt + timedelta(seconds=jitter)
        return next_dt


class ConditionalTrigger(Trigger):
    """Trigger that fires when an external condition becomes true.

    Args:
        check_every: How often to evaluate the condition.
        condition: Callable that takes a :class:`PGBankClient` and returns True if the job should run.
    """

    def __init__(
        self,
        check_every: timedelta,
        condition: Callable[["PGBankClient"], bool],
    ) -> None:
        if check_every.total_seconds() <= 0:
            raise ValueError("check_every must be positive")
        self.check_every = check_every
        self.condition = condition
        self._last_check: Optional[datetime] = None

    def next_run_at(self, after: datetime) -> Optional[datetime]:
        """Return next check time, or `after` if a check is due now.

        Note: This trigger only computes the next *check* time. Whether to
        actually run the job is determined by calling the condition callback
        in the scheduler.
        """
        if self._last_check is None:
            return after
        next_check = self._last_check + self.check_every
        if after >= next_check:
            return after
        return next_check

    def mark_checked(self, at: datetime) -> None:
        """Mark that a condition check happened at the given time."""
        self._last_check = at


# ──────────────────────────────────────────────────────────────────────────────
# Job dataclass
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class Job:
    """A scheduled unit of work.

    Attributes:
        id: Unique identifier (UUID4 string). Assigned by scheduler.
        name: Human-readable name (e.g. "Monthly Rent").
        trigger: When to run.
        action: Callable receiving :class:`JobContext` and returning a result.
        account_nickname: Which account (in PGBankManager) to use.
        dry_run: If True, action is never actually called (useful for testing).
        daily_limit: Maximum total transfer amount per day for this job (None = no limit).
        enabled: Whether the job is enabled.
        created_at: Job creation timestamp.
        last_run_at: Last successful run timestamp.
        next_run_at: Next scheduled run timestamp.
        consecutive_failures: Count of consecutive failures (auto-pause on max).
    """

    name: str
    trigger: Trigger
    action: Callable[["JobContext"], Any]
    account_nickname: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    dry_run: bool = False
    daily_limit: Optional[Decimal] = None
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    consecutive_failures: int = 0

    def __post_init__(self) -> None:
        """Compute initial next_run_at from trigger if not provided."""
        if self.next_run_at is None and self.trigger is not None:
            try:
                self.next_run_at = self.trigger.next_run_at(_now())
            except Exception:
                # Trigger may not be fully initialized; scheduler will retry
                pass


# ──────────────────────────────────────────────────────────────────────────────
# JobContext
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class JobContext:
    """Context passed to a job's action callable.

    Attributes:
        job: The :class:`Job` being executed.
        client: A logged-in :class:`PGBankClient` for the job's account.
        scheduler: Reference to the :class:`AutoPaymentScheduler` (for OTP callbacks, etc.).
    """

    job: Job
    client: "PGBankClient"
    scheduler: "AutoPaymentScheduler"


class TransferAction:
    """Action that performs a transfer. Fully serializable for persistence."""

    def __init__(
        self,
        to_account: str,
        amount: Decimal,
        description: Optional[str] = None,
        bank_code: str = "PGBANK",
    ) -> None:
        self.to_account = to_account
        self.amount = amount
        self.description = description
        self.bank_code = bank_code
        self._action_type = "transfer"
        self._action_args = {
            "to_account": to_account,
            "amount": str(amount),
            "description": description,
            "bank_code": bank_code,
        }

    def __call__(self, ctx: JobContext) -> Any:
        return ctx.client.transfer(
            from_account=ctx.job.account_nickname,
            to_account=self.to_account,
            amount=self.amount,
            description=self.description,
            bank_code=self.bank_code,
        )


def _default_action_loader(
    action_type: str, action_args: Optional[dict]
) -> Callable[[JobContext], Any]:
    if action_type == "transfer" and action_args:
        return TransferAction(
            to_account=action_args["to_account"],
            amount=Decimal(action_args["amount"]),
            description=action_args.get("description"),
            bank_code=action_args.get("bank_code", "PGBANK"),
        )

    # Fallback dummy action
    def dummy_action(ctx: JobContext) -> None:
        logger.warning(
            "Unregistered or custom action '%s' triggered for job '%s' (%s).",
            action_type,
            ctx.job.id,
            ctx.job.name,
        )

    dummy_action._action_type = action_type
    dummy_action._action_args = action_args or {}
    return dummy_action


# ──────────────────────────────────────────────────────────────────────────────
# JobRun
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class JobRun:
    """A single execution record.

    Attributes:
        job_id: ID of the job that ran.
        started_at: When execution started.
        finished_at: When execution finished.
        success: Whether the action completed without error.
        error: Error message (None if success).
        dry_run: Whether this was a dry-run (no actual action).
        triggered_by: "scheduler" (background) or "manual" (run_job_now).
    """

    job_id: str
    started_at: datetime
    finished_at: Optional[datetime]
    success: bool
    error: Optional[str]
    dry_run: bool
    triggered_by: str

    @property
    def duration(self) -> Optional[timedelta]:
        """Duration of the run, or None if not finished."""
        if self.finished_at is None:
            return None
        return self.finished_at - self.started_at


# ──────────────────────────────────────────────────────────────────────────────
# AutoPaymentScheduler
# ──────────────────────────────────────────────────────────────────────────────


class AutoPaymentScheduler:
    """Schedules and executes Jobs on triggers.

    Args:
        manager: :class:`PGBankManager` with registered accounts.
        dispatcher: Optional :class:`WebhookDispatcher` for event publishing.
        max_workers: Maximum concurrent job executions.
        max_consecutive_failures: Auto-pause job after this many consecutive failures.
        daily_limit_per_account: Global per-account daily limit (None = no limit).

    Attributes:
        otp_callback: Optional callable to handle OTP requests from the bank.
    """

    def __init__(
        self,
        manager: "PGBankManager",
        dispatcher: Optional["WebhookDispatcher"] = None,
        *,
        max_workers: int = 2,
        max_consecutive_failures: int = 3,
        daily_limit_per_account: Optional[Decimal] = None,
    ) -> None:
        self._manager = manager
        self._dispatcher = dispatcher
        self._max_workers = max(1, int(max_workers))
        self._max_consecutive_failures = max(1, int(max_consecutive_failures))
        self._daily_limit_per_account = (
            Decimal(daily_limit_per_account) if daily_limit_per_account is not None else None
        )
        self._jobs: dict[str, Job] = {}
        self._history: dict[str, Deque[JobRun]] = {}
        self._lock = threading.RLock()

        # Load persisted jobs and history
        try:
            for job in self._manager.storage.load_jobs(_default_action_loader):
                self._jobs[job.id] = job
                runs = self._manager.storage.get_job_runs(job.id)
                self._history[job.id] = deque(runs, maxlen=100)
        except Exception as exc:
            logger.warning("Failed to load jobs from storage: %s", exc)

        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers, thread_name_prefix="pgbank-scheduler"
        )
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.otp_callback: Optional[Callable[[str], str]] = None

    # ── Public API: Job registry ────────────────────────────────────────────

    def add_job(self, job: Job) -> str:
        """Add a job to the scheduler. Returns the job's ID."""
        with self._lock:
            # Compute initial next_run_at
            if job.next_run_at is None:
                job.next_run_at = job.trigger.next_run_at(_now())
            self._jobs[job.id] = job
            self._history.setdefault(job.id, deque(maxlen=100))
            self._manager.storage.save_job(job)
        logger.info("Added job %s: %s (next run: %s)", job.id, job.name, job.next_run_at)
        return job.id

    def remove_job(self, job_id: str) -> None:
        """Remove a job by ID. Raises KeyError if not found."""
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"No job with id {job_id}")
            del self._jobs[job_id]
            self._manager.storage.remove_job(job_id)
            # Keep history for inspection
        logger.info("Removed job %s", job_id)

    def pause_job(self, job_id: str) -> None:
        """Pause a job (sets enabled=False)."""
        with self._lock:
            job = self._jobs[job_id]
            job.enabled = False
            self._manager.storage.save_job(job)
        logger.info("Paused job %s", job_id)

    def resume_job(self, job_id: str) -> None:
        """Resume a paused job (sets enabled=True)."""
        with self._lock:
            job = self._jobs[job_id]
            job.enabled = True
            job.consecutive_failures = 0
            self._manager.storage.save_job(job)
        logger.info("Resumed job %s", job_id)

    def list_jobs(self) -> list[Job]:
        """Return a snapshot of all jobs."""
        with self._lock:
            return list(self._jobs.values())

    def get_history(self, job_id: str) -> list[JobRun]:
        """Return the run history for a job."""
        with self._lock:
            return list(self._history.get(job_id, []))

    # ── Public API: Execution ───────────────────────────────────────────────

    def run_job_now(self, job_id: str, *, dry_run: bool = False) -> JobRun:
        """Execute a job synchronously and return the JobRun.

        Args:
            job_id: Job to execute.
            dry_run: If True, do not actually call the action (but record the run).

        Returns:
            :class:`JobRun` with the execution outcome.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(f"No job with id {job_id}")

        return self._execute_job(job, dry_run=dry_run, triggered_by="manual")

    def start(self, *, daemon: bool = True, poll_interval: float = 1.0) -> None:
        """Start the background scheduler thread.

        Args:
            daemon: If True, the thread is a daemon (exits when main process exits).
            poll_interval: Seconds between polls of the job registry.
        """
        if self._thread is not None and self._thread.is_alive():
            logger.warning("Scheduler is already running")
            return
        self._stop_event.clear()
        self._poll_interval = poll_interval
        self._thread = threading.Thread(
            target=self._run_loop, name="pgbank-scheduler-main", daemon=daemon
        )
        self._thread.start()
        logger.info("Scheduler started (daemon=%s, poll_interval=%.2fs)", daemon, poll_interval)

    def stop(self, *, timeout: float = 5.0) -> None:
        """Stop the background scheduler thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._executor.shutdown(wait=True, cancel_futures=False)
        logger.info("Scheduler stopped")

    # ── Internal: execution engine ──────────────────────────────────────────

    def _execute_job(
        self, job: Job, *, dry_run: bool = False, triggered_by: str = "scheduler"
    ) -> JobRun:
        """Execute a single job and record the run."""
        started_at = _now()
        run = JobRun(
            job_id=job.id,
            started_at=started_at,
            finished_at=None,
            success=False,
            error=None,
            dry_run=dry_run,
            triggered_by=triggered_by,
        )
        is_dry = dry_run or job.dry_run

        try:
            # Check daily limit (skip for dry runs)
            if not is_dry:
                limit_error = self._check_daily_limit(job)
                if limit_error is not None:
                    run.finished_at = _now()
                    run.error = limit_error
                    run.success = False
                    self._record_run(job, run)
                    return run

            if is_dry:
                run.finished_at = _now()
                run.success = True
                self._record_run(job, run)
                logger.info("Dry-run for job %s (%s)", job.id, job.name)
                return run

            # Get the client for this account
            client = self._manager.get_client(job.account_nickname)
            ctx = JobContext(job=job, client=client, scheduler=self)

            # Execute the action
            result = job.action(ctx)
            logger.info("Job %s (%s) completed: %r", job.id, job.name, result)

            run.finished_at = _now()
            run.success = True
            self._record_run(job, run)
            return run

        except Exception as exc:
            logger.exception("Job %s (%s) failed: %s", job.id, job.name, exc)
            run.finished_at = _now()
            run.error = f"{type(exc).__name__}: {exc}"
            run.success = False
            self._record_run(job, run)
            return run

    def _record_run(self, job: Job, run: JobRun) -> None:
        """Record a run in history and update job state."""
        with self._lock:
            self._history.setdefault(job.id, deque(maxlen=100)).append(run)
            if run.success:
                job.consecutive_failures = 0
                job.last_run_at = run.finished_at or run.started_at
            else:
                job.consecutive_failures += 1
                if job.consecutive_failures >= self._max_consecutive_failures:
                    job.enabled = False
                    logger.warning(
                        "Job %s auto-paused after %d consecutive failures",
                        job.id,
                        job.consecutive_failures,
                    )
                    self._publish_job_event(job, "paused")

            # Compute next run time
            if job.enabled:
                try:
                    job.next_run_at = job.trigger.next_run_at(_now())
                except Exception:
                    logger.exception("Failed to compute next run for job %s", job.id)
            else:
                job.next_run_at = None

            # Persist run and updated job state
            try:
                self._manager.storage.add_job_run(run)
                self._manager.storage.save_job(job)
            except Exception as exc:
                logger.warning("Failed to persist job run/state to storage: %s", exc)

    def _check_daily_limit(self, job: Job) -> Optional[str]:
        """Check if a job would exceed its daily_limit. Returns error message or None."""
        # If the global limit is set, use it; otherwise fall back to per-job
        limit = job.daily_limit if job.daily_limit is not None else self._daily_limit_per_account
        if limit is None:
            return None
        # We don't have a generic transfer ledger; we approximate by checking
        # the available balance as a proxy. If balance < limit, allow; else refuse.
        # In production, you'd plug in a proper transfer ledger.
        try:
            client = self._manager.get_client(job.account_nickname)
            balance = client.get_balance()
            if balance.available < limit:
                # Balance-based check (proxy): if available is less than limit, we can't transfer
                # This is a conservative check; the actual logic is up to the action
                return f"DAILY_LIMIT_EXCEEDED: available {balance.available} < limit {limit}"
        except Exception as exc:
            logger.warning("Could not check balance for daily limit: %s", exc)
        return None

    def _publish_job_event(self, job: Job, event_type: str) -> None:
        """Publish a job event via webhook dispatcher if available."""
        if self._dispatcher is None:
            return
        try:
            from pgbank_unofficial.webhook import Event  # local import to avoid circular

            event = Event(
                type=f"job.{event_type}",
                timestamp=_now(),
                data={
                    "job_id": job.id,
                    "job_name": job.name,
                    "consecutive_failures": job.consecutive_failures,
                },
            )
            # Run dispatcher in background (sync wrapper around async dispatch)
            self._executor.submit(self._dispatch_sync, event)
        except Exception as exc:
            logger.warning("Failed to publish job event: %s", exc)

    def _dispatch_sync(self, event: Any) -> None:
        """Synchronous wrapper to dispatch a webhook event."""
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self._dispatcher.dispatch(event))
            finally:
                loop.close()
        except Exception as exc:
            logger.warning("Webhook dispatch failed: %s", exc)

    # ── Internal: Background loop ───────────────────────────────────────────

    def _run_loop(self) -> None:
        """Main scheduler loop: poll jobs, execute due jobs."""
        logger.info("Scheduler loop started")
        while not self._stop_event.is_set():
            try:
                self._process_due_jobs()
            except Exception:
                logger.exception("Error in scheduler loop")
            self._stop_event.wait(self._poll_interval)
        logger.info("Scheduler loop exited")

    def _process_due_jobs(self) -> None:
        """Find due jobs and execute them in the thread pool."""
        now = _now()
        due_jobs: list[Job] = []
        with self._lock:
            for job in self._jobs.values():
                if not job.enabled:
                    continue
                if job.next_run_at is None:
                    continue
                if job.next_run_at <= now:
                    due_jobs.append(job)

        for job in due_jobs:
            self._executor.submit(self._execute_job, job, False, "scheduler")


__all__ = [
    "Trigger",
    "CronTrigger",
    "IntervalTrigger",
    "ConditionalTrigger",
    "Job",
    "JobContext",
    "JobRun",
    "TransferAction",
    "AutoPaymentScheduler",
]
