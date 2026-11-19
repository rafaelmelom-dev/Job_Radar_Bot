import asyncio
import pandas as pd
from jobspy import scrape_jobs

from app.domain.entities.job import Job


def _normalize_text(value) -> str:
    """Convert missing JobSpy/pandas values to strings safe for the database."""
    if pd.isna(value):
        return ""
    return value if isinstance(value, str) else str(value)


class LinkedInScraperService:
    async def search_jobs(self, keyword: str, location: str = "Brazil") -> list[Job]:
        """
        Orquestra a pesquisa e a extração assíncrona com restrição nacional.
        """

        jobs_raw = await asyncio.to_thread(
            scrape_jobs,
            site_name=["linkedin"],
            search_term=keyword,
            location="Brazil",
            results_wanted=20,
            hours_old=24,
            fetch_description=True,
            # proxies=["user:pass@host:port", "localhost"],
        )

        jobs = [
            Job(
                title=_normalize_text(job_raw.title),
                company_name=_normalize_text(job_raw.company),
                location=_normalize_text(job_raw.location),
                work_regime=_normalize_text(job_raw.job_type),
                apply_url=_normalize_text(job_raw.job_url),
                description=_normalize_text(job_raw.description),
                external_id=_normalize_text(job_raw.id) or None,
            )
            for job_raw in jobs_raw.itertuples(index=False)
        ]

        return jobs
