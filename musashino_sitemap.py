#!/usr/bin/env python3
"""武蔵野大学Webサイトのサイトマップ抽出スクリプト

トップページから同一ドメイン内のリンクを辿り、
{URL: <title>} の辞書を作成してCSVに保存する。

必要ライブラリ:
    pip install requests beautifulsoup4
"""

import csv
import time
import urllib.robotparser
from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

# ===== 設定 =====
START_URL = "https://www.musashino-u.ac.jp/"
OUTPUT_CSV = "musashino_sitemap.csv"
SLEEP_SEC = 1.5          # 1リクエストごとの待機秒数（サーバー負荷軽減）
TIMEOUT_SEC = 15
MAX_PAGES = None         # テスト時は 50 などに設定。None で無制限
USER_AGENT = "Mozilla/5.0 (compatible; SitemapExtractor/1.0; educational use)"

# HTML以外とみなして辿らない拡張子
SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".zip", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".mp3", ".mp4", ".mov", ".avi", ".css", ".js", ".xml", ".json",
)


def normalize(url: str) -> str:
    """フラグメント（#以降）を除去して正規化する"""
    url, _ = urldefrag(url)
    return url


def is_same_domain(url: str, base_netloc: str) -> bool:
    return urlparse(url).netloc == base_netloc


def should_skip(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return True
    return parsed.path.lower().endswith(SKIP_EXTENSIONS)


def load_robots(base_url: str, session: requests.Session):
    """robots.txtを取得（取得前にもsleepで負荷軽減）"""
    rp = urllib.robotparser.RobotFileParser()
    robots_url = urljoin(base_url, "/robots.txt")
    time.sleep(SLEEP_SEC)
    try:
        resp = session.get(robots_url, timeout=TIMEOUT_SEC)
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
        else:
            rp.parse([])  # 無ければ全許可
    except requests.RequestException:
        rp.parse([])
    return rp


def crawl(start_url: str) -> dict:
    base_netloc = urlparse(start_url).netloc
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    robots = load_robots(start_url, session)

    sitemap = {}                      # key: URL, value: <title>の文字列
    visited = set()
    queue = deque([normalize(start_url)])

    while queue:
        if MAX_PAGES is not None and len(sitemap) >= MAX_PAGES:
            break

        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        if not robots.can_fetch(USER_AGENT, url):
            print(f"[robots除外] {url}")
            continue

        time.sleep(SLEEP_SEC)  # ★必ずアクセス前に待機
        try:
            resp = session.get(url, timeout=TIMEOUT_SEC)
        except requests.RequestException as e:
            print(f"[エラー] {url} : {e}")
            continue

        # リダイレクト後のURLが別ドメインなら除外
        final_url = normalize(resp.url)
        if not is_same_domain(final_url, base_netloc):
            continue
        if final_url != url:
            if final_url in sitemap:
                continue
            visited.add(final_url)
            url = final_url

        if resp.status_code != 200:
            print(f"[{resp.status_code}] {url}")
            continue

        content_type = resp.headers.get("Content-Type", "")
        if "html" not in content_type.lower():
            continue

        # 文字コード対策
        if "charset" not in content_type.lower():
            resp.encoding = resp.apparent_encoding

        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        sitemap[url] = title
        print(f"[{len(sitemap)}] {url} | {title}")

        # 同一ドメインのリンクをキューに追加
        for a in soup.find_all("a", href=True):
            link = normalize(urljoin(url, a["href"].strip()))
            if (
                link not in visited
                and is_same_domain(link, base_netloc)
                and not should_skip(link)
            ):
                queue.append(link)

    return sitemap


def save_csv(sitemap: dict, path: str) -> None:
    # utf-8-sig: Excelで開いても文字化けしない
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "title"])
        for url, title in sitemap.items():
            writer.writerow([url, title])


if __name__ == "__main__":
    result = crawl(START_URL)
    save_csv(result, OUTPUT_CSV)
    print(f"完了: {len(result)} ページを {OUTPUT_CSV} に保存しました")