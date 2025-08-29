import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------- 共通 LLM 呼び出し ----------
def call_llm(prompt: str, temperature: float = 0.7) -> str:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()


# ---------- 内部要約 ----------
def summarize_internal(text: str) -> str:
    prompt = f"""
次のデータを要約してください。
- 数字や事実は保持
- 重要な詳細も含める
- 出力は5〜8行程度
- 箇条書きまたは段落形式で記述

データ:
{text}
"""
    return call_llm(prompt, temperature=0.3)


# ---------- 課題抽出 ----------
def derive_issues(internal_summary: str, external_summary: str) -> str:
    prompt = f"""
次の情報から課題を整理してください。業界情報がない場合は、IBPデータに基づく課題のみを抽出してください。データ数が少ない場合、データ数が少ないことを課題にしないでください。

[IBPデータ]
{internal_summary}

[業界情報]
{external_summary}

分類:
1. IBPデータに基づく課題
2. 業界情報に基づく課題
3. 1.2の比較から導かれる課題（差分・矛盾・不足）

各項目ごとに2〜3行で簡潔にまとめてください。
"""
    return call_llm(prompt, temperature=0.4)


# ---------- 施策案生成 ----------
def generate_proposals(issues: str, category: str = "すべて") -> str:
    category_prompt = ""
    if category in ["保守", "拡大", "撤退"]:
        category_prompt = f"カテゴリは「{category}」に限定してください。"

    prompt = f"""
以下の課題に対して施策案を提案してください。
- 各施策はできるだけ具体的に
- 数値目標や実施例を含める
- 根拠を1文で補足
- 合計で3案出す
{category_prompt}

[課題]
{issues}
"""
    return call_llm(prompt, temperature=0.6)


# ---------- Judge（矛盾検出） ----------
def review_proposals(proposals: str, internal_summary: str, external_summary: str = "", extra_input="") -> str:
    prompt = f"""
あなたは優秀なコンサルタントです。部下が作成した提案をレビューします。
以下の施策案が、IBPデータや業界情報などを元にレビューしてください。また、全体のリスクをまとめてください。

[施策案]
{proposals}

[IBPデータ]
{internal_summary}

[業界情報]
{external_summary}

[追加条件（ユーザー入力）]
{extra_input}

出力形式:
- ペルソナの設定は出さず、回答だけを出力せよ
- 各施策案ごとに良い点と改善点を一文ずつ
- 全体のリスクを2〜3行で
"""
    return call_llm(prompt, temperature=0.3)


# ---------- 施策修正（Judge反映） ----------
def refine_proposals(proposals: str, judge_feedback: str, internal_summary: str, external_summary: str) -> str:
    prompt = f"""
以下の施策案を、レビューの指摘を踏まえて修正してください。

[現在の施策案]
{proposals}

[Judgeの指摘]
{judge_feedback}

[内部要約]
{internal_summary}

[外部要約]
{external_summary}

出力形式:
- 修正後の施策案を3つ
- 各案ごとに「改善点」を1文で説明
"""
    return call_llm(prompt, temperature=0.5)


# ---------- スライド骨子 ----------
def build_slide_markdown(internal_summary: str, external_summary: str, issues: str, proposals: str, judge: str) -> str:
    prompt = f"""
次の情報をもとに、Markdown形式の提案スライド骨子を作成してください。業界情報がない場合は省略してください。

[IBPデータ]
{internal_summary}

[業界情報]
{external_summary}

[課題]
{issues}

[施策案]
{proposals}

スライド構成:
# 提案資料タイトル
## 課題整理
- IBPデータ
- 業界情報
- IBPと業界の比較からの課題

## 提案施策
- 案1
- 案2
- 案3

## 期待される効果
- 売上/利益/シェア改善の見込みを数値や定性的効果で

## まとめ
- 今後の進め方
"""
    return call_llm(prompt, temperature=0.3)