import asyncio
import html
import logging
import os

import aiohttp

from app.domain.entities.job import CompanyInfo, Course, Job
from app.infrastructure.scrapers import glassdoor, youtube, StackOverflow

logger = logging.getLogger(__name__)


class DataEnrichmentService:
    def __init__(self):
        # Headers padronizados e mais simples (Salario.com.br não exige evasão pesada)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    async def validate_tags(self, title: str, description: str) -> list[str]:
        """Extrai as tecnologias essenciais mencionadas no cargo."""
        tags = StackOverflow.run_scraper(2, None)

        tech_dictionary = [tag.nome for tag in tags]

        text = f"{title} {description}".lower()
        ranked = [
            (tag, text.count(tag.lower()))
            for tag in tech_dictionary
        ]
        matched = [
            tag
            for tag, count in sorted(ranked, key=lambda item: item[1], reverse=True)
            if count
        ]
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
                    is_paid=False
                )
            )

        return courses

    async def _get_udemy_courses(
        self, tag: str, session: aiohttp.ClientSession
    ) -> list[Course]:
        """Busca cursos via Udemy REST API Oficial."""
        if not UDEMY_CLIENT_ID or not UDEMY_CLIENT_SECRET:
            # Fallback se a API não estiver configurada
            return [
                Course(
                    title=f"Cursos de {tag.title()} na Udemy",
                    url=f"https://www.udemy.com/courses/search/?q={tag}",
                    platform="Udemy",
                    provider_or_channel="Busca Udemy",
                    is_paid=True,
                )
            ]

        url = "https://www.udemy.com/api-2.0/courses/"
        params = {"search": tag, "page_size": 1, "language": "pt"}
        auth = aiohttp.BasicAuth(UDEMY_CLIENT_ID, UDEMY_CLIENT_SECRET)

        try:
            async with session.get(url, params=params, auth=auth) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    courses = []
                    for item in data.get("results", []):
                        # Pega o nome do instrutor (se disponível)
                        instructors = item.get(
                            "visible_instructors", [{"title": "Instrutor Udemy"}]
                        )
                        provider = instructors[0]["title"] if instructors else "Udemy"

                        courses.append(
                            Course(
                                title=item["title"],
                                url=f"https://www.udemy.com{item['url']}",
                                platform="Udemy",
                                provider_or_channel=provider,
                                is_paid=item.get("is_paid", True),
                            )
                        )
                    return courses
        except Exception as e:
            logger.error(f"Erro na Udemy API: {e}")

        return []

    async def get_courses_for_tag(self, tag: str) -> list[Course]:
        """Orquestra as buscas nos scrapes de cursos."""
        yt_courses = await self._get_youtube_courses(tag, 1)
        udemy_courses = []
        # udemy_task = self._get_udemy_courses(tag, session)

        return yt_courses + udemy_courses

    async def enrich(self, job: Job) -> Job:
        loop = asyncio.get_running_loop()

        # 1. Extração de tags técnicas
        job.technical_requirements = await self.validate_tags(
            job.title, job.description
        )

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
