import csv
import json
import re
from datetime import datetime
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}
COOKIES = {"CONSENT": "YES+1"}

#procura uma chave no JSON aninhado e retorna todos os valores encontrados -> em qualquer profundidade
def _encontrar(obj, chave):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == chave:
                yield v
            else:
                yield from _encontrar(v, chave)
    elif isinstance(obj, list):
        for item in obj:
            yield from _encontrar(item, chave)

#verifica se o campo existe e retorna o texto contido nele, caso contrário retorna None
def _texto(campo):
    if not campo:
        return None
    if "simpleText" in campo:
        return campo["simpleText"]
    return "".join(run.get("text", "") for run in campo.get("runs", [])) or None

#faz a busca no youtube e retorna uma lista de dicionários com os resultados encontrados
def buscar_youtube(termo, limite=10):
    url = f"https://www.youtube.com/results?search_query={quote_plus(termo)}"
    resp = requests.get(url, headers=HEADERS, cookies=COOKIES, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    dados = None
    decoder = json.JSONDecoder()
    initial_data_pattern = re.compile(
        r'(?:var\s+)?ytInitialData\s*=\s*|window\["ytInitialData"\]\s*=\s*'
    )
    for script in soup.find_all("script"):
        conteudo = script.get_text()
        match = initial_data_pattern.search(conteudo)
        if not match:
            continue

        json_bruto = conteudo[match.end():].lstrip()
        try:
            dados, _ = decoder.raw_decode(json_bruto)
            break
        except json.JSONDecodeError:
            continue

    if dados is None:
        titulo = soup.title.get_text(" ", strip=True) if soup.title else "sem título"
        raise RuntimeError(
            "YouTube não retornou ytInitialData "
            f"(título da página: {titulo!r}, URL final: {resp.url}). "
            "Pode ser página de consentimento, bloqueio ou mudança no layout."
        )

    resultados, vistos = [], set()
    for vr in _encontrar(dados, "videoRenderer"):
        video_id = vr.get("videoId")
        if not video_id or video_id in vistos:
            continue
        vistos.add(video_id)

        resultados.append({
            "titulo": _texto(vr.get("title")),
            "autor": _texto(vr.get("ownerText")) or _texto(vr.get("longBylineText")),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })
        if len(resultados) >= limite:
            break

    return resultados

#salva os resultados em um arquivo CSV com o nome baseado no termo pesquisado e na data/hora atual
def salvar_csv(videos, termo):
    nome_termo = re.sub(r"[^\w]+", "_", termo.lower()).strip("_")
    data_hora = datetime.now().strftime("%Y%m%d_%H%M%S")
    arquivo = f"youtube_{nome_termo}_{data_hora}.csv"

    with open(arquivo, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=["titulo", "autor", "url"], delimiter=";")
        escritor.writeheader()
        escritor.writerows(videos)

    return arquivo

# Função principal que executa o programa, solicitando ao usuário o termo de pesquisa e a quantidade de vídeos desejada, realizando a busca e salvando os resultados em um arquivo CSV.
def main():
    print("=== Busca no YouTube (scraping) ===")
    print("Digite o que quer pesquisar (ou 'sair' para encerrar).\n")

    while True:
        termo = input("Pesquisar: ").strip()
        if not termo:
            continue
        if termo.lower() in ("sair", "exit", "q"):
            break

        qtd = input("Quantos vídeos? [10]: ").strip()
        limite = int(qtd) if qtd.isdigit() else 10

        try:
            videos = buscar_youtube(termo, limite)
        except Exception as erro:
            print(f"Erro na busca: {erro}\n")
            continue

        if not videos:
            print("Nenhum vídeo encontrado.\n")
            continue

        print()
        for i, v in enumerate(videos, 1):
            print(f"{i:>2}. {v['titulo']}\n    Autor: {v['autor']}\n    {v['url']}\n")

        arquivo = salvar_csv(videos, termo)
        print(f"Resultados salvos em: {arquivo}\n")


if __name__ == "__main__":
    main()
