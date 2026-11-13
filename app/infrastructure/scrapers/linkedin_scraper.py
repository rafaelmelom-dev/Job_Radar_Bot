import asyncio
from jobspy import scrape_jobs

from app.domain.entities.job import Job


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
                title=job_raw.title,
                company_name=job_raw.company,
                location=job_raw.location,
                work_regime=job_raw.job_type,
                apply_url=job_raw.job_url,
                description=job_raw.description,
                external_id=job_raw.id,
            )
            for job_raw in jobs_raw.itertuples(index=False)
        ]

        return jobs
