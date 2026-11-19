import random
import time
from dataclasses import dataclass, asdict
from typing import Optional

import pandas as pd
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from playwright_stealth import Stealth

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class TagInfo:
    nome: str
    quantidade_perguntas: int
    descricao: str
    link: str


def pausa(minimo: float = 1.0, maximo: float = 3.0) -> None:
    """Pausa com duração aleatória, como uma pessoa lendo a página."""
    time.sleep(random.uniform(minimo, maximo))


def create_browser(p) -> Browser:
    """Inicia o browser com args anti-detecção (janela visível, mais difícil de barrar)."""
    return p.chromium.launch(
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--no-default-browser-check",
        ],
    )


def create_context(browser: Browser) -> BrowserContext:
    """Cria contexto com fingerprint brasileiro e headers customizados."""
    return browser.new_context(
        viewport={"width": 1366, "height": 768},
        screen={"width": 1366, "height": 768},
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        geolocation={"latitude": -18.7289, "longitude": -47.4994},  # Monte Carmelo
        permissions=["geolocation"],
        color_scheme="light",
        device_scale_factor=1,
        has_touch=False,
        is_mobile=False,
        user_agent=USER_AGENT,
        extra_http_headers=HEADERS,
    )


def apply_stealth(context: BrowserContext) -> None:
    """Aplica stealth para evitar detecção de automação."""
    stealth = Stealth()
    stealth.apply_stealth_sync(context)


def comportamento_humano(page: Page) -> None:
    """Move o mouse e rola a página aos poucos."""
    for _ in range(random.randint(3, 6)):
        page.mouse.move(
            random.randint(100, 1200),
            random.randint(100, 700),
            steps=random.randint(10, 25),
        )
        pausa(0.2, 0.6)

    altura = page.evaluate("document.body.scrollHeight")
    posicao = 0
    while posicao < altura:
        passo = random.randint(250, 500)
        page.mouse.wheel(0, passo)
        posicao += passo
        pausa(0.3, 0.9)


def aguardar_cloudflare(page: Page, tentativas: int = 10) -> bool:
    """Espera a verificação passar. Retorna False se continuar bloqueado."""
    for _ in range(tentativas):
        titulo = page.title().lower()
        if "just a moment" not in titulo and "um momento" not in titulo:
            return True
        print("[AVISO] Verificação do Cloudflare... resolva na janela se aparecer captcha.")
        time.sleep(3)
    return False


def navigate_to_tags(page: Page, pagina: int) -> None:
    """Navega para a página de tags populares do Stack Overflow."""
    url = f"https://stackoverflow.com/tags?tab=popular&page={pagina}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    if not aguardar_cloudflare(page):
        raise RuntimeError("bloqueado pelo Cloudflare")
    page.wait_for_selector("#tags-browser .js-tag-cell", state="visible", timeout=15000)


def extract_tags(page: Page) -> list[TagInfo]:
    """Extrai as tags da página atual."""
    resultado: list[TagInfo] = []
    cards = page.locator("#tags-browser .js-tag-cell")

    for i in range(cards.count()):
        card = cards.nth(i)
        link_tag = card.locator("a.post-tag").first
        nome = link_tag.text_content().strip()
        href = link_tag.get_attribute("href") or ""

        qtd_texto = card.locator(".fs-caption").first.text_content()
        qtd = int("".join(c for c in qtd_texto if c.isdigit()))

        desc_loc = card.locator("div.v-truncate4")
        descricao = desc_loc.first.text_content().strip() if desc_loc.count() else ""

        resultado.append(
            TagInfo(
                nome=nome,
                quantidade_perguntas=qtd,
                descricao=descricao,
                link=f"https://stackoverflow.com{href}",
            )
        )
    return resultado


def print_tag_info(info: TagInfo) -> None:
    """Exibe informações formatadas."""
    print(f"Tag: {info.nome}")
    print(f"Perguntas: {info.quantidade_perguntas}")
    print(f"Link: {info.link}")
    print("")


def scrape_page(page: Page, numero: int) -> Optional[list[TagInfo]]:
    """Processa uma página: navega -> age como humano -> extrai. Retorna None se falhar."""
    try:
        navigate_to_tags(page, numero)
        comportamento_humano(page)
        tags = extract_tags(page)
        for t in tags:
            print_tag_info(t)
        return tags
    except Exception as e:
        print(f"[ERRO] página {numero}: {e}")
        return None


def export_tags(data: list[TagInfo], filename: str) -> None:
    df = pd.DataFrame([asdict(t) for t in data])
    df.to_excel(filename, index=False)


def run_scraper(paginas: int, arquivo: str) -> list[TagInfo]:
    """Orquestra o scraping. Salva o Excel a cada página e para após 2 falhas seguidas."""
    resultados: list[TagInfo] = []
    falhas_seguidas = 0

    with sync_playwright() as p:
        browser = create_browser(p)
        context = create_context(browser)
        apply_stealth(context)

        try:
            page = context.new_page()
            for numero in range(1, paginas + 1):
                tags = scrape_page(page, numero)
                if tags:
                    resultados.extend(tags)
                    falhas_seguidas = 0
                    # export_tags(resultados, arquivo)  # salva a cada página
                    print(f"[OK] página {numero}: {len(resultados)} tags até agora")
                else:
                    falhas_seguidas += 1
                    if falhas_seguidas >= 2:
                        print("[PARADO] 2 falhas seguidas, provavelmente bloqueio.")
                        break
                pausa(5, 10)
        except KeyboardInterrupt:
            print("\n[INTERROMPIDO] salvando o que foi coletado...")
        finally:
            browser.close()
            # if resultados:
            #     export_tags(resultados, arquivo)

    return resultados


if __name__ == "__main__":
    dados = run_scraper(paginas=3, arquivo="stackoverflow_tags.xlsx")
    print(f"\n--- Concluído: {len(dados)} tags salvas ---")