from dataclasses import asdict
from urllib.parse import quote

import pandas as pd
from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from playwright_stealth import Stealth

from app.domain.entities.job import CompanyInfo

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


async def create_browser(p) -> Browser:
    """Inicia o browser com args anti-detecção."""
    return await p.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-web-security",
            "--no-sandbox",
        ],
    )


async def create_context(browser: Browser) -> BrowserContext:
    """Cria contexto com fingerprint brasileiro e headers customizados."""
    return await browser.new_context(
        viewport={"width": 1368, "height": 768},
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        user_agent=USER_AGENT,
        extra_http_headers=HEADERS,
    )


async def apply_stealth(context: BrowserContext) -> None:
    """Aplica stealth para evitar detecção de automação."""
    stealth = Stealth()
    await stealth.apply_stealth_async(context)


async def navigate_to_search(page: Page, keyword: str) -> None:
    """Navega para a página de busca da Glassdoor."""
    encoded_keyword = quote(keyword)
    url = f"https://www.glassdoor.com.br/Search/results.htm?keyword={encoded_keyword}"
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)


async def click_first_company(page: Page) -> None:
    """Clica no primeiro card de empresa da lista."""
    await page.wait_for_selector(
        "[data-test='company-card']", state="visible", timeout=10000
    )
    await page.locator("[data-test='company-card']").first.click()
    await page.wait_for_load_state("domcontentloaded")


async def extract_company_info(page: Page) -> CompanyInfo:
    """Extrai informações da empresa da página de overview."""
    name_locator = page.locator(
        "css=.EmployerInfo_employerInfoHeadingWrapper__3GunT"
    )
    await name_locator.wait_for(state="attached", timeout=10000)
    name = (await name_locator.text_content() or "").strip()

    async def optional_text(selector: str) -> str:
        locator = page.locator(selector)
        if not await locator.count():
            return ""
        return (await locator.text_content() or "").strip()

    headquarter = await optional_text(
        "xpath=//span[text()='Sede']/preceding-sibling::span[1]"
    )
    rating_text = await optional_text(
        "css=.CompanyOverview_overallRating__TKVRp"
    )
    recommend_text = await optional_text(
        "css=.ReviewOverview_recommendLine__qeCP5"
    )
    reviews_text = await optional_text(
        "css=.CompanyOverview_ratingCount__j9KfQ"
    )

    def parse_int(value: str) -> int:
        digits = "".join(char for char in value if char.isdigit())
        return int(digits) if digits else 0

    try:
        rating = float(rating_text.replace(",", "."))
    except (ValueError, AttributeError):
        rating = 0.0

    return CompanyInfo(
        name=name,
        rating=rating,
        recommend_percentage=parse_int(recommend_text),
        reviews_count=parse_int(reviews_text),
        headquarter=headquarter,
        link=page.url,
    )


def print_company_info(info: CompanyInfo) -> None:
    """Exibe informações formatadas."""
    print(f"Nome: {info.name}")
    print(f"Rating: {info.rating}")
    print(f"Recomendação: {info.recommend_percentage}")
    print(f"Contagem avaliações: {info.reviews_count}")
    print(f"Sede: {info.headquarter}")
    print(f"Link: {info.link}")
    print()


async def scrape_keyword(page: Page, keyword: str) -> CompanyInfo | None:
    """Processa uma única keyword: busca -> clica -> extrai. Retorna None se falhar."""
    try:
        await navigate_to_search(page, keyword)
        await click_first_company(page)
        info = await extract_company_info(page)
        # print_company_info(info)
        return info
    except Exception as e:
        print(f"[ERRO] '{keyword}': {e}")
        return None


async def run_scraper(keywords: list[str]) -> dict[str, CompanyInfo]:
    """Orquestra scraping de múltiplas keywords. Retorna dict {keyword: CompanyInfo}."""
    resultados: dict[str, CompanyInfo] = {}

    async with async_playwright() as p:
        browser = await create_browser(p)
        try:
            context = await create_context(browser)
            try:
                await apply_stealth(context)
                for keyword in keywords:
                    page = await context.new_page()
                    try:
                        info = await scrape_keyword(page, keyword)
                        if info:
                            resultados[keyword] = info
                    finally:
                        await page.close()
            finally:
                await context.close()
        finally:
            await browser.close()

    return resultados


def export_company_info(data: dict[str, CompanyInfo], filename: str) -> None:
    df = pd.DataFrame([asdict(c) for c in data.values()])
    df.to_excel(filename, index=False)


# if __name__ == "__main__":
#     palavras = [
#         "nava | tech for business",
#         "levty",
#         "google",
#         "microsoft",
#         "bairesdev",
#         "valve",
#         "dlfkjslad",
#         "ifood",
#         "instituto eldorado"
#     ]
#     import asyncio
#
#     dados = asyncio.run(run_scraper(palavras))
#     export_company_info(dados, "dados.xlsx")
#     print(f"\n--- Concluído: {len(dados)}/{len(palavras)} sucessos ---")
