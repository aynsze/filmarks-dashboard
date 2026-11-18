# scraper/fetcher.py
# bk1
# Filmarksのページを取得

import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_URL = "https://filmarks.com"

# サーバーへの負荷を抑えるため、アクセス間隔を設ける
REQUEST_INTERVAL = 2.0

# 通信設定
TIMEOUT = 30
MAX_RETRIES = 3

_last_request_time = 0.0

class FetchError(Exception):
    """HTML取得に失敗した場合の例外"""
    pass

class NotFoundError(Exception):
    """HTTP 404が発生した場合の例外"""
    pass

def build_list_url(username, category, target, page=1):
    """
    Filmarksのユーザー一覧URLを作成する。

    category:
        movies / dramas / animes

    target:
        marks / clips

    page:
        ページ番号
    """

    if category not in ("movies", "dramas", "animes"):
        raise ValueError(f"不正なカテゴリです: {category}")

    if target not in ("marks", "clips"):
        raise ValueError(f"不正な取得対象です: {target}")

    if not isinstance(page, int) or page < 1:
        raise ValueError("pageは1以上の整数にしてください")

    username = quote(username, safe="")

    if category == "movies":
        if target == "marks":
            path = f"/users/{username}"
        else:
            path = f"/users/{username}/clips"
    else:
        if target == "marks":
            path = f"/users/{username}/marks/{category}"
        else:
            path = f"/users/{username}/clips/{category}"

    url = BASE_URL + path

    # 1ページ目はページ番号を付けない
    if page > 1:
        url += "?" + urlencode({"page": page})

    return url

def build_review_url(category, item_id, review_id):
    """
    レビュー詳細ページのURLを作成する。

    item_id:
        movies: 65267
        dramas: 9032/16111
        animes: 228/337
    """

    if category not in ("movies", "dramas", "animes"):
        raise ValueError(f"不正なカテゴリです: {category}")

    if not review_id:
        raise ValueError("review_idが必要です")

    parts = item_id.strip("/").split("/")

    if category == "movies":
        if len(parts) != 1:
            raise ValueError("映画のIDは1つの数字で指定してください")
    else:
        if len(parts) != 2:
            raise ValueError(
                f"{category}のIDはシリーズID/シーズンIDで指定してください"
            )

    path = "/".join(quote(part, safe="") for part in parts)
    review_id = quote(str(review_id), safe="")

    return f"{BASE_URL}/{category}/{path}/reviews/{review_id}"

def fetch_html(url):
    """
    URLからHTMLを取得する。

    - アクセス間隔を2秒以上確保
    - 一時的な通信エラーは最大3回再試行
    - 文字コードをレスポンスから判定
    """

    global _last_request_time

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; FilmarksPersonalDashboard/1.0)"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "ja,en;q=0.8",
    }

    for attempt in range(MAX_RETRIES + 1):

        # 前回のアクセスから一定時間空ける
        elapsed = time.monotonic() - _last_request_time
        wait_time = REQUEST_INTERVAL - elapsed

        if wait_time > 0:
            time.sleep(wait_time)

        request = Request(url, headers=headers)

        try:
            with urlopen(request, timeout=TIMEOUT) as response:
                _last_request_time = time.monotonic()

                charset = response.headers.get_content_charset() or "utf-8"
                html = response.read().decode(charset, errors="replace")

                return html

        except HTTPError as error:
            _last_request_time = time.monotonic()

            # 404は呼び出し側で処理する
            if error.code == 404:
                raise NotFoundError(
                    f"HTTP 404: {url}"
                ) from error

            # アクセス制限や認証エラーなど
            if error.code not in (429, 500, 502, 503, 504):
                raise FetchError(
                    f"HTTPエラー {error.code}: {url}"
                ) from error

            if attempt >= MAX_RETRIES:
                raise FetchError(
                    f"HTTPエラー {error.code}: 再試行回数を超えました: {url}"
                ) from error

        except (URLError, TimeoutError, OSError) as error:
            _last_request_time = time.monotonic()

            if attempt >= MAX_RETRIES:
                raise FetchError(
                    f"通信に失敗しました: {url} ({error})"
                ) from error

        # 再試行までの待ち時間を段階的に増やす
        retry_wait = 5 * (2 ** attempt)
        print(
            f"通信に失敗しました。{retry_wait}秒後に再試行します。"
        )
        time.sleep(retry_wait)

    raise FetchError(f"HTMLを取得できませんでした: {url}")