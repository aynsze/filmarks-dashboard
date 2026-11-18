# scraper/parser.py
# bk1
# marks・clips・レビュー詳細HTMLを解析

import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

def _normalize_path(href):
    """URLからクエリ・フラグメントを除き、先頭と末尾の / を除去する。"""
    if not href:
        return None

    path = urlsplit(href).path.strip("/")
    return path or None

def _extract_item_id(href, category):
    """
    作品URLからカテゴリ部分を除いたIDを取得する。

    movies: /movies/65267 -> 65267
    dramas: /dramas/9032/16111 -> 9032/16111
    animes: /animes/228/337 -> 228/337
    """
    path = _normalize_path(href)

    if not path:
        return None

    prefix = category + "/"

    if not path.startswith(prefix):
        return None

    item_id = path[len(prefix):]

    expected_parts = 1 if category == "movies" else 2
    parts = item_id.split("/")

    if len(parts) != expected_parts:
        return None

    if not all(part.isdigit() for part in parts):
        return None

    return item_id

def _extract_review_id(card, title_link):
    """
    marks一覧カードからreviewIdを取得する。

    優先順位:
    1. 続きを読むリンクのURL末尾
    2. 作品URLの #mark-reviewId
    """
    readmore = card.select_one(
        ".c-content-card__readmore-review a"
    )

    if readmore:
        path = _normalize_path(readmore.get("href"))
        if path:
            match = re.search(r"/reviews/(\d+)$", path)
            if match:
                return match.group(1)

    if title_link:
        href = title_link.get("href", "")
        fragment = urlsplit(href).fragment
        match = re.fullmatch(r"mark-(\d+)", fragment)

        if match:
            return match.group(1)

    return None

def _extract_title(element):
    """タイトルから年などの補足spanを除いて取得する。"""
    if not element:
        return None

    # spanなどの子要素を除いた直接テキストを取得
    direct_text = "".join(
        str(node)
        for node in element.find_all(string=True, recursive=False)
    )

    title = direct_text.strip()

    if title:
        return title

    return element.get_text(" ", strip=True)

def _extract_image(card, selector):
    """画像URLを取得する。"""
    image = card.select_one(selector)

    if not image:
        return None

    return image.get("src")

def parse_marks_list(html, category):
    """
    marks一覧HTMLを解析する。

    取得項目:
    id, reviewId, title, image

    ratingとwatched_dateはレビュー詳細ページから取得するため、
    この関数ではNoneにする。
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for card in soup.select(".c-content-card"):
        title_link = card.select_one(
            ".c-content-card__title a"
        )

        if not title_link:
            continue

        item_id = _extract_item_id(
            title_link.get("href"),
            category
        )

        if not item_id:
            continue

        title = _extract_title(title_link)

        if not title:
            continue

        review_id = _extract_review_id(
            card,
            title_link
        )

        image = _extract_image(
            card,
            ".c-content__jacket img"
        )

        results.append({
            "id": item_id,
            "reviewId": review_id,
            "title": title,
            "watched_date": None,
            "rating": None,
            "image": image,
        })

    return results

def parse_clips_list(html, category):
    """
    clips一覧HTMLを解析する。

    取得項目:
    id, title, image

    clipsにはreviewId、watched_date、ratingがないためNoneにする。
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for card in soup.select(".c-content-item"):
        title_link = card.select_one(
            ".c-content-item__title a"
        )

        if not title_link:
            continue

        item_id = _extract_item_id(
            title_link.get("href"),
            category
        )

        if not item_id:
            continue

        title = title_link.get_text(" ", strip=True)

        if not title:
            continue

        image = _extract_image(
            card,
            ".c2-poster-m img"
        )

        results.append({
            "id": item_id,
            "reviewId": None,
            "title": title,
            "watched_date": None,
            "rating": None,
            "image": image,
        })

    return results

def parse_review_detail(html):
    """
    レビュー詳細HTMLから評価と鑑賞日時を取得する。

    評価:
        .c-rating__score のテキスト
        "-" の場合はNone

    鑑賞日時:
        time.c-media__date のdatetime属性
    """
    soup = BeautifulSoup(html, "html.parser")

    # 評価
    rating_element = soup.select_one(
        ".c-rating__score"
    )

    rating = None

    if rating_element:
        rating_text = rating_element.get_text(
            strip=True
        )

        if rating_text and rating_text != "-":
            try:
                rating = float(rating_text)
            except ValueError:
                rating = None

    # 鑑賞日時
    date_element = soup.select_one(
        "time.c-media__date"
    )

    watched_date = None

    if date_element:
        watched_date = date_element.get("datetime")

        if watched_date:
            watched_date = watched_date.strip() or None

    return {
        "rating": rating,
        "watched_date": watched_date,
    }