# scraper/main.py
# bk1
# 取得範囲やカテゴリを判断し、JSONを更新

import argparse
import json
import sys
from pathlib import Path

from fetcher import (
    build_list_url,
    build_review_url,
    fetch_html,
    FetchError,
)
from parser import (
    parse_marks_list,
    parse_clips_list,
    parse_review_detail,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"

CATEGORIES = ("movies", "dramas", "animes")
TARGETS = ("marks", "clips")

# ページ送りの仕様が変わった場合の無限ループ防止
MAX_PAGES = 1000

def parse_arguments():
    """コマンドライン引数を読み取る。"""

    parser = argparse.ArgumentParser(
        description="Filmarksのmarks/clipsデータを取得します。"
    )

    parser.add_argument(
        "--scope",
        choices=("all", "latest", "id"),
        required=True,
        help="取得範囲",
    )

    parser.add_argument(
        "--category",
        choices=("all", "movies", "dramas", "animes"),
        required=True,
        help="取得カテゴリ",
    )

    parser.add_argument(
        "--target",
        choices=("both", "marks", "clips"),
        required=True,
        help="marks / clips / 両方",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="最新N件の取得件数",
    )

    parser.add_argument(
        "--item-id",
        default="",
        help="特定作品のID",
    )

    args = parser.parse_args()

    if args.scope == "latest" and args.limit < 1:
        parser.error("--limitには1以上を指定してください。")

    if args.scope == "id":
        if not args.item_id.strip():
            parser.error("--scope idでは--item-idが必要です。")

        if args.category == "all":
            parser.error(
                "特定IDを取得する場合はカテゴリを1つ指定してください。"
            )

    return args

def get_categories(category):
    """取得対象のカテゴリ一覧を返す。"""

    if category == "all":
        return list(CATEGORIES)

    return [category]

def get_targets(target):
    """
    取得対象を返す。

    両方の場合はclipsを先に取得し、
    marksを後から取得する。

    同じ作品IDが両方に存在した場合は、
    marksの情報を優先する。
    """

    if target == "both":
        return ["clips", "marks"]

    return [target]

def validate_item_id(category, item_id):
    """指定された作品IDの形式を確認する。"""

    parts = item_id.strip("/").split("/")

    expected_parts = 1 if category == "movies" else 2

    if len(parts) != expected_parts:
        raise ValueError(
            f"{category}のID形式が正しくありません: {item_id}"
        )

    if not all(part.isdigit() for part in parts):
        raise ValueError(
            f"作品IDには数字を指定してください: {item_id}"
        )

    return "/".join(parts)

def fetch_listing_page(username, category, target, page):
    """一覧ページを取得して解析する。"""

    url = build_list_url(
        username=username,
        category=category,
        target=target,
        page=page,
    )

    print(f"一覧取得: {url}")

    html = fetch_html(url)

    if target == "marks":
        records = parse_marks_list(html, category)
    else:
        records = parse_clips_list(html, category)

    return records

def fetch_all_listing(
    username,
    category,
    target,
    scope,
    limit=50,
    item_id=None,
):
    """
    一覧をページ単位で取得する。

    all:
        データがなくなるまで取得する。

    latest:
        先頭からlimit件に達するまで取得する。

    id:
        指定IDが見つかるまで取得する。
    """

    collected = []
    seen_ids = set()
    previous_page_signature = None

    for page in range(1, MAX_PAGES + 1):

        page_records = fetch_listing_page(
            username,
            category,
            target,
            page,
        )

        if not page_records:
            print(f"{page}ページ目にデータがありません。終了します。")
            break

        # 同じページが繰り返し返される場合の対策
        page_signature = tuple(
            record["id"] for record in page_records
        )

        if page_signature == previous_page_signature:
            print("前ページと同じ内容のため、ページ取得を終了します。")
            break

        previous_page_signature = page_signature

        new_count = 0

        for record in page_records:

            record_id = record["id"]

            if record_id in seen_ids:
                continue

            seen_ids.add(record_id)
            collected.append(record)
            new_count += 1

            if scope == "id" and record_id == item_id:
                print(f"指定IDを発見しました: {item_id}")
                return [record]

            if scope == "latest" and len(collected) >= limit:
                return collected[:limit]

        print(
            f"{page}ページ目: {len(page_records)}件取得 "
            f"(新規 {new_count}件)"
        )

        # 同じIDばかり返される場合も終了
        if new_count == 0:
            print("新しい作品がないため、ページ取得を終了します。")
            break

    else:
        print(
            f"警告: 最大ページ数 {MAX_PAGES} に達しました。"
        )

    if scope == "id":
        raise ValueError(
            f"指定された作品IDが見つかりません: {item_id}"
        )

    return collected

def enrich_marks(username, category, records):
    """
    marksのレビュー詳細を取得して評価と鑑賞日時を補完する。

    詳細ページの取得に失敗した場合は、
    既存JSONの値を残せるように記録する。
    """

    for index, record in enumerate(records, start=1):

        review_id = record.get("reviewId")

        record["_detail_fetched"] = False

        if not review_id:
            print(
                f"[{index}/{len(records)}] "
                f"reviewIdがないため詳細取得をスキップ: "
                f"{record['title']}"
            )
            continue

        url = build_review_url(
            category=category,
            item_id=record["id"],
            review_id=review_id,
        )

        print(
            f"[{index}/{len(records)}] "
            f"レビュー詳細取得: {record['title']}"
        )

        try:
            html = fetch_html(url)

            detail = parse_review_detail(html)

            record["rating"] = detail["rating"]
            record["watched_date"] = detail["watched_date"]
            record["_detail_fetched"] = True

        except FetchError as error:
            print(f"レビュー詳細の取得に失敗しました: {error}")

    return records

def load_data(category):
    """既存JSONを読み込む。"""

    path = DATA_DIR / f"{category}.json"

    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

    except json.JSONDecodeError as error:
        raise ValueError(
            f"{path} のJSON形式が正しくありません: {error}"
        ) from error

    if not isinstance(data, list):
        raise ValueError(
            f"{path} はJSON配列である必要があります。"
        )

    return data

def merge_record(existing, new_record, target):
    """
    同じ作品IDのデータを更新する。

    marks:
        詳細取得に成功した場合は評価・日時を更新する。
        詳細取得に失敗した場合は既存値を維持する。

    clips:
        marksからclipsへの変更を反映するため、
        reviewId・評価・日時をNoneに更新する。
    """

    merged = existing.copy()

    detail_fetched = new_record.get("_detail_fetched", False)

    for key, value in new_record.items():

        if key.startswith("_"):
            continue

        if (
            target == "marks"
            and not detail_fetched
            and key in ("rating", "watched_date")
            and value is None
        ):
            continue

        if (
            target == "marks"
            and value is None
            and key == "reviewId"
            and merged.get("reviewId")
        ):
            continue

        merged[key] = value

    return merged

def save_data(category, new_records, target):
    """
    既存JSONにデータを追加・更新して保存する。

    作品IDをキーとして扱う。
    取得対象に含まれない作品は削除しない。
    """

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    existing_records = load_data(category)

    records_by_id = {}
    ordered_ids = []

    # 既存データを読み込む
    for record in existing_records:

        if not isinstance(record, dict):
            continue

        record_id = record.get("id")

        if not record_id:
            continue

        if record_id not in records_by_id:
            ordered_ids.append(record_id)

        records_by_id[record_id] = record

    added = 0
    updated = 0

    # 新しいデータを追加・更新する
    for new_record in new_records:

        record_id = new_record["id"]

        existing = records_by_id.get(record_id)

        if existing is None:

            merged = {
                key: value
                for key, value in new_record.items()
                if not key.startswith("_")
            }

            records_by_id[record_id] = merged
            ordered_ids.append(record_id)
            added += 1

        else:

            merged = merge_record(
                existing,
                new_record,
                target,
            )

            if merged != existing:
                updated += 1

            records_by_id[record_id] = merged

    final_records = [
        records_by_id[record_id]
        for record_id in ordered_ids
    ]

    path = DATA_DIR / f"{category}.json"

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            final_records,
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")

    print(
        f"{path.name}: "
        f"追加 {added}件 / 更新 {updated}件 / "
        f"合計 {len(final_records)}件"
    )

def run():
    """スクレイピング全体を実行する。"""

    args = parse_arguments()

    username = __import__("os").environ.get(
        "FILMARKS_USERNAME"
    )

    if not username:
        raise ValueError(
            "環境変数 FILMARKS_USERNAME が設定されていません。"
        )

    categories = get_categories(args.category)
    targets = get_targets(args.target)

    for category in categories:

        print("")
        print("=" * 50)
        print(f"カテゴリ: {category}")
        print("=" * 50)

        # 指定IDの場合はカテゴリごとの形式を確認
        item_id = None

        if args.scope == "id":
            item_id = validate_item_id(
                category,
                args.item_id,
            )

        for target in targets:

            print("")
            print(f"取得対象: {target}")

            records = fetch_all_listing(
                username=username,
                category=category,
                target=target,
                scope=args.scope,
                limit=args.limit,
                item_id=item_id,
            )

            if not records:
                print("取得データがありません。")
                continue

            if target == "marks":
                records = enrich_marks(
                    username,
                    category,
                    records,
                )

            save_data(
                category=category,
                new_records=records,
                target=target,
            )

    print("")
    print("Filmarksデータの取得・更新が完了しました。")

if __name__ == "__main__":

    try:
        run()

    except Exception as error:
        print(f"エラー: {error}", file=sys.stderr)
        sys.exit(1)
