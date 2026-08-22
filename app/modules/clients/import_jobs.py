import uuid
from typing import TypedDict, List, Literal
from sqlalchemy import String, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.config.database import Base, SessionLocal, engine

JobStatus = Literal["pending", "running", "done", "error"]


class ImportJobModel(Base):
    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    job_type: Mapped[str] = mapped_column(String(50), default="clients")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    imported: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)


# Table creation is now handled by Alembic migrations


class ImportJob(TypedDict):
    status: JobStatus
    progress: int
    imported: int
    created: int
    updated: int
    total: int
    errors: List[str]


def create_job(tenant_id: int | None = None, job_type: str = "clients") -> str:
    """Creates a new job entry in the DB and returns its ID."""
    job_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        job = ImportJobModel(
            id=job_id,
            tenant_id=tenant_id,
            job_type=job_type,
            status="pending",
            progress=0,
            imported=0,
            created=0,
            updated=0,
            total=0,
            errors=[],
        )
        db.add(job)
        db.commit()
    finally:
        db.close()
    return job_id


def get_job(job_id: str) -> ImportJob | None:
    """Reads job status from the database (Cloud Run multi-instance safe)."""
    db = SessionLocal()
    try:
        job = db.query(ImportJobModel).filter(ImportJobModel.id == job_id).first()
        if not job:
            return None
        return {
            "status": job.status,
            "progress": job.progress,
            "imported": job.imported,
            "created": job.created,
            "updated": job.updated,
            "total": job.total,
            "errors": job.errors or [],
        }
    finally:
        db.close()


def update_job(job_id: str, **kwargs) -> None:
    """Updates job fields in the database (thread & process safe)."""
    db = SessionLocal()
    try:
        job = db.query(ImportJobModel).filter(ImportJobModel.id == job_id).first()
        if job:
            for k, v in kwargs.items():
                if hasattr(job, k):
                    setattr(job, k, v)
            db.commit()
    finally:
        db.close()
