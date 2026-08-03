"""Generate the profile's GitHub stats SVG using only GitHub-owned APIs."""

from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path


USERNAME = os.environ.get("PROFILE_USERNAME", "jebarson-caleb")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUTPUT = Path(__file__).resolve().parents[2] / "assets" / "github-stats.svg"

API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "jebarson-caleb-profile-stats",
    "X-GitHub-Api-Version": "2022-11-28",
}
if TOKEN:
    API_HEADERS["Authorization"] = f"Bearer {TOKEN}"


def request_json(url: str, *, data: dict | None = None) -> object:
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(url, data=body, headers=API_HEADERS)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def request_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": API_HEADERS["User-Agent"],
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def contribution_count() -> int:
    if TOKEN:
        query = """
        query($login: String!) {
          user(login: $login) {
            contributionsCollection {
              contributionCalendar { totalContributions }
            }
          }
        }
        """
        payload = request_json(
            "https://api.github.com/graphql",
            data={"query": query, "variables": {"login": USERNAME}},
        )
        return int(
            payload["data"]["user"]["contributionsCollection"]
            ["contributionCalendar"]["totalContributions"]
        )

    fragment = request_text(
        f"https://github.com/{USERNAME}?action=show&controller=profiles"
        f"&tab=contributions&user_id={USERNAME}"
    )
    match = re.search(r"([\d,]+)\s+contributions?\s+in the last year", fragment)
    return int(match.group(1).replace(",", "")) if match else 0


def collect_stats() -> tuple[dict[str, int], Counter[str]]:
    user = request_json(f"https://api.github.com/users/{USERNAME}")
    repos = request_json(
        f"https://api.github.com/users/{USERNAME}/repos"
        "?per_page=100&type=owner&sort=updated"
    )
    owned = [repo for repo in repos if not repo["fork"]]

    language_bytes: Counter[str] = Counter()
    language_failures: list[str] = []
    for repo in owned:
        try:
            languages = request_json(repo["languages_url"])
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            language_failures.append(repo["name"])
            continue
        language_bytes.update(languages)

    # Never replace a complete graphic with partial data when the API is
    # rate-limited or temporarily unavailable.
    if language_failures:
        failed = ", ".join(language_failures)
        raise RuntimeError(f"Could not fetch language data for: {failed}")

    stats = {
        "repos": int(user["public_repos"]),
        "contributions": contribution_count(),
        "stars": sum(int(repo["stargazers_count"]) for repo in owned),
        "followers": int(user["followers"]),
    }
    return stats, language_bytes


def format_number(value: int) -> str:
    return f"{value:,}"


def render_svg(stats: dict[str, int], languages: Counter[str]) -> str:
    palette = ["#EE4E27", "#D7FF3F", "#5A7DFF", "#FF3F98", "#F3F1EC"]
    top_languages = languages.most_common(5)
    total_bytes = sum(count for _, count in top_languages) or 1

    metrics = [
        ("PUBLIC REPOSITORIES", format_number(stats["repos"])),
        ("CONTRIBUTIONS / LAST YEAR", format_number(stats["contributions"])),
        ("STARS / OWN REPOSITORIES", format_number(stats["stars"])),
        ("FOLLOWERS", format_number(stats["followers"])),
    ]

    cards: list[str] = []
    for index, (label, value) in enumerate(metrics):
        x = 36 + index * 282
        cards.append(
            f'<rect x="{x}" y="82" width="270" height="112" rx="3" '
            'fill="#101010" stroke="#2B2B2B"/>'
            f'<text x="{x + 20}" y="116" class="label">{html.escape(label)}</text>'
            f'<text x="{x + 20}" y="166" class="value">{html.escape(value)}</text>'
        )

    segments: list[str] = []
    legends: list[str] = []
    cursor = 36.0
    bar_width = 1128.0
    for index, (language, count) in enumerate(top_languages):
        percentage = count / total_bytes
        width = bar_width * percentage
        color = palette[index]
        segments.append(
            f'<rect x="{cursor:.2f}" y="232" width="{width:.2f}" height="14" fill="{color}"/>'
        )
        legend_x = 36 + index * 225
        legends.append(
            f'<circle cx="{legend_x + 5}" cy="281" r="5" fill="{color}"/>'
            f'<text x="{legend_x + 18}" y="286" class="legend">'
            f'{html.escape(language)} {percentage * 100:.1f}%</text>'
        )
        cursor += width

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="320" viewBox="0 0 1200 320" role="img" aria-labelledby="title desc">
  <title id="title">Live GitHub statistics for {html.escape(USERNAME)}</title>
  <desc id="desc">Public repositories, contributions in the last year, stars, followers, and top languages.</desc>
  <style>
    .kicker {{ font: 700 12px ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: 3px; fill: #9B958C; }}
    .label {{ font: 700 11px ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: 1.4px; fill: #9B958C; }}
    .value {{ font: 800 38px Inter, ui-sans-serif, system-ui, sans-serif; letter-spacing: -1px; fill: #F3F1EC; }}
    .legend {{ font: 650 13px ui-monospace, SFMono-Regular, Consolas, monospace; fill: #F3F1EC; }}
  </style>
  <rect width="1200" height="320" rx="4" fill="#050505"/>
  <rect x=".5" y=".5" width="1199" height="319" rx="4" fill="none" stroke="#252525"/>
  <text x="36" y="48" class="kicker">PUBLIC GITHUB / LIVE SIGNAL</text>
  <circle cx="1158" cy="43" r="5" fill="#EE4E27"/>
  <path d="M1080 43h61" stroke="#EE4E27" stroke-width="2"/>
  {''.join(cards)}
  <text x="36" y="218" class="label">LANGUAGE FOOTPRINT / BYTES IN OWN PUBLIC REPOSITORIES</text>
  {''.join(segments)}
  {''.join(legends)}
</svg>
'''


def main() -> None:
    stats, languages = collect_stats()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render_svg(stats, languages), encoding="utf-8", newline="\n")
    print(f"Updated {OUTPUT} for @{USERNAME}")


if __name__ == "__main__":
    main()
