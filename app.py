# app.py
from __future__ import annotations

from collections import defaultdict

from flask import Flask, render_template, request, redirect, url_for, session

from questions import (
    SECTIONS,
    CHOICES,
    ANSWER_LABEL,
    DISPLAY_ANSWERS,
    RISK_LABELS,
    VALID_ANSWERS,
    iter_items,
    validate_questions,
)

app = Flask(__name__)
app.secret_key = "change-me"  # 本番は環境変数へ

# リスク優先度（表示順）
RISK_ORDER = {"high": 0, "medium": 1, "low": 2}


def overall_judgement(counts: dict) -> dict:
    """
    点数は使わず、件数で総評を出す
    """
    if counts["high"] > 0:
        return {
            "code": "優先対応",
            "message": "優先して整理・ルール化したい論点があります。",
            "lead": "まずは「高」の項目から着手し、所内の運用を“判断できる状態”に整えるのがおすすめです。",
        }
    if counts["medium"] > 0:
        return {
            "code": "要整理",
            "message": "いくつか整理すると安心できる論点があります。",
            "lead": "「中」の項目を中心に、現状の棚卸しと簡単なルール化から始めるのがおすすめです。",
        }
    if counts["low"] > 0:
        return {
            "code": "軽微",
            "message": "大きな懸念は多くありませんが、整えるとより安心です。",
            "lead": "余力のあるタイミングで「低」の項目を整理しておくと、トラブル耐性が上がります。",
        }
    return {
        "code": "問題なし",
        "message": "現時点で、優先して整理すべき論点は見当たりません。",
        "lead": "運用が変わったタイミングで、定期的に見直すのがおすすめです。",
    }


def build_findings(answers: dict) -> tuple[list[dict], dict]:
    """
    answers を元に「結果表示する項目（no/unknown）」を組み立てる
    - リスクは設問固定（item["risk"]）
    - no/unknown どちらも “対応が必要” として finding にする
    """
    findings: list[dict] = []
    counts = {"high": 0, "medium": 0, "low": 0}

    for sec, item in iter_items():
        qid = item["id"]
        ans = answers.get(qid)

        # 未回答は finding にしない（設計次第で unknown 扱いにしてもOK）
        if ans not in VALID_ANSWERS:
            continue

        # yes は表示しない（問題なし）
        if ans not in DISPLAY_ANSWERS:
            continue

        risk = item.get("risk", "medium")
        if risk not in RISK_LABELS:
            risk = "medium"

        # result_by_answer があれば優先、なければ result
        res = {}
        if "result_by_answer" in item and isinstance(item["result_by_answer"], dict):
            res = item["result_by_answer"].get(ans, {}) or {}
        if not res:
            res = item.get("result", {}) or {}

        title = res.get("title", "")
        why = res.get("why", "")
        next_steps = res.get("next", []) or []

        findings.append(
            {
                "section_id": sec["id"],
                "section_title": sec["title"],
                "risk": risk,
                "risk_label": RISK_LABELS[risk]["label"],
                "risk_desc": RISK_LABELS[risk]["desc"],
                "question": item["q"],
                "answer": ans,
                "answer_label": ANSWER_LABEL.get(ans, ans),
                "title": title,
                "why": why,
                "next": next_steps,
            }
        )
        counts[risk] += 1

    # リスク高→中→低、同一リスク内は並びそのまま
    findings.sort(key=lambda f: (RISK_ORDER.get(f["risk"], 9)))
    return findings, counts


@app.route("/")
def index():
    return redirect(url_for("start"))


@app.route("/check", methods=["GET", "POST"])
def start():
    """
    診断スタート画面
    GET : start.html 表示
    POST: セッション初期化 -> 1セクション目へ
    """
    if request.method == "POST":
        session["answers"] = {}
        return redirect(url_for("section", idx=0))

    return render_template("start.html", total_sections=len(SECTIONS), choices=CHOICES)


@app.route("/check/q/<int:idx>", methods=["GET", "POST"])
def section(idx: int):
    """
    セクション単位の回答画面
    """
    if idx < 0 or idx >= len(SECTIONS):
        return redirect(url_for("result"))

    answers = session.get("answers", {})
    sec = SECTIONS[idx]

    if request.method == "POST":
        # このセクションの回答を保存
        for item in sec["items"]:
            key = item["id"]
            val = request.form.get(key)
            if val in VALID_ANSWERS:
                answers[key] = val

        session["answers"] = answers

        if "prev" in request.form:
            return redirect(url_for("section", idx=idx - 1))
        if "next" in request.form:
            return redirect(url_for("section", idx=idx + 1))
        # それ以外は結果へ
        return redirect(url_for("result"))

    progress = {"current": idx + 1, "total": len(SECTIONS)}
    # ★sec.items という名前はJinjaで dictメソッドと衝突しやすいので items を別名で渡す
    return render_template(
        "section.html",
        sec=sec,
        sec_items=sec["items"],
        idx=idx,
        answers=answers,
        progress=progress,
        choices=CHOICES,
    )

def build_rows_all(answers: dict) -> list[dict]:
    rows = []
    for sec, item in iter_items():
        qid = item["id"]
        ans = answers.get(qid)  # "yes"/"no"/"unknown"/None

        # 未回答は "わからない" 扱いにしたいならここで置換も可能
        if ans is None:
            ans = "unknown"

        risk = item.get("risk", "medium")
        if risk not in RISK_LABELS:
            risk = "medium"

        # 結果文は no/unknown の時だけ使う想定（テンプレ側でも分岐）
        res = {}
        if "result_by_answer" in item and isinstance(item["result_by_answer"], dict):
            res = item["result_by_answer"].get(ans, {}) or {}
        if not res:
            res = item.get("result", {}) or {}

        rows.append(
            {
                "section_id": sec["id"],
                "section_title": sec["title"],
                "risk": risk,
                "risk_label": RISK_LABELS[risk]["label"],
                "question": item["q"],
                "answer": ans,
                "answer_label": ANSWER_LABEL.get(ans, ans),
                "title": res.get("title", ""),
                "why": res.get("why", ""),
                "next": res.get("next", []) or [],
            }
        )

    # リスク順で並べたいならここ（不要なら消してOK）
    # order = {"high": 0, "medium": 1, "low": 2}
    # rows.sort(key=lambda r: (order.get(r["risk"], 9)))
    return rows


def build_section_summary(answers: dict) -> tuple[list[dict], dict]:
    """セクション（device/backup/...）単位のサマリを作る。

    - 指摘：item.show_if_answer_in に該当した件数（通常 no/unknown）
    - リスク別：high/medium/low
    - 回答内訳：yes/no/unknown

    戻り値は (rows_list, rows_by_section_id)
    """

    summary = defaultdict(
        lambda: {
            "section_id": "",
            "title": "",
            "total": 0,
            "answers": {"yes": 0, "no": 0, "unknown": 0},
            "hit_total": 0,
            "hit_by_risk": {"high": 0, "medium": 0, "low": 0},
        }
    )

    for sec, item in iter_items():
        sid = sec["id"]
        qid = item["id"]

        ans = answers.get(qid)
        if ans not in VALID_ANSWERS:
            ans = "unknown"

        risk = item.get("risk", "medium")
        if risk not in RISK_LABELS:
            risk = "medium"

        s = summary[sid]
        s["section_id"] = sid
        s["title"] = sec.get("title", sid)
        s["total"] += 1
        s["answers"][ans] += 1

        show_if = item.get("show_if_answer_in", ["no", "unknown"])
        if ans in show_if:
            s["hit_total"] += 1
            s["hit_by_risk"][risk] += 1

    # 表示順は設問定義順（SECTIONS順）に合わせる
    rows = [summary[sec["id"]] for sec in SECTIONS if sec["id"] in summary]
    by_id = {r["section_id"]: r for r in rows}
    return rows, by_id


def build_rows_by_section(answers: dict, section_summary_by_id: dict) -> list[dict]:
    """セクション単位に、全設問の rows をまとめて返す（ジャンル分け表示用）"""

    buckets: list[dict] = []
    for sec in SECTIONS:
        rows: list[dict] = []
        for item in sec["items"]:
            qid = item["id"]
            ans = answers.get(qid)
            if ans not in VALID_ANSWERS:
                ans = "unknown"

            risk = item.get("risk", "medium")
            if risk not in RISK_LABELS:
                risk = "medium"

            res = {}
            if "result_by_answer" in item and isinstance(item["result_by_answer"], dict):
                res = item["result_by_answer"].get(ans, {}) or {}
            if not res:
                res = item.get("result", {}) or {}

            rows.append(
                {
                    "risk": risk,
                    "risk_label": RISK_LABELS[risk]["label"],
                    "question": item["q"],
                    "answer": ans,
                    "answer_label": ANSWER_LABEL.get(ans, ans),
                    "title": res.get("title", ""),
                    "why": res.get("why", ""),
                    "next": res.get("next", []) or [],
                }
            )

        ssum = section_summary_by_id.get(sec["id"], {})
        buckets.append(
            {
                "section_id": sec["id"],
                "title": sec["title"],
                "total": ssum.get("total", len(rows)),
                "hit_total": ssum.get("hit_total", 0),
                "hit_by_risk": ssum.get("hit_by_risk", {"high": 0, "medium": 0, "low": 0}),
                "answers": ssum.get("answers", {"yes": 0, "no": 0, "unknown": 0}),
                "rows": rows,
            }
        )

    return buckets

@app.route("/check/result")
def result():
    answers = session.get("answers", {})

    # サマリは「回答が yes 以外の件数」だけを数えるのがおすすめ
    counts = {"high": 0, "medium": 0, "low": 0}
    for sec, item in iter_items():
        ans = answers.get(item["id"])
        if ans in ("no", "unknown"):
            risk = item.get("risk", "medium")
            if risk not in counts:
                risk = "medium"
            counts[risk] += 1

    overall = overall_judgement(counts)

    # 分野別サマリ（= セクション別サマリ）
    section_summary, section_summary_by_id = build_section_summary(answers)

    # 詳細表示用：セクション（①〜⑤など）でジャンル分け
    sections = build_rows_by_section(answers, section_summary_by_id)

    # 互換：テンプレで使っている場合に備えて残す（不要なら削除OK）
    all_rows = build_rows_all(answers)

    return render_template(
        "result.html",
        overall=overall,
        counts=counts,
        all_rows=all_rows,
        section_summary=section_summary,
        sections=sections,
    )


if __name__ == "__main__":
    # 設問定義のミスを起動時に検知できる（便利）
    validate_questions(raise_on_error=True)
    app.run(debug=True)
