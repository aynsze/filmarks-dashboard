// docs/script.js
// bk3
// filmarks-dashboard

// GitHub Raw ContentのURL
const RAW_DATA_BASE =
  "https://raw.githubusercontent.com/aynsze/filmarks-dashboard/refs/heads/main/data";

// ===== データ取得 =====
const CATEGORIES = [
  { key: "movies", label: "映画" },
  { key: "dramas", label: "ドラマ" },
  { key: "animes", label: "アニメ" }
];

let allData = null;

// JSONを1ファイル取得
async function fetchJSON(filename) {
  const url =
    `${RAW_DATA_BASE}/${filename}.json?t=${Date.now()}`;

  const response = await fetch(url, {
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(
      `${filename}.json の取得に失敗しました (${response.status})`
    );
  }

  const data = await response.json();

  if (!Array.isArray(data)) {
    throw new Error(
      `${filename}.json の形式が配列ではありません。`
    );
  }

  return data;
}

/**
 * 3つのJSONを並列取得
 *
 * ページを開いたときに一度だけ実行する。
 * タブを切り替えても再取得しない。
 */
async function loadAllData() {
  const results = await Promise.all(
    CATEGORIES.map(category =>
      fetchJSON(category.key)
    )
  );

  allData = {
    movies: results[0],
    dramas: results[1],
    animes: results[2]
  };
}

// ===== 共通処理 =====
// 観た作品かどうか
function isWatched(item) {
  return item.reviewId !== null &&
    item.reviewId !== undefined;
}

// 観たい作品かどうか
function isWatchlist(item) {
  return !isWatched(item);
}

/**
 * 評価を数値に変換
 *
 * null、空文字、"-" は評価なしとして扱う。
 */
function getRating(item) {
  if (
    item.rating === null ||
    item.rating === undefined ||
    item.rating === "" ||
    item.rating === "-"
  ) {
    return null;
  }

  const value = Number(item.rating);

  return Number.isFinite(value) ? value : null;
}

/**
 * watched_dateをDateとして扱える形式にする
 *
 * 例：
 * 2025-11-27 08:21
 * ↓
 * 2025-11-27T08:21
 */
function getDateValue(item) {
  if (!item.watched_date) {
    return null;
  }

  const value = String(item.watched_date)
    .trim()
    .replace(" ", "T");

  const timestamp = Date.parse(value);

  if (!Number.isFinite(timestamp)) {
    return null;
  }

  return timestamp;
}

// watched_dateから年を取得
function getWatchedYear(item) {
  const timestamp = getDateValue(item);

  if (timestamp === null) {
    return null;
  }

  return new Date(timestamp).getFullYear();
}

/**
 * 日付の古い順に並べる
 *
 * 日付不明は最後。
 */
function sortOldestFirst(items) {
  return [...items].sort((a, b) => {
    const dateA = getDateValue(a);
    const dateB = getDateValue(b);

    if (dateA === null && dateB === null) return 0;
    if (dateA === null) return 1;
    if (dateB === null) return -1;

    return dateA - dateB;
  });
}

// 日付の新しい順に並べる
function sortNewestFirst(items) {
  return [...items].sort((a, b) => {
    const dateA = getDateValue(a);
    const dateB = getDateValue(b);

    if (dateA === null && dateB === null) return 0;
    if (dateA === null) return 1;
    if (dateB === null) return -1;

    return dateB - dateA;
  });
}

/**
 * 年の一覧を取得
 *
 * 新しい年から古い年の順。
 */
function getYears(items) {
  return [
    ...new Set(
      items
        .map(getWatchedYear)
        .filter(year => year !== null)
    )
  ].sort((a, b) => b - a);
}

// HTMLエスケープ
function escapeHTML(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    char => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[char]
  );
}

// ===== 作品表示 =====
// SVG画像かどうかを判定
function isSvgImage(image) {
  if (!image) {
    return false;
  }

  const imagePath = String(image).split(/[?#]/)[0];

  return imagePath.toLowerCase().endsWith(".svg");
}

/**
 * 作品グリッドを生成
 *
 * 画像がnullまたはSVGの場合はタイトルを画像領域に表示。
 */
function createGrid(items) {
  if (items.length === 0) {
    return `<p class="empty-message">作品はありません。</p>`;
  }

  const cards = items.map(item => {
    const title = escapeHTML(item.title || "タイトル不明");
    const image = item.image
      ? escapeHTML(item.image)
      : "";

    // 画像が存在し、SVGではない場合
    const hasUsableImage =
      image !== "" && !isSvgImage(item.image);

    const imageHTML = hasUsableImage
      ? `
          <img
            src="${image}"
            alt="${title}"
            loading="lazy"
          >
        `
      : `
          <div class="grid__placeholder">
            <span class="grid__placeholder-title">
              ${title}
            </span>
          </div>
        `;

    return `
      <div class="grid__item">
        ${imageHTML}
                <p class="grid__title">${title}</p>
      </div>
    `;
  }).join("");

  return `
    <div class="grid">
      ${cards}
    </div>
  `;
}

// カウント付きヘッダー
function createStatusHeader(label, count) {
  return `
    <h2 class="status-block__header">
      <span>${escapeHTML(label)}</span>
      <span class="status-block__count">${count}</span>
    </h2>
  `;
}

// ===== ➀ 一覧 =====
/**
 * ジャンルごとの一覧を生成
 *
 * 映画
 *  ├─ 観たい作品
 *  └─ 観た作品
 *       └─ 年代順
 */
function createGenreList(category) {
  const items = allData[category.key];

  const watchlist = items.filter(isWatchlist);
  const watched = items.filter(isWatched);

  const years = getYears(watched);

  let yearHTML = "";

  // 年ごとの作品
  for (const year of years) {
    const yearItems = sortOldestFirst(
      watched.filter(
        item => getWatchedYear(item) === year
      )
    );

    yearHTML += `
    <div class="year-group">
      <h2>
        ${year}年
        <span class="status-block__count">${yearItems.length}</span>
      </h2>

      ${createGrid(yearItems)}
    </div>
  `;
  }

  // 日付不明の作品
  const unknownDateItems = watched.filter(
    item => getWatchedYear(item) === null
  );

  if (unknownDateItems.length > 0) {
    yearHTML += `
    <div class="year-group">
      <h2>
        日付不明
        <span class="status-block__count">${unknownDateItems.length}</span>
      </h2>

      ${createGrid(unknownDateItems)}
    </div>
  `;
  }

  if (years.length === 0 && unknownDateItems.length === 0) {
    yearHTML = `
            <p class="empty-message">作品はありません。</p>
        `;
  }

  return `
        <section class="genre-section">

            <p class="genre-title">
                ${category.label}
            </p>

            <section class="status-section">
                ${createStatusHeader("観たい作品", watchlist.length)}
                ${createGrid(watchlist)}
            </section>

            <section class="status-section">
                ${createStatusHeader("観た作品", watched.length)}

                ${yearHTML}
            </section>

        </section>
    `;
}

// 一覧画面を描画
function renderList() {
  const html = CATEGORIES.map(
    category => createGenreList(category)
  ).join("");

  document.getElementById("list-content").innerHTML = html;
}

// ===== ➁ 統計 =====
// 総計とジャンル別統計
function renderTotalStats() {
  const total = CATEGORIES.reduce(
    (sum, category) =>
      sum + allData[category.key].length,
    0
  );

  const watchlistTotal = CATEGORIES.reduce(
    (sum, category) =>
      sum + allData[category.key].filter(isWatchlist).length,
    0
  );

  let html = `
        <div class="stats-total">

            <div class="stat-card">
                <div class="stat-card__label">総作品数</div>
                <div class="stat-card__value">${total}</div>
            </div>

            <div class="stat-card">
                <div class="stat-card__label">観たい作品数</div>
                <div class="stat-card__value">${watchlistTotal}</div>
            </div>

        </div>

        <div class="stats-genre">
    `;

  for (const category of CATEGORIES) {
    const items = allData[category.key];

    const watched = items.filter(isWatched).length;
    const watchlist = items.filter(isWatchlist).length;

    html += `
            <div class="stats-genre__item">
                <strong>${category.label}</strong>
                <span>
                    ${watched} / ${watchlist}
                </span>
            </div>
        `;
  }

  html += `</div>`;

  return html;
}

/**
 * 年別統計
 *
 * watched_dateの年を使用。
 * 観た作品のみが対象。
 */
function renderYearStats() {
  const allWatched = CATEGORIES.flatMap(
    category => allData[category.key]
      .filter(isWatched)
  );

  const years = getYears(allWatched);

  let html = `
        <h3 class="section-title">年別統計</h3>
    `;

  if (years.length === 0) {
    return html + `
            <p class="empty-message">
                年別のデータはありません。
            </p>
        `;
  }

  for (const year of years) {
    const counts = CATEGORIES.map(category => {
      return allData[category.key].filter(
        item =>
          isWatched(item) &&
          getWatchedYear(item) === year
      ).length;
    });

    const total = counts.reduce(
      (sum, count) => sum + count,
      0
    );

    html += `
            <section class="stats-year">

                <div class="stats-year__header">
                    <span>${year}年</span>
                    <span>${total}作品</span>
                </div>

                <div class="stats-year__details">

                    ${CATEGORIES.map((category, index) => `
                        <div class="stats-year__item">
                            <span class="stats-year__label">
                                ${category.label}
                            </span>
                            <span class="stats-year__value">
                                ${counts[index]}
                            </span>
                        </div>
                    `).join("")}

                </div>

            </section>
        `;
  }

  return html;
}

// 統計画面を描画
function renderStats() {
  document.getElementById("stats-content").innerHTML =
    renderTotalStats() +
    renderYearStats();
}

// ===== ➂ 評価別 =====
/**
 * 評価別画面を描画
 *
 * ジャンルを統合。
 * 評価がある観た作品のみ。
 */
function renderRatings() {
  const watchedItems = CATEGORIES.flatMap(
    category => allData[category.key].filter(
      item =>
        isWatched(item) &&
        getRating(item) !== null
    )
  );

  const ratings = [
    ...new Set(
      watchedItems.map(getRating)
    )
  ].sort((a, b) => b - a);

  let html = "";

  if (ratings.length === 0) {
    html = `
            <p class="empty-message">
                評価のある作品はありません。
            </p>
        `;
  }

  for (const rating of ratings) {
    const items = sortNewestFirst(
      watchedItems.filter(
        item => getRating(item) === rating
      )
    );

    html += `
    <section class="rating-section">
      <h2>
        <span>★ ${rating.toFixed(1)}</span>
        <span class="status-block__count">
          ${items.length}
        </span>
      </h2>
      ${createGrid(items)}
    </section>
  `;
  }

  document.getElementById("ratings-content").innerHTML = html;
}

// ===== ➃ 年別一覧 =====
/**
 * 全ジャンルを統合して年別に表示
 *
 * 古い日付 → 新しい日付
 * 日付不明は最後。
 */
function renderYears() {
  const watchedItems = CATEGORIES.flatMap(
    category => allData[category.key].filter(isWatched)
  );

  const years = getYears(watchedItems);

  let html = "";

  for (const year of years) {
    const items = sortOldestFirst(
      watchedItems.filter(
        item => getWatchedYear(item) === year
      )
    );

    html += `
  <section class="year-section">
      <h2>
        <span>${year}年</span>
        <span class="status-block__count">
          ${items.length}
        </span>
      </h2>

      ${createGrid(items)}
    </section>
  `;
  }

  const unknownItems = watchedItems.filter(
    item => getWatchedYear(item) === null
  );

  if (unknownItems.length > 0) {
    html += `
    <section class="year-section">
      <h2>
        <span>日付不明</span>
        <span class="status-block__count">
          ${unknownItems.length}
        </span>
      </h2>

      ${createGrid(unknownItems)}
    </section>
  `;
  }

  if (watchedItems.length === 0) {
    html = `
            <p class="empty-message">
                観た作品はありません。
            </p>
        `;
  }

  document.getElementById("years-content").innerHTML = html;
}

// ===== タブ切り替え =====
function switchPage(pageName) {
  // ナビゲーション
  document.querySelectorAll(".nav-button").forEach(button => {
    button.classList.toggle(
      "is-active",
      button.dataset.page === pageName
    );
  });

  // 表示画面
  document.querySelectorAll(".page-section").forEach(section => {
    section.classList.toggle(
      "is-active",
      section.id === `page-${pageName}`
    );
  });

  window.scrollTo({
    top: 0,
    behavior: "instant"
  });
}

function setupNavigation() {
  document.querySelectorAll(".nav-button").forEach(button => {
    button.addEventListener("click", () => {
      switchPage(button.dataset.page);
    });
  });
}

// ===== 初期化 =====
async function initialize() {
  const loading = document.getElementById("loading");
  const error = document.getElementById("error");
  const main = document.querySelector(".main-content");

  try {
    setupNavigation();

    // JSONを3ファイル取得
    await loadAllData();

    // 4画面を生成
    renderList();
    renderStats();
    renderRatings();
    renderYears();

    loading.hidden = true;

  } catch (err) {
    console.error(err);

    loading.hidden = true;
    error.hidden = false;

    error.textContent =
      "データの読み込みに失敗しました。時間をおいて再度お試しください。";
  }
}

document.addEventListener("DOMContentLoaded", initialize);
