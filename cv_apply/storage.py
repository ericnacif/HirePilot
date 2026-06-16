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
