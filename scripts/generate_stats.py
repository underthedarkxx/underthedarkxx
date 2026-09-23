#!/usr/bin/env python3
"""Regenera assets/stats.svg e assets/langs.svg a partir da API do GitHub.

Rodado pela GitHub Action .github/workflows/update-stats.yml — não precisa
ser executado manualmente, mas funciona local também (usa GITHUB_TOKEN do
ambiente se existir; sem token, cai no limite de taxa não autenticado).

Critério: "commits totais" e "linguagens" só contam repositórios reais —
exclui forks, repositórios arquivados (as cópias "-main" antigas) e o
próprio repositório de perfil. "Estrelas recebidas" soma todos os
repositórios públicos sem exclusão. "Projetos em que contribuí" vem do
GraphQL (mesma métrica que o GitHub mostra no perfil).
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request

USERNAME = "underthedarkxx"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PALETTE = ["#00E5FF", "#00B8D4", "#0097A7", "#4DD0E1", "#26C6DA"]


def _request(url: str, method: str = "GET", body: bytes | None = None):
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USERNAME,
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp, resp.read()


def list_repos() -> list[dict]:
    repos, page = [], 1
    while True:
        qs = urllib.parse.urlencode({"per_page": 100, "page": page, "type": "owner"})
        _, body = _request(f"https://api.github.com/users/{USERNAME}/repos?{qs}")
        data = json.loads(body)
        if not data:
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    return repos


def commit_count(repo_name: str) -> int:
    qs = urllib.parse.urlencode({"author": USERNAME, "per_page": 1})
    resp, body = _request(f"https://api.github.com/repos/{USERNAME}/{repo_name}/commits?{qs}")
    link = resp.headers.get("Link", "")
    match = re.search(r'page=(\d+)>; rel="last"', link)
    if match:
        return int(match.group(1))
    return len(json.loads(body))


def repos_contributed_to(fallback: int) -> int:
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          totalRepositoriesWithContributedCommits
        }
      }
    }
    """
    payload = json.dumps({"query": query, "variables": {"login": USERNAME}}).encode()
    try:
        _, body = _request("https://api.github.com/graphql", method="POST", body=payload)
        data = json.loads(body)
        return data["data"]["user"]["contributionsCollection"]["totalRepositoriesWithContributedCommits"]
    except Exception as exc:  # noqa: BLE001 — nao trava o resto por causa disso
        print(f"aviso: nao consegui buscar 'contribuido a' via GraphQL ({exc}); mantendo {fallback}", file=sys.stderr)
        return fallback


def read_current_number(svg_path: str, label: str) -> int:
    """Le o valor atual de um card pra usar de fallback se a API falhar."""
    try:
        text = open(svg_path, encoding="utf-8").read()
    except FileNotFoundError:
        return 0
    match = re.search(rf'{re.escape(label)}</text>.*?text-anchor="end">(\d+)<', text, re.S)
    return int(match.group(1)) if match else 0


def write_stats_svg(commits: int, public_repos: int, contributed: int, stars: int) -> None:
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="480" height="210" viewBox="0 0 480 210" role="img" aria-label="Estatísticas do GitHub">
  <defs>
    <linearGradient id="card" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#090C10"/>
      <stop offset="100%" stop-color="#0A1418"/>
    </linearGradient>
  </defs>
  <rect x="0.5" y="0.5" width="479" height="209" rx="12" fill="url(#card)" stroke="#12303A"/>
  <rect x="0.5" y="0.5" width="4" height="209" rx="2" fill="#00E5FF" opacity="0.9"/>
  <g font-family="'Segoe UI',Roboto,Helvetica,Arial,sans-serif">
    <text x="28" y="40" fill="#00E5FF" font-size="16" font-weight="700" letter-spacing="1">ESTATÍSTICAS</text>

    <text x="28" y="80" fill="#7C8B99" font-size="14">Commits totais</text>
    <text x="452" y="80" fill="#EAF6F8" font-size="16" font-weight="700" text-anchor="end">{commits}</text>

    <text x="28" y="112" fill="#7C8B99" font-size="14">Repositórios públicos</text>
    <text x="452" y="112" fill="#EAF6F8" font-size="16" font-weight="700" text-anchor="end">{public_repos}</text>

    <text x="28" y="144" fill="#7C8B99" font-size="14">Projetos em que contribuí</text>
    <text x="452" y="144" fill="#EAF6F8" font-size="16" font-weight="700" text-anchor="end">{contributed}</text>

    <text x="28" y="176" fill="#7C8B99" font-size="14">Estrelas recebidas</text>
    <text x="452" y="176" fill="#EAF6F8" font-size="16" font-weight="700" text-anchor="end">{stars}</text>
  </g>
  <g stroke="#12303A" stroke-width="1">
    <line x1="28" y1="92" x2="452" y2="92"/>
    <line x1="28" y1="124" x2="452" y2="124"/>
    <line x1="28" y1="156" x2="452" y2="156"/>
  </g>
</svg>
'''
    with open(os.path.join(ROOT, "assets", "stats.svg"), "w", encoding="utf-8") as f:
        f.write(svg)


def write_langs_svg(top_langs: list[tuple[str, int]]) -> None:
    n = max(len(top_langs), 1)
    height = 34 * (n - 1) + 108
    max_count = top_langs[0][1] if top_langs else 1

    rows = []
    for i, (lang, count) in enumerate(top_langs):
        y_text = 76 + 34 * i
        y_bar = 63 + 34 * i
        width = round(300 * count / max_count) if max_count else 0
        color = PALETTE[i % len(PALETTE)]
        rows.append(
            f'<text x="28" y="{y_text}" fill="#B7C4CE" font-size="13">{lang}</text>'
            f'<rect x="120" y="{y_bar}" width="302" height="12" rx="6" fill="#0F1B20"/>'
            f'<rect x="120" y="{y_bar}" width="{width}" height="12" rx="6" fill="{color}"/>'
            f'<text x="452" y="{y_text}" fill="#7C8B99" font-size="13" text-anchor="end">{count}</text>'
        )
    rows_svg = "".join(rows)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="480" height="{height}" viewBox="0 0 480 {height}" role="img" aria-label="Projetos por linguagem">
  <defs>
    <linearGradient id="card" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#090C10"/>
      <stop offset="100%" stop-color="#0A1418"/>
    </linearGradient>
  </defs>
  <rect x="0.5" y="0.5" width="479" height="{height - 1}" rx="12" fill="url(#card)" stroke="#12303A"/>
  <rect x="0.5" y="0.5" width="4" height="{height - 1}" rx="2" fill="#00E5FF" opacity="0.9"/>
  <g font-family="'Segoe UI',Roboto,Helvetica,Arial,sans-serif">
    <text x="28" y="34" fill="#00E5FF" font-size="16" font-weight="700" letter-spacing="1">LINGUAGENS</text>
    <text x="452" y="34" fill="#55636E" font-size="11" text-anchor="end">projetos públicos</text>
    {rows_svg}
  </g>
</svg>
'''
    with open(os.path.join(ROOT, "assets", "langs.svg"), "w", encoding="utf-8") as f:
        f.write(svg)


def main() -> None:
    repos = list_repos()
    if not repos:
        print("nenhum repositorio retornado pela API — abortando sem sobrescrever nada", file=sys.stderr)
        sys.exit(1)

    stars = sum(r["stargazers_count"] for r in repos)
    public_repos = len(repos)

    qualifying = [r for r in repos if not r["fork"] and not r["archived"] and r["name"] != USERNAME]
    total_commits = sum(commit_count(r["name"]) for r in qualifying)

    lang_counts: dict[str, int] = {}
    for r in qualifying:
        if r["language"]:
            lang_counts[r["language"]] = lang_counts.get(r["language"], 0) + 1
    top_langs = sorted(lang_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]

    stats_path = os.path.join(ROOT, "assets", "stats.svg")
    contributed_fallback = read_current_number(stats_path, "Projetos em que contribuí")
    contributed = repos_contributed_to(contributed_fallback)

    write_stats_svg(total_commits, public_repos, contributed, stars)
    write_langs_svg(top_langs)

    print(f"commits={total_commits} repos={public_repos} contribuido_a={contributed} estrelas={stars}")
    print(f"linguagens={top_langs}")


if __name__ == "__main__":
    main()
