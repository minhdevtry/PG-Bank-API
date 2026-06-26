"""Session storage backends for PGBank Unofficial Client."""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from contextlib import closing
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from pgbank_unofficial.models import Account
    from pgbank_unofficial.scheduler import Job, JobRun


class BaseSessionStorage(ABC):
    """Base interface for synchronous session storage backends."""

    @abstractmethod
    def save_session(self, username: str, data: dict) -> None:
        """Save session data for a given username."""
        pass

    @abstractmethod
    def load_session(self, username: str) -> Optional[dict]:
        """Load session data for a given username. Returns None if not found."""
        pass

    @abstractmethod
    def delete_session(self, username: str) -> None:
        """Delete session data for a given username."""
        pass


class BaseAsyncSessionStorage(ABC):
    """Base interface for asynchronous session storage backends."""

    @abstractmethod
    async def save_session(self, username: str, data: dict) -> None:
        """Save session data for a given username."""
        pass

    @abstractmethod
    async def load_session(self, username: str) -> Optional[dict]:
        """Load session data for a given username. Returns None if not found."""
        pass

    @abstractmethod
    async def delete_session(self, username: str) -> None:
        """Delete session data for a given username."""
        pass


class FileSessionStorage(BaseSessionStorage):
    """Default file-based session storage (JSON format) for a single file path."""

    def __init__(self, session_path: str | Path) -> None:
        self.session_path = Path(session_path)

    def save_session(self, username: str, data: dict) -> None:
        try:
            self.session_path.parent.mkdir(parents=True, exist_ok=True)
            self.session_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as e:
            raise RuntimeError(f"Failed to save session to {self.session_path}: {e}") from e

    def load_session(self, username: str) -> Optional[dict]:
        if not self.session_path.exists():
            return None
        try:
            return json.loads(self.session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def delete_session(self, username: str) -> None:
        if self.session_path.exists():
            try:
                self.session_path.unlink()
            except OSError:
                pass


class DirSessionStorage(BaseSessionStorage):
    """File-based session storage that saves each account to a separate file in a directory."""

    def __init__(self, sessions_dir: str | Path) -> None:
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, username: str) -> Path:
        # Sanitize username/nickname for safe filename
        safe_name = "".join(c for c in username if c.isalnum() or c in ("-", "_"))
        return self.sessions_dir / f"{safe_name}.json"

    def save_session(self, username: str, data: dict) -> None:
        path = self._get_path(username)
        try:
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as e:
            raise RuntimeError(f"Failed to save session to {path}: {e}") from e

    def load_session(self, username: str) -> Optional[dict]:
        path = self._get_path(username)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def delete_session(self, username: str) -> None:
        path = self._get_path(username)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass


class MemorySessionStorage(BaseSessionStorage):
    """In-memory dictionary session storage (useful for tests/ephemeral environments)."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}

    def save_session(self, username: str, data: dict) -> None:
        self._sessions[username] = data.copy()

    def load_session(self, username: str) -> Optional[dict]:
        return self._sessions.get(username)

    def delete_session(self, username: str) -> None:
        self._sessions.pop(username, None)


class BaseStorage(ABC):
    """Base interface for persisting accounts, jobs, and run history."""

    @abstractmethod
    def save_account(self, account: Account) -> None:
        """Save an account configuration."""
        pass

    @abstractmethod
    def get_account(self, nickname: str) -> Optional[Account]:
        """Load a single account by nickname. Returns None if not found."""
        pass

    @abstractmethod
    def load_accounts(self) -> list[Account]:
        """Load all registered accounts."""
        pass

    @abstractmethod
    def remove_account(self, nickname: str) -> None:
        """Remove an account by nickname."""
        pass

    @abstractmethod
    def save_job(self, job: Job) -> None:
        """Save a scheduled job."""
        pass

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        """Load a single job by ID. Returns None if not found."""
        pass

    @abstractmethod
    def load_jobs(self, action_loader: Callable[[str, Optional[dict]], Callable]) -> list[Job]:
        """Load all scheduled jobs."""
        pass

    @abstractmethod
    def remove_job(self, job_id: str) -> None:
        """Remove a job by ID."""
        pass

    @abstractmethod
    def add_job_run(self, run: JobRun) -> None:
        """Record a job run in history."""
        pass

    @abstractmethod
    def get_job_runs(self, job_id: str) -> list[JobRun]:
        """Load run history for a job."""
        pass


class SQLiteStorage(BaseStorage):
    """SQLite-based persistent storage for accounts, jobs, and run history."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_info (
                    version INTEGER PRIMARY KEY
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    nickname TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL,
                    browser_id TEXT NOT NULL,
                    proxy TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    trigger_expr TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_args TEXT,
                    account_nickname TEXT NOT NULL,
                    dry_run INTEGER NOT NULL,
                    daily_limit TEXT,
                    enabled INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    last_run_at TEXT,
                    next_run_at TEXT,
                    consecutive_failures INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS job_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    success INTEGER NOT NULL,
                    error TEXT,
                    dry_run INTEGER NOT NULL,
                    triggered_by TEXT NOT NULL
                )
            """)
            conn.execute("INSERT OR IGNORE INTO schema_info (version) VALUES (1)")
            conn.commit()

    def save_account(self, account: Account) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO accounts (nickname, username, password, browser_id, proxy) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    account.nickname,
                    account.username,
                    account.password,
                    account.browser_id,
                    account.proxy,
                ),
            )
            conn.commit()

    def get_account(self, nickname: str) -> Optional[Account]:
        from pgbank_unofficial.models import Account

        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT username, password, browser_id, proxy FROM accounts WHERE nickname = ?",
                (nickname,),
            ).fetchone()
            if row:
                return Account(
                    username=row[0],
                    password=row[1],
                    browser_id=row[2],
                    proxy=row[3],
                    nickname=nickname,
                )
            return None

    def load_accounts(self) -> list[Account]:
        from pgbank_unofficial.models import Account

        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.execute(
                "SELECT nickname, username, password, browser_id, proxy FROM accounts"
            )
            return [
                Account(
                    nickname=row[0],
                    username=row[1],
                    password=row[2],
                    browser_id=row[3],
                    proxy=row[4],
                )
                for row in cursor.fetchall()
            ]

    def remove_account(self, nickname: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("DELETE FROM accounts WHERE nickname = ?", (nickname,))
            conn.commit()

    def save_job(self, job: Job) -> None:
        from pgbank_unofficial.scheduler import ConditionalTrigger, CronTrigger, IntervalTrigger

        # Serialize trigger
        t_type = "custom"
        t_expr = {}
        if isinstance(job.trigger, CronTrigger):
            t_type = "cron"
            t_expr = {
                "expression": job.trigger.expression,
                "jitter_seconds": job.trigger.jitter_seconds,
            }
        elif isinstance(job.trigger, IntervalTrigger):
            t_type = "interval"
            t_expr = {
                "seconds": job.trigger._interval.total_seconds(),
                "jitter_seconds": job.trigger.jitter_seconds,
            }
        elif isinstance(job.trigger, ConditionalTrigger):
            t_type = "conditional"
            t_expr = {"check_every_seconds": job.trigger.check_every.total_seconds()}

        # Serialize action
        a_type = "custom"
        a_args = {}
        if hasattr(job.action, "_action_type"):
            a_type = job.action._action_type
            a_args = getattr(job.action, "_action_args", {})

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO jobs ("
                "  id, name, trigger_type, trigger_expr, action_type, action_args, "
                "  account_nickname, dry_run, daily_limit, enabled, created_at, "
                "  last_run_at, next_run_at, consecutive_failures"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job.id,
                    job.name,
                    t_type,
                    json.dumps(t_expr),
                    a_type,
                    json.dumps(a_args),
                    job.account_nickname,
                    1 if job.dry_run else 0,
                    str(job.daily_limit) if job.daily_limit is not None else None,
                    1 if job.enabled else 0,
                    job.created_at.isoformat(),
                    job.last_run_at.isoformat() if job.last_run_at else None,
                    job.next_run_at.isoformat() if job.next_run_at else None,
                    job.consecutive_failures,
                ),
            )
            conn.commit()

    def get_job(self, job_id: str) -> Optional[Job]:
        from pgbank_unofficial.scheduler import (
            ConditionalTrigger,
            CronTrigger,
            IntervalTrigger,
            Job,
            _default_action_loader,
        )

        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return None

            t_type = row[2]
            t_expr = json.loads(row[3] or "{}")
            if t_type == "cron":
                trigger = CronTrigger(
                    t_expr["expression"], jitter_seconds=t_expr.get("jitter_seconds", 0)
                )
            elif t_type == "interval":
                trigger = IntervalTrigger(
                    seconds=t_expr["seconds"], jitter_seconds=t_expr.get("jitter_seconds", 0)
                )
            elif t_type == "conditional":
                trigger = ConditionalTrigger(
                    check_every=timedelta(seconds=t_expr["check_every_seconds"]),
                    condition=lambda c: False,
                )
            else:
                trigger = IntervalTrigger(seconds=3600)

            a_type = row[4]
            a_args = json.loads(row[5] or "{}")
            action = _default_action_loader(a_type, a_args)

            job = Job(
                name=row[1],
                trigger=trigger,
                action=action,
                account_nickname=row[6],
                id=row[0],
                dry_run=bool(row[7]),
                daily_limit=Decimal(row[8]) if row[8] is not None else None,
                enabled=bool(row[9]),
                created_at=datetime.fromisoformat(row[10]),
            )
            job.last_run_at = datetime.fromisoformat(row[11]) if row[11] else None
            job.next_run_at = datetime.fromisoformat(row[12]) if row[12] else None
            job.consecutive_failures = row[13]
            return job

    def load_jobs(self, action_loader: Callable[[str, Optional[dict]], Callable]) -> list[Job]:
        from pgbank_unofficial.scheduler import (
            ConditionalTrigger,
            CronTrigger,
            IntervalTrigger,
            Job,
        )

        jobs = []
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.execute("SELECT * FROM jobs")
            for row in cursor.fetchall():
                # Reconstruct trigger
                t_type = row[2]
                t_expr = json.loads(row[3] or "{}")
                if t_type == "cron":
                    trigger = CronTrigger(
                        t_expr["expression"], jitter_seconds=t_expr.get("jitter_seconds", 0)
                    )
                elif t_type == "interval":
                    trigger = IntervalTrigger(
                        seconds=t_expr["seconds"], jitter_seconds=t_expr.get("jitter_seconds", 0)
                    )
                elif t_type == "conditional":
                    trigger = ConditionalTrigger(
                        check_every=timedelta(seconds=t_expr["check_every_seconds"]),
                        condition=lambda c: False,
                    )
                else:
                    trigger = IntervalTrigger(seconds=3600)

                # Reconstruct action
                a_type = row[4]
                a_args = json.loads(row[5] or "{}")
                action = action_loader(a_type, a_args)

                job = Job(
                    name=row[1],
                    trigger=trigger,
                    action=action,
                    account_nickname=row[6],
                    id=row[0],
                    dry_run=bool(row[7]),
                    daily_limit=Decimal(row[8]) if row[8] is not None else None,
                    enabled=bool(row[9]),
                    created_at=datetime.fromisoformat(row[10]),
                )
                job.last_run_at = datetime.fromisoformat(row[11]) if row[11] else None
                job.next_run_at = datetime.fromisoformat(row[12]) if row[12] else None
                job.consecutive_failures = row[13]
                jobs.append(job)
        return jobs

    def remove_job(self, job_id: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            conn.commit()

    def add_job_run(self, run: JobRun) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO job_runs (job_id, started_at, finished_at, success, error, dry_run, triggered_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run.job_id,
                    run.started_at.isoformat(),
                    run.finished_at.isoformat() if run.finished_at else None,
                    1 if run.success else 0,
                    run.error,
                    1 if run.dry_run else 0,
                    run.triggered_by,
                ),
            )
            conn.commit()

    def get_job_runs(self, job_id: str) -> list[JobRun]:
        from pgbank_unofficial.scheduler import JobRun

        runs = []
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.execute(
                "SELECT job_id, started_at, finished_at, success, error, dry_run, triggered_by "
                "FROM job_runs WHERE job_id = ? ORDER BY started_at DESC",
                (job_id,),
            )
            for row in cursor.fetchall():
                runs.append(
                    JobRun(
                        job_id=row[0],
                        started_at=datetime.fromisoformat(row[1]),
                        finished_at=datetime.fromisoformat(row[2]) if row[2] else None,
                        success=bool(row[3]),
                        error=row[4],
                        dry_run=bool(row[5]),
                        triggered_by=row[6],
                    )
                )
        return runs


class MemoryStorage(BaseStorage):
    """In-memory transient storage for accounts, jobs, and runs."""

    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._jobs: dict[str, Job] = {}
        self._runs: dict[str, list[JobRun]] = {}

    def save_account(self, account: Account) -> None:
        self._accounts[account.nickname] = account

    def get_account(self, nickname: str) -> Optional[Account]:
        return self._accounts.get(nickname)

    def load_accounts(self) -> list[Account]:
        return list(self._accounts.values())

    def remove_account(self, nickname: str) -> None:
        self._accounts.pop(nickname, None)

    def save_job(self, job: Job) -> None:
        self._jobs[job.id] = job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def load_jobs(self, action_loader: Callable[[str, Optional[dict]], Callable]) -> list[Job]:
        return list(self._jobs.values())

    def remove_job(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)

    def add_job_run(self, run: JobRun) -> None:
        self._runs.setdefault(run.job_id, []).append(run)

    def get_job_runs(self, job_id: str) -> list[JobRun]:
        return self._runs.get(job_id, [])
