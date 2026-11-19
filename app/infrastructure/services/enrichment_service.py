import asyncio
import html
import logging
import os

import aiohttp

from app.domain.entities.job import CompanyInfo, Course, Job
from app.infrastructure.scrapers import glassdoor, youtube, udemy_scraper

logger = logging.getLogger(__name__)


class DataEnrichmentService:
    def __init__(self):
        # Headers padronizados e mais simples (Salario.com.br não exige evasão pesada)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    async def validate_tags(self, title: str) -> list[str]:
        """Extrai as tecnologias essenciais mencionadas no cargo."""
        tech_dictionary = [
            "python",
            "java",
            "c#",
            "c++",
            "golang",
            "ruby",
            "php",
            "javascript",
            "typescript",
            "react",
            "angular",
            "vue",
            "node",
            "fastapi",
            "django",
            "spring",
            "sql",
            "postgresql",
            "mysql",
            "mongodb",
            "aws",
            "azure",
            "gcp",
            "docker",
            "kubernetes",
            "devops",
            "spark",
            "hadoop",
        ]
        title_clean = title.lower()
        matched = [t for t in tech_dictionary if t in title_clean]
        return matched if matched else ["desenvolvimento", "tecnologia"]

    async def _get_company(self, company_name: str) -> CompanyInfo:
        """Extrai as informações sobre a empresa"""
        company_info = await glassdoor.run_scraper([company_name])
        company_info = company_info.get(
            company_name, CompanyInfo("", 0.0, 0, 0, "", "")
        )
        return company_info

    async def _get_youtube_courses(self, tag: str, limit: int) -> list[Course]:
        """Busca vídeos reais via YouTube"""
        courses_scraped = youtube.buscar_youtube(tag, limit)
        courses = []

        for course in courses_scraped:
            courses.append(
                Course(
                    title=course.get("titulo", ""),
                    url=course.get("url", ""),
                    platform="YouTube",
                    provider_or_channel=course.get("autor", ""),
                    is_paid=False,
                )
            )

        return courses

    async def _get_udemy_courses(self, tag: str) -> list[Course]:
        """Busca cursos via Udemy Scraper."""

        async with aiohttp.ClientSession() as session:
            scraper = udemy_scraper.UdemyScraper()
            return await scraper.get_courses(tag, session)

        return []

    async def get_courses_for_tag(self, tag: str) -> list[Course]:
        """Orquestra as buscas nos scrapes de cursos."""
        yt_courses = await self._get_youtube_courses(tag, 1)
        udemy_courses = await self._get_udemy_courses(f"curso {tag}")

        return yt_courses + udemy_courses

    async def enrich(self, job: Job) -> Job:
        loop = asyncio.get_running_loop()

        # 1. Extração de tags técnicas
        job.technical_requirements = await self.validate_tags(job.title)

        # # 2. Associação dos cursos via APIs (YouTube e Udemy)
        courses = []
        for tag in job.technical_requirements[
            :2
        ]:  # Limita a 2 tags para não gerar muito tráfego/custo
            courses.extend(await self.get_courses_for_tag(tag))

        # 3. Associação as informações da empresa
        job.company = await self._get_company(job.company_name)

        job.courses = courses

        return job
