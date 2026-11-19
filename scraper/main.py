# scraper/main.py
# bk2
# 取得範囲やカテゴリを判断し、JSONを更新

import argparse
import json
import os
import sys
from pathlib import Path
from bs4 import BeautifulSoup

from fetcher import (
    build_list_url,
    build_review_url,
    fetch_html,
    FetchError,
    NotFoundError,
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
        "--sync-mode",
        choices=("normal", "full"),
        default="normal",
        help="normal: 通常更新 / full: 完全同期",
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

    # 完全同期は全件・marksとclips両方が必須
    # カテゴリは1つでもallでも選択可能
    if args.sync_mode == "full":
        if not (
            args.scope == "all"
            and args.target == "both"
        ):
            parser.error(
                "完全同期では、取得範囲=all、"
                "取得対象=bothを指定してください。"
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

    try:
        html = fetch_html(url)

    except NotFoundError:
        # 1ページ目の404はユーザー名やURLの誤りの可能性があるため、
        # 正常終了として扱わない。
        if page == 1:
            raise

        print(
            f"{page}ページ目はHTTP 404です。"
            "コンテンツがないページとして扱います。"
        )
        return []

    # コンテンツなしページを確認
    soup = BeautifulSoup(html, "html.parser")

    empty_message = soup.select_one(
        '.p-content__center-img img[alt="表示するコンテンツがありません。"]'
    )

    if empty_message:
        print(
            f"{page}ページ目は表示するコンテンツがありません。"
            "正常終了します。"
        )
        return []

    if target == "marks":
        return parse_marks_list(html, category)

    return parse_clips_list(html, category)

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
        指定作品IDが見つかるまで取得する。
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
        raise FetchError(
            f"最大ページ数 {MAX_PAGES} に達しました。"
            "ページ送りを確認してください。"
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

def clean_record(record):
    """内部処理用のキーを除外したデータを返す。"""

    return {
        key: value
        for key, value in record.items()
        if not key.startswith("_")
    }

def save_json_atomically(category, records):
    """
    一時ファイルにJSONを書き出してから置き換える。
    書き込み途中のJSON破損を防ぐ。
    """

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    path = DATA_DIR / f"{category}.json"
    temp_path = DATA_DIR / f"{category}.json.tmp"

    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(
                records,
                file,
                ensure_ascii=False,
                indent=2,
            )
            file.write("\n")

        temp_path.replace(path)

    finally:
        if temp_path.exists():
            temp_path.unlink()

def save_data(category, new_records, target):
    """
    通常更新用。

    既存JSONにデータを追加・更新する。
    取得対象に含まれない作品は削除しない。
    """

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
            records_by_id[record_id] = clean_record(new_record)
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

    save_json_atomically(category, final_records)

    print(
        f"{category}.json: "
        f"追加 {added}件 / 更新 {updated}件 / "
        f"合計 {len(final_records)}件"
    )

def build_full_sync_records(category, clips, marks, existing_records):
    """
    完全同期用のデータを組み立てる。

    clipsに存在する作品とmarksに存在する作品を統合する。
    両方にある場合はmarksを優先する。
    """

    old_by_id = {
        record["id"]: record
        for record in existing_records
        if isinstance(record, dict) and record.get("id")
    }

    clips_by_id = {
        record["id"]: record
        for record in clips
    }

    marks_by_id = {
        record["id"]: record
        for record in marks
    }

    ordered_ids = list(clips_by_id.keys())

    for record_id in marks_by_id:
        if record_id not in clips_by_id:
            ordered_ids.append(record_id)

    final_records = []

    for record_id in ordered_ids:

        clip_record = clips_by_id.get(record_id)
        mark_record = marks_by_id.get(record_id)

        if mark_record is not None:
            # 既存データを優先してベースにすることで、
            # レビュー詳細の取得失敗時に評価・日時を引き継ぐ。
            base_record = (
                old_by_id.get(record_id)
                or clip_record
                or {}
            )

            merged = merge_record(
                base_record,
                mark_record,
                "marks",
            )

            final_records.append(clean_record(merged))

        elif clip_record is not None:
            # marksには存在せずclipsにだけ存在する作品
            final_records.append(clean_record(clip_record))

    return final_records

def save_full_sync_data(staged_data):
    """
    完全同期用。

    取得済みデータと既存JSONを比較し、
    取得結果に存在しない作品を削除する。

    カテゴリの取得が終わってから呼び出す。
    """

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    output_records = {}
    stats = {}

    # まずカテゴリの新しいデータをメモリ上で組み立てる
    for category in staged_data:

        existing = load_data(category)

        final_records = build_full_sync_records(
            category=category,
            clips=staged_data[category]["clips"],
            marks=staged_data[category]["marks"],
            existing_records=existing,
        )

        old_by_id = {
            record["id"]: record
            for record in existing
            if isinstance(record, dict) and record.get("id")
        }

        new_by_id = {
            record["id"]: record
            for record in final_records
        }

        added = len(set(new_by_id) - set(old_by_id))
        deleted = len(set(old_by_id) - set(new_by_id))
        updated = sum(
            1
            for record_id in set(old_by_id) & set(new_by_id)
            if old_by_id[record_id] != new_by_id[record_id]
        )

        output_records[category] = final_records
        stats[category] = {
            "added": added,
            "updated": updated,
            "deleted": deleted,
        }

    # すべてのJSONを一時ファイルとして先に書き出す
    temp_paths = {}

    try:
        for category, records in output_records.items():

            temp_path = DATA_DIR / f"{category}.json.tmp"

            with temp_path.open("w", encoding="utf-8") as file:
                json.dump(
                    records,
                    file,
                    ensure_ascii=False,
                    indent=2,
                )
                file.write("\n")

            temp_paths[category] = temp_path

        # 全ファイルの準備ができたらJSONを置き換える
        for category in staged_data:
            final_path = DATA_DIR / f"{category}.json"
            temp_paths[category].replace(final_path)

    finally:
        for temp_path in temp_paths.values():
            if temp_path.exists():
                temp_path.unlink()

    for category in staged_data:
        result = stats[category]

        print(
            f"{category}.json: "
            f"追加 {result['added']}件 / "
            f"更新 {result['updated']}件 / "
            f"削除 {result['deleted']}件 / "
            f"合計 {len(output_records[category])}件"
        )

def run():
    """スクレイピング全体を実行する。"""

    args = parse_arguments()

    username = os.environ.get("FILMARKS_USERNAME")

    if not username:
        raise ValueError(
            "環境変数 FILMARKS_USERNAME が設定されていません。"
        )

    categories = get_categories(args.category)
    targets = get_targets(args.target)

    if args.sync_mode == "full":
        print("")
        print("=" * 50)
        print("完全同期モード")
        print(
            f"対象カテゴリ: {', '.join(categories)}"
        )
        print("対象: marksとclips")
        print("全取得が成功するまでJSONは変更しません。")
        print("=" * 50)

        # 既存JSONにはまだ触れず、取得データを一時的に保持する
        staged_data = {
            category: {
                "clips": [],
                "marks": [],
            }
            for category in categories
        }

        for category in categories:

            print("")
            print("=" * 50)
            print(f"カテゴリ: {category}")
            print("=" * 50)

            for target in ("clips", "marks"):

                print("")
                print(f"取得対象: {target}")

                records = fetch_all_listing(
                    username=username,
                    category=category,
                    target=target,
                    scope="all",
                )

                if target == "marks":
                    records = enrich_marks(
                        username,
                        category,
                        records,
                    )

                staged_data[category][target] = records

                print(f"{target}: {len(records)}件取得")

        # 全カテゴリ・全対象の取得が終わってから保存する
        print("")
        print("すべての一覧取得が完了しました。JSONを更新します。")

        save_full_sync_data(staged_data)

    else:
        # 通常更新は従来どおり追加・更新のみ
        for category in categories:

            print("")
            print("=" * 50)
            print(f"カテゴリ: {category}")
            print("=" * 50)

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
