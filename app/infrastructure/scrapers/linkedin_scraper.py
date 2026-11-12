import asyncio
from typing import List
from bs4 import BeautifulSoup
# from curl_cffi import requests
from jobspy import scrape_jobs
from app.domain.entities.job import Job


class LinkedInScraperService:

    @classmethod
    def _parse_jobs_sync(cls, html_content: str) -> List[Job]:
        """
        Processa o parsing do HTML usando 'lxml' e filtra qualquer resultado
        fora do território brasileiro.
        """
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, "lxml")
        cards = soup.find_all("li")
        jobs: List[Job] = []

        for card in cards:
            title_tag = card.find("h3", class_="base-search-card__title")
            company_tag = card.find("h4", class_="base-search-card__subtitle")
            loc_tag = card.find("span", class_="job-search-card__location")
            link_tag = card.find("a", class_="base-card__full-link")

            if not (title_tag and company_tag and link_tag):
                continue

            title = title_tag.get_text(strip=True)
            company = company_tag.get_text(strip=True)
            loc = loc_tag.get_text(strip=True) if loc_tag else "Brasil"
            link = link_tag.get("href", "").split("?")[0]

            # Filtro de segurança: descarta vagas fora do Brasil
            if not cls._is_brazilian_location(loc):
                continue

            # Identificação do regime de trabalho
            regime = "Presencial"
            lower_title_loc = f"{title.lower()} {loc.lower()}"
            if (
                "remot" in lower_title_loc
                or "home office" in lower_title_loc
                or "teletrabalho" in lower_title_loc
            ):
                regime = "Remoto"
            elif "híbrid" in lower_title_loc or "hibrid" in lower_title_loc:
                regime = "Híbrido"

            job = Job(
                title=title,
                company_name=company,
                location=loc,
                work_regime=regime,
                apply_url=link,
                description=f"Oportunidade para {title} na empresa {company} ({regime}). Candidatura através da ligação oficial.",
                external_id=link.split("-")[-1] if "-" in link else link,
            )
            jobs.append(job)

        return jobs

    async def search_jobs(self, keyword: str, location: str = "Brasil") -> List[Job]:
        """
        Orquestra a pesquisa e a extração assíncrona com restrição nacional.
        """
        loop = asyncio.get_running_loop()

        # # 1. Descarrega o HTML em background com geoId brasileiro
        # html_content = await loop.run_in_executor(
        #     None, self._fetch_html_sync, keyword, location
        # )

        # if not html_content:
        #     return []

        # # 2. Processa o parsing e valida as localidades
        # jobs = await loop.run_in_executor(None, self._parse_jobs_sync, html_content)

        jobs_raw = scrape_jobs(
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
                external_id=job_raw.id
            )
            for job_raw in jobs_raw
        ]

        return jobs
