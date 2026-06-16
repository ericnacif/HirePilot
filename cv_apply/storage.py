"""Persistência de vagas, rankings e histórico de candidaturas."""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from cv_apply.profile import CandidateProfile, JobMatch, JobPosting


class Storage:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = data_dir / "cv_apply.db"
        self.profile_path = data_dir / "profile.json"
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT,
                    url TEXT NOT NULL,
                    description TEXT,
                    easy_apply INTEGER DEFAULT 0,
                    posted_at TEXT,
                    scraped_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS rankings (
                    job_id TEXT NOT NULL,
                    score REAL NOT NULL,
                    reasons TEXT,
                    skill_overlap TEXT,
                    ranked_at TEXT NOT NULL,
                    PRIMARY KEY (job_id, ranked_at)
                );

                CREATE TABLE IF NOT EXISTS applications (
                    job_id TEXT PRIMARY KEY,
                    job_title TEXT,
                    company TEXT,
                    url TEXT,
                    status TEXT DEFAULT 'prepared',
                    applied_at TEXT NOT NULL,
                    notes TEXT
                );

                CREATE TABLE IF NOT EXISTS web_favorites (
                    sid TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    saved_at TEXT NOT NULL,
                    PRIMARY KEY (sid, job_id)
                );

                CREATE TABLE IF NOT EXISTS web_applied (
                    sid TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    applied_at TEXT NOT NULL,
                    PRIMARY KEY (sid, job_id)
                );

                CREATE TABLE IF NOT EXISTS seen_jobs (
                    sid TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    PRIMARY KEY (sid, job_id)
                );

                CREATE TABLE IF NOT EXISTS search_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sid TEXT NOT NULL,
                    name TEXT NOT NULL,
                    filters_json TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    last_run TEXT,
                    last_new_count INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS web_profiles (
                    sid TEXT PRIMARY KEY,
                    profile_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def save_profile(self, profile: CandidateProfile) -> None:
        self.profile_path.write_text(
            profile.model_dump_json(indent=2), encoding="utf-8"
        )

    def load_profile(self) -> CandidateProfile | None:
        if not self.profile_path.exists():
            return None
        data = json.loads(self.profile_path.read_text(encoding="utf-8"))
        return CandidateProfile.model_validate(data)

    def save_web_profile(self, sid: str, profile: CandidateProfile) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO web_profiles (sid, profile_json, updated_at)
                VALUES (?, ?, ?)
                """,
                (sid, profile.model_dump_json(), datetime.now().isoformat()),
            )

    def load_web_profile(self, sid: str) -> CandidateProfile | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT profile_json FROM web_profiles WHERE sid = ?", (sid,)
            ).fetchone()
        if not row:
            return None
        return CandidateProfile.model_validate(json.loads(row[0]))

    def save_jobs(self, jobs: list[JobPosting]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            for job in jobs:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO jobs
                    (id, title, company, location, url, description, easy_apply, posted_at, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.id,
                        job.title,
                        job.company,
                        job.location,
                        job.url,
                        job.description,
                        1 if job.easy_apply else 0,
                        job.posted_at,
                        job.scraped_at.isoformat(),
                    ),
                )

    def load_jobs(self) -> list[JobPosting]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM jobs ORDER BY scraped_at DESC").fetchall()

        jobs: list[JobPosting] = []
        for row in rows:
            jobs.append(
                JobPosting(
                    id=row["id"],
                    title=row["title"],
                    company=row["company"],
                    location=row["location"] or "",
                    url=row["url"],
                    description=row["description"] or "",
                    easy_apply=bool(row["easy_apply"]),
                    posted_at=row["posted_at"],
                    scraped_at=datetime.fromisoformat(row["scraped_at"]),
                )
            )
        return jobs

    def save_rankings(self, matches: list[JobMatch]) -> None:
        ranked_at = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            for match in matches:
                conn.execute(
                    """
                    INSERT INTO rankings
                    (job_id, score, reasons, skill_overlap, ranked_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        match.job.id,
                        match.score,
                        json.dumps(match.reasons, ensure_ascii=False),
                        json.dumps(match.skill_overlap, ensure_ascii=False),
                        ranked_at,
                    ),
                )

    def load_latest_rankings(self) -> list[tuple[JobPosting, JobMatch]]:
        jobs = {j.id: j for j in self.load_jobs()}
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            latest = conn.execute(
                "SELECT MAX(ranked_at) as ts FROM rankings"
            ).fetchone()
            if not latest or not latest["ts"]:
                return []

            rows = conn.execute(
                """
                SELECT job_id, score, reasons, skill_overlap
                FROM rankings WHERE ranked_at = ?
                ORDER BY score DESC
                """,
                (latest["ts"],),
            ).fetchall()

        result: list[tuple[JobPosting, JobMatch]] = []
        for row in rows:
            job = jobs.get(row["job_id"])
            if not job:
                continue
            match = JobMatch(
                job=job,
                score=row["score"],
                reasons=json.loads(row["reasons"]),
                skill_overlap=json.loads(row["skill_overlap"]),
            )
            result.append((job, match))
        return result

    def record_application(
        self,
        job: JobPosting,
        status: str = "prepared",
        notes: str = "",
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO applications
                (job_id, job_title, company, url, status, applied_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.title,
                    job.company,
                    job.url,
                    status,
                    datetime.now().isoformat(),
                    notes,
                ),
            )

    def has_applied(self, job_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM applications WHERE job_id = ?", (job_id,)
            ).fetchone()
        return row is not None

    def applications_today_count(self) -> int:
        today = date.today().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM applications WHERE applied_at LIKE ?",
                (f"{today}%",),
            ).fetchone()
        return row[0] if row else 0

    def export_rankings_json(self, matches: list[JobMatch], path: Path | None = None) -> Path:
        out = path or (self.data_dir / "rankings.json")
        payload = [
            {
                "score": m.score,
                "title": m.job.title,
                "company": m.job.company,
                "location": m.job.location,
                "url": m.job.url,
                "easy_apply": m.job.easy_apply,
                "reasons": m.reasons,
                "skill_overlap": m.skill_overlap,
            }
            for m in matches
        ]
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return out

    def export_rankings_csv(self, matches: list[JobMatch], path: Path | None = None) -> Path:
        out = path or (self.data_dir / "rankings.csv")
        with out.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                ["score", "title", "company", "location", "easy_apply", "skills", "reasons", "url"]
            )
            for m in matches:
                writer.writerow([
                    f"{m.score:.1f}",
                    m.job.title,
                    m.job.company,
                    m.job.location,
                    "sim" if m.job.easy_apply else "nao",
                    ", ".join(m.skill_overlap),
                    "; ".join(m.reasons),
                    m.job.url,
                ])
        return out

    # ----- Estado web por sessão (favoritos, aplicadas, vagas vistas) -----

    def get_web_state(self, sid: str) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            favs = {
                r["job_id"]: json.loads(r["data"])
                for r in conn.execute(
                    "SELECT job_id, data FROM web_favorites WHERE sid = ?", (sid,)
                )
            }
            applied = {
                r["job_id"]: json.loads(r["data"])
                for r in conn.execute(
                    "SELECT job_id, data FROM web_applied WHERE sid = ?", (sid,)
                )
            }
            seen = [
                r["job_id"]
                for r in conn.execute(
                    "SELECT job_id FROM seen_jobs WHERE sid = ?", (sid,)
                )
            ]
            alerts = [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "filters": json.loads(r["filters_json"]),
                    "enabled": bool(r["enabled"]),
                    "last_run": r["last_run"],
                    "last_new_count": r["last_new_count"],
                }
                for r in conn.execute(
                    "SELECT * FROM search_alerts WHERE sid = ? ORDER BY id DESC",
                    (sid,),
                )
            ]
        return {"favorites": favs, "applied": applied, "seen_ids": seen, "alerts": alerts}

    def save_favorite(self, sid: str, job_id: str, data: dict) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO web_favorites (sid, job_id, data, saved_at)
                VALUES (?, ?, ?, ?)
                """,
                (sid, job_id, json.dumps(data, ensure_ascii=False), datetime.now().isoformat()),
            )

    def remove_favorite(self, sid: str, job_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM web_favorites WHERE sid = ? AND job_id = ?",
                (sid, job_id),
            )

    def save_applied_meta(self, sid: str, job_id: str, data: dict) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO web_applied (sid, job_id, data, applied_at)
                VALUES (?, ?, ?, ?)
                """,
                (sid, job_id, json.dumps(data, ensure_ascii=False), datetime.now().isoformat()),
            )

    def remove_applied_meta(self, sid: str, job_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM web_applied WHERE sid = ? AND job_id = ?",
                (sid, job_id),
            )

    def mark_seen_jobs(self, sid: str, job_ids: list[str]) -> None:
        if not job_ids:
            return
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            for jid in job_ids:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO seen_jobs (sid, job_id, first_seen_at)
                    VALUES (?, ?, ?)
                    """,
                    (sid, jid, now),
                )

    def get_seen_ids(self, sid: str) -> set[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT job_id FROM seen_jobs WHERE sid = ?", (sid,)
            ).fetchall()
        return {r[0] for r in rows}

    def save_alert(self, sid: str, name: str, filters: dict, alert_id: int | None = None) -> int:
        payload = json.dumps(filters, ensure_ascii=False)
        with sqlite3.connect(self.db_path) as conn:
            if alert_id:
                conn.execute(
                    "UPDATE search_alerts SET name = ?, filters_json = ? WHERE id = ? AND sid = ?",
                    (name, payload, alert_id, sid),
                )
                return alert_id
            cur = conn.execute(
                """
                INSERT INTO search_alerts (sid, name, filters_json, enabled)
                VALUES (?, ?, ?, 1)
                """,
                (sid, name, payload),
            )
            return int(cur.lastrowid)

    def delete_alert(self, sid: str, alert_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM search_alerts WHERE id = ? AND sid = ?", (alert_id, sid)
            )

    def update_alert_run(self, sid: str, alert_id: int, new_count: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE search_alerts SET last_run = ?, last_new_count = ?
                WHERE id = ? AND sid = ?
                """,
                (datetime.now().isoformat(), new_count, alert_id, sid),
            )

    def set_alert_enabled(self, sid: str, alert_id: int, enabled: bool) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE search_alerts SET enabled = ? WHERE id = ? AND sid = ?",
                (1 if enabled else 0, alert_id, sid),
            )

    def enabled_alerts(self) -> list[tuple[str, dict]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM search_alerts WHERE enabled = 1"
            ).fetchall()
        out: list[tuple[str, dict]] = []
        for r in rows:
            out.append(
                (
                    r["sid"],
                    {
                        "id": r["id"],
                        "name": r["name"],
                        "filters": json.loads(r["filters_json"]),
                        "sid": r["sid"],
                    },
                )
            )
        return out
