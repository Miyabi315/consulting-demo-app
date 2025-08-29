import streamlit as st
import data_io, llm_utils, web_search
import difflib
import pandas as pd

# ---------- ページ設定 ----------
st.set_page_config(page_title="Consulting Demo App", layout="wide")

# ---------- カスタムCSS ----------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Noto+Sans+JP:wght@400;700&display=swap');

    html, body, [class*="css"]  {
        font-family: 'Inter', 'Noto Sans JP', sans-serif;
    }
    .step-card {
        padding: 1.2em;
        margin: 1em 0;
        border-radius: 12px;
        background-color: #ffffff;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
    }
    .step-title {
        font-weight: 600;
        font-size: 1.2em;
        margin-bottom: 0.5em;
        color: #333;
    }
    .removed {
        background-color: #ffecec;
        color: #d32f2f;
    }
    .added {
        background-color: #e8f5e9;
        color: #2e7d32;
    }
    </style>
    """,
    unsafe_allow_html=True
)

def init_state():
    for k, v in {
        "logs": [],
        "internal_summary": None,
        "queries": [],
        "executed_queries": [],
        "search_results": None,
        "issues": None,
        "proposal_category": "すべて",
        "proposals": None,
        "judge": None,
        "slides": None,
        "external_text": ""   # 👈 追加
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ---------- Helpers ----------
def show_diff_table(old: str, new: str):
    """差分を表形式で見やすく表示"""
    diff = difflib.ndiff(old.splitlines(), new.splitlines())
    removed, added = [], []
    for line in diff:
        if line.startswith("- "):
            removed.append(line[2:])
        elif line.startswith("+ "):
            added.append(line[2:])
    df = pd.DataFrame({
        "削除された案": removed + [""] * (max(len(added), len(removed)) - len(removed)),
        "追加された案": added + [""] * (max(len(added), len(removed)) - len(added)),
    })
    st.table(df.style.set_properties(**{'text-align': 'left'}))

def reset_downstream(*keys):
    for k in keys:
        st.session_state[k] = None

def add_log(entry: str):
    if entry and entry.strip():
        st.session_state.logs.append(entry.strip())

# ---------- Sidebar ----------
st.sidebar.header("履歴")
if st.session_state.logs:
    for i, log in enumerate(reversed(st.session_state.logs[-5:])):
        run_id = len(st.session_state.logs) - i
        st.sidebar.markdown(f"**Run {run_id}:**")
        st.sidebar.markdown(log)
else:
    st.sidebar.write("まだ実行結果はありません")

# ---------- Title ----------
st.title("Consulting Demo App")
st.caption("IBPデータ + 業界情報 → 課題リスト → 提案アイデア → AIレビュー → 提案スライド文章")

# ---------- Step 1: データ入力 ----------
with st.container():
    st.markdown('<div class="step-card"><div class="step-title">Step 1. データ入力</div>', unsafe_allow_html=True)
    uploaded_internal = st.file_uploader("IBPデータ (CSV/Excel/TXT)", type=["csv","xls","xlsx","txt"])
    uploaded_external = st.file_uploader("それ以外のデータ (PDF)", type=["pdf"])
    pasted_text = st.text_area("またはテキストを直接貼り付け")

    internal_text, external_text = "", ""
    if uploaded_internal:
        internal_text = data_io.load_file(uploaded_internal)
    if pasted_text:
        internal_text = pasted_text
    if uploaded_external:
        external_text = data_io.load_file(uploaded_external)   # ← ここで終わってる
    st.markdown('</div>', unsafe_allow_html=True)

# ---------- Step 2: 会社データまとめ ----------
with st.container():
    st.markdown('<div class="step-card"><div class="step-title">Step 2. IBP情報要約</div>', unsafe_allow_html=True)
    if st.button("IBPデータ要約", disabled=not bool(internal_text)):
        with st.spinner("要約中..."):
            st.session_state.internal_summary = llm_utils.summarize_internal(internal_text)
            reset_downstream("queries", "executed_queries", "search_results", "issues", "proposals", "judge", "slides")

    if st.session_state.internal_summary:
        st.write(st.session_state.internal_summary)
    st.markdown('</div>', unsafe_allow_html=True)

# ---------- Step 3: 検索 ----------
with st.container():
    st.markdown('<div class="step-card"><div class="step-title">Step 3. 業界情報の取得</div>', unsafe_allow_html=True)
    if st.button("検索ワードを生成", disabled=not bool(st.session_state.internal_summary)):
        with st.spinner("検索ワードを生成中..."):
            st.session_state.queries = web_search.suggest_queries(st.session_state.internal_summary)
            st.session_state.executed_queries = []
            reset_downstream("search_results", "issues", "proposals", "judge", "slides")

    if st.session_state.queries:
        edited_queries = []
        for idx, q in enumerate(st.session_state.queries):
            cols = st.columns([0.1, 0.9])
            use = cols[0].checkbox("", value=True, key=f"use_q_{idx}")
            txt = cols[1].text_input("検索ワード", value=q, key=f"edit_q_{idx}")
            if use and txt.strip():
                edited_queries.append(txt.strip())

        col1, col2 = st.columns([0.5, 0.5])
        with col1:
            if st.button("選択したワードで検索実行", disabled=len(edited_queries) == 0):
                combined = {"cards": [], "summary": ""}
                executed = []
                for q in edited_queries:
                    with st.spinner(f"検索中: {q}"):
                        res = web_search.aggregate_search(q, max_results=5)
                    if not res["cards"]:
                        executed.append(q + "（スキップ）")
                        continue
                    combined["cards"].extend(res["cards"])
                    if res["summary"]:
                        combined["summary"] += ("\n" + res["summary"])
                    executed.append(q)

                st.session_state.search_results = combined
                st.session_state.executed_queries = executed
                reset_downstream("issues", "proposals", "judge", "slides")

        with col2:
            if st.button("検索せずIBPデータのみで進める"):
                st.session_state.search_results = {
                    "cards": [],
                    "summary": st.session_state.external_text or "",
                }
                st.session_state.executed_queries = ["検索なし（IBPデータのみ）"]
                reset_downstream("issues", "proposals", "judge", "slides")

    if st.session_state.search_results:
        st.markdown("**検索ワード:** " + ", ".join(st.session_state.executed_queries))
        for card in st.session_state.search_results["cards"]:
            st.markdown(f"- [{card['title']}]({card['url']}) ({card['source']})")
        st.markdown("**要点まとめ:**")
        st.write(st.session_state.search_results["summary"] or "_（業界情報なし）_")
    st.markdown('</div>', unsafe_allow_html=True)

# ---------- Step 4: 課題リスト ----------
with st.container():
    st.markdown('<div class="step-card"><div class="step-title">Step 4. 課題抽出</div>', unsafe_allow_html=True)
    if st.button("課題を抽出", disabled=not bool(st.session_state.search_results)):
        with st.spinner("課題を抽出中..."):
            st.session_state.issues = llm_utils.derive_issues(
                st.session_state.internal_summary,
                st.session_state.search_results["summary"] or "",
            )
            reset_downstream("proposals", "judge", "slides")

    if st.session_state.issues:
        st.write(st.session_state.issues)
    st.markdown('</div>', unsafe_allow_html=True)

# ---------- Step 5: 提案アイデア ----------
with st.container():
    st.markdown('<div class="step-card"><div class="step-title">Step 5. 施策案</div>', unsafe_allow_html=True)
    st.session_state.proposal_category = st.radio(
        "カテゴリを選択",
        ["保守", "拡大", "撤退", "おすすめ（AIが選びます）"],
        index=["保守", "拡大", "撤退", "おすすめ"].index(st.session_state.proposal_category),
    )
    if st.button("提案アイデアを生成", disabled=not bool(st.session_state.issues)):
        with st.spinner("生成中..."):
            st.session_state.proposals = llm_utils.generate_proposals(
                st.session_state.issues, st.session_state.proposal_category
            )
            reset_downstream("judge", "slides")

    if st.session_state.proposals:
        st.write(st.session_state.proposals)
        if st.button("再生成（差分表示）"):
            with st.spinner("再生成中..."):
                new_prop = llm_utils.generate_proposals(
                    st.session_state.issues, st.session_state.proposal_category
                )
            show_diff_table(st.session_state.proposals, new_prop)
            col1, col2 = st.columns(2)
            if col1.button("▶ 新しい案を採用"):
                st.session_state.proposals = new_prop
                reset_downstream("judge", "slides")
            if col2.button("⏹ 現在の案を維持"):
                pass
    st.markdown('</div>', unsafe_allow_html=True)

# ---------- Step 6: チェック ----------
with st.container():
    st.markdown('<div class="step-card"><div class="step-title">Step 6. AIレビュー</div>', unsafe_allow_html=True)

    # --- オプション入力欄（追加プロンプト） ---
    extra_review_input = st.text_area(
        "レビュー時に考慮してほしい条件（任意）",
        placeholder="例：予算は年間1億円まで、リスクは低めを重視"
    )

    if st.button("レビューを実行", disabled=not bool(st.session_state.proposals)):
        with st.spinner("レビュー実行中..."):
            st.session_state.judge = llm_utils.review_proposals(
                proposals=st.session_state.proposals,
                internal_summary=st.session_state.internal_summary,
                external_summary=st.session_state.search_results["summary"] or "",
                extra_input=extra_review_input,   # ここで渡す
            )
            reset_downstream("slides")

    if st.session_state.judge:
        st.write(st.session_state.judge)
        if st.button("修正案を適用（差分表示）"):
            with st.spinner("修正案生成中..."):
                refined = llm_utils.refine_proposals(
                    proposals=st.session_state.proposals,
                    judge_feedback=st.session_state.judge,
                    internal_summary=st.session_state.internal_summary,
                    external_summary=st.session_state.search_results["summary"] or "",
                )
            show_diff_table(st.session_state.proposals, refined)
            col1, col2 = st.columns(2)
            if col1.button("▶ 修正案を採用"):
                st.session_state.proposals = refined
                reset_downstream("slides")
            if col2.button("⏹ 続行（修正せず）"):
                pass

    st.markdown('</div>', unsafe_allow_html=True)

# ---------- Step 7: 提案スライド文章 ----------
with st.container():
    st.markdown('<div class="step-card"><div class="step-title">Step 7. 提案スライド文章</div>', unsafe_allow_html=True)
    if st.button("スライド用文章を生成", disabled=not bool(st.session_state.judge)):
        with st.spinner("文章生成中..."):
            st.session_state.slides = llm_utils.build_slide_markdown(
                st.session_state.internal_summary,
                st.session_state.search_results["summary"] or st.session_state.external_text or "",
                st.session_state.issues or "",
                st.session_state.proposals or "",
                st.session_state.judge or "",
            )
            add_log("【スライド文章】\n" + st.session_state.slides)

    if st.session_state.slides:
        st.markdown(st.session_state.slides)
        st.download_button("ダウンロード (Markdown)", st.session_state.slides, file_name="slides.md")
    st.markdown('</div>', unsafe_allow_html=True)