from llm_utils import call_llm
from googlesearch import search  # pip install googlesearch-python
from PyPDF2 import PdfReader
import requests
from io import BytesIO

# HTML本文抽出（bs4が無い場合はタイトル要約にフォールバック）
try:
    from bs4 import BeautifulSoup  # pip install beautifulsoup4
    HAS_BS4 = True
except Exception:
    HAS_BS4 = False


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
TIMEOUT = 15
MAX_DOCS = 3            # 上位3件だけ処理
MAX_EXTRACT_CHARS = 8000  # LLMに渡す生テキストの最大長


def suggest_queries(internal_summary: str) -> list[str]:
    """
    内部要約から検索クエリ3つを生成。必ず3件返す。
    """
    prompt = f"""
以下の内部要約から、外部情報収集に有効な検索クエリを3つ日本語で提案してください。
- 短く具体的な名詞句で
内部要約:
{internal_summary}
"""
    resp = call_llm(prompt, temperature=0.5)
    qs = [q.strip("・- 1234567890. ") for q in resp.splitlines() if q.strip()]
    if not qs:
        qs = ["業界動向", "競合分析", "成長戦略"]
    while len(qs) < 3:
        qs.append("市場動向")
    return qs[:3]


def _google_urls(query: str, k: int) -> list[str]:
    """
    Google検索でURLを上位k件取得。
    """
    urls = []
    try:
        for url in search(query, num_results=k, lang="ja"):
            urls.append(url)
            if len(urls) >= k:
                break
    except Exception:
        pass
    return urls


def _is_pdf_url(url: str) -> bool:
    return url.lower().endswith(".pdf")


def _fetch(url: str) -> requests.Response | None:
    try:
        return requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, allow_redirects=True)
    except Exception:
        return None


def _extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content))
        text_parts = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t:
                text_parts.append(t)
        return "\n".join(text_parts)
    except Exception:
        return ""


def _extract_html_text(html: str) -> str:
    if not HAS_BS4:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        # 目立つ部分だけ拾う（title/h1-h3/p/li）
        texts = []
        if soup.title and soup.title.string:
            texts.append(soup.title.get_text(" ", strip=True))
        for tag in soup.find_all(["h1", "h2", "h3", "p", "li"]):
            tx = tag.get_text(" ", strip=True)
            if tx:
                texts.append(tx)
        return "\n".join(texts)
    except Exception:
        return ""


def summarize_title(title: str) -> str:
    """
    URLしか無いときにタイトルから内容を推測要約
    """
    prompt = f"次のタイトルから内容を推測して日本語で1文説明してください:\n{title}"
    return call_llm(prompt, temperature=0.5)


def _summarize_doc(text: str, url: str) -> str:
    """
    単一ドキュメント要約（1〜3文）。長文は先に丸める。
    """
    if not text:
        return summarize_title(url)

    clipped = text[:MAX_EXTRACT_CHARS]
    prompt = f"""
次の本文を日本語で1〜3文に要約してください。簡潔に。

本文（冒頭〜{len(clipped)}文字）:
{clipped}
"""
    return call_llm(prompt, temperature=0.3)


def _summarize_corpus(internal_summary: str, doc_summaries: list[str]) -> str:
    """
    内部要約＋外部（各ドキュメント要約）を統合して、外部要約（3〜5行）を作る。
    内部をファクト優先、外部は補足に。
    """
    joined = "\n".join(f"- {s}" for s in doc_summaries if s.strip())
    prompt = f"""
内部要約と外部要約を統合して、3〜5行の簡潔な統合要約を日本語で作成してください。
- 内部要約は事実として優先
- 外部要約は補足情報として統合（矛盾があれば条件付きで記述）

[内部要約]
{internal_summary}

[外部要約（各ソース1〜3文）]
{joined}
"""
    return call_llm(prompt, temperature=0.3)


def aggregate_search(query: str, max_results: int = MAX_DOCS) -> dict:
    """
    検索 → （PDFは本文抽出 / HTMLは本文抽出）→ 各ドキュメント要約 → 外部要約
    返り値:
      {
        "cards": [{"title","source","url","snippet"}...],
        "summary": "<外部要約（複数ソースのまとめ）>"
      }
    """
    urls = _google_urls(query, k=max_results)
    cards = []
    per_doc_summaries = []

    for url in urls:
        title = url
        source = "Google"
        snippet = ""

        # 1) PDF判定
        if _is_pdf_url(url):
            r = _fetch(url)
            if r and r.ok:
                text = _extract_pdf_text(r.content)
                snippet = _summarize_doc(text, url)
            else:
                snippet = summarize_title(url)
        else:
            r = _fetch(url)
            if r and r.ok:
                ctype = r.headers.get("Content-Type", "").lower()
                if "pdf" in ctype:
                    text = _extract_pdf_text(r.content)
                    snippet = _summarize_doc(text, url)
                else:
                    html_text = _extract_html_text(r.text) if HAS_BS4 else ""
                    snippet = _summarize_doc(html_text, url)
            else:
                snippet = summarize_title(url)

        per_doc_summaries.append(snippet)
        cards.append({
            "title": title[:80],
            "source": source,
            "url": url,
            "snippet": snippet
        })

    # 0件保険
    if not cards:
        cards = [{
            "title": f"参考情報（{query}）",
            "source": "Fallback",
            "url": "https://www.wikipedia.org/",
            "snippet": "検索結果が取得できませんでした。内部データのみで続行します。",
        }]
        external_summary = "外部要約なし"
    else:
        # 外部要約（各ドキュメント要約の合体）
        external_summary = _summarize_corpus("内部要約は別途参照", per_doc_summaries)

    return {"cards": cards, "summary": external_summary}