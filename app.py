from __future__ import annotations

from collections import defaultdict

from flask import Flask, render_template, request, redirect, url_for, session, make_response, send_from_directory
from playwright.sync_api import sync_playwright

from questions import (
    SECTIONS,
    CHOICES,
    ANSWER_LABEL,
    RISK_LABELS,
    VALID_ANSWERS,
    iter_items,
    validate_questions,
)

app = Flask(__name__, static_folder="static")
app.secret_key = "change-me"  # 本番は環境変数へ


@app.get("/robots.txt")
def robots_txt():
    return send_from_directory(app.static_folder, "robots.txt", mimetype="text/plain")

@app.get("/sitemap.xml")
def sitemap_xml():
    return send_from_directory(app.static_folder, "sitemap.xml", mimetype="application/xml")

# --------------------------
# 集計・結果生成
# --------------------------
def overall_judgement(counts: dict) -> dict:
    if counts["high"] > 0:
        return {
            "code": "優先対応",
            "message": "優先して整理・ルール化したい論点があります。",
            "lead": "まずは「リスク：高」の項目から着手し、所内の運用を“判断できる状態”に整えるのがおすすめです。",
        }
    if counts["medium"] > 0:
        return {
            "code": "要整理",
            "message": "いくつか整理すると安心できる論点があります。",
            "lead": "「リスク：中」の項目を中心に、現状の棚卸しと簡単なルール化から始めるのがおすすめです。",
        }
    if counts["low"] > 0:
        return {
            "code": "軽微",
            "message": "大きな懸念は多くありませんが、整えるとより安心です。",
            "lead": "余力のあるタイミングで「リスク：低」の項目を整理しておくと、トラブル耐性が上がります。",
        }
    return {
        "code": "問題なし",
        "message": "現時点で、優先して整理すべき論点は見当たりません。",
        "lead": "運用が変わったタイミングで、定期的に見直すのがおすすめです。",
    }


def build_rows_all(answers: dict) -> list[dict]:
    rows: list[dict] = []
    for sec, item in iter_items():
        qid = item["id"]
        ans = answers.get(qid)
        if ans not in VALID_ANSWERS:
            ans = "unknown"

        risk = item.get("risk", "medium")
        if risk not in RISK_LABELS:
            risk = "medium"

        # result_by_answer があれば優先
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
    return rows


def build_section_summary(answers: dict) -> tuple[list[dict], dict]:
    """
    セクションごとに
      - 全件
      - 回答内訳(yes/no/unknown)
      - 指摘（= show_if_answer_in に該当するもの）をリスク別に
    を集計
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

        # 指摘対象（デフォルト：no/unknown）
        show_if = item.get("show_if_answer_in", ["no", "unknown"])
        if ans in show_if:
            s["hit_total"] += 1
            s["hit_by_risk"][risk] += 1

    rows = [summary[sec["id"]] for sec in SECTIONS if sec["id"] in summary]
    by_id = {r["section_id"]: r for r in rows}
    return rows, by_id


def build_rows_by_section(answers: dict, section_summary_by_id: dict) -> list[dict]:
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


def build_result_context(is_pdf: bool = False) -> dict:
    answers = session.get("answers", {}) or {}
    # 結果表示対象（no / unknown / 未回答）の件数をリスク別に集計
    counts = {"high": 0, "medium": 0, "low": 0}

    for _, item in iter_items():
        ans = answers.get(item["id"])

        # 未回答(None)も unknown と同じ扱い
        if ans in ("no", "unknown") or ans is None:
            risk = item.get("risk", "medium")
            if risk not in counts:
                risk = "medium"
            counts[risk] += 1

    overall = overall_judgement(counts)
    section_summary, section_summary_by_id = build_section_summary(answers)
    sections = build_rows_by_section(answers, section_summary_by_id)
    all_rows = build_rows_all(answers)  # 互換用（テンプレが参照してもOK）

    return {
        "overall": overall,
        "counts": counts,
        "all_rows": all_rows,
        "section_summary": section_summary,
        "sections": sections,
        "is_pdf": is_pdf,  # ✅ テンプレが open 判定に使う
    }


# --------------------------
# ルーティング
# --------------------------
@app.route("/")
def index():
    return redirect(url_for("start"))


@app.route("/check", methods=["GET", "POST"])
def start():
    if request.method == "POST":
        session["answers"] = {}
        return redirect(url_for("section", idx=0))
    return render_template("start.html", total_sections=len(SECTIONS), choices=CHOICES)


@app.route("/check/q/<int:idx>", methods=["GET", "POST"])
def section(idx: int):
    if idx < 0 or idx >= len(SECTIONS):
        return redirect(url_for("result"))

    answers = session.get("answers", {}) or {}
    sec = SECTIONS[idx]

    if request.method == "POST":
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
        return redirect(url_for("result"))

    progress = {"current": idx + 1, "total": len(SECTIONS)}
    return render_template(
        "section.html",
        sec=sec,
        sec_items=sec["items"],
        idx=idx,
        answers=answers,
        progress=progress,
        choices=CHOICES,
    )


@app.route("/check/result")
def result():
    ctx = build_result_context(is_pdf=False)
    return render_template("result.html", **ctx)


# ✅ PDF用：展開済みHTML（CSS相対パスが自然に効く）
@app.get("/check/result/print")
def result_print():
    ctx = build_result_context(is_pdf=True)
    return render_template("result.html", **ctx)


# ✅ PDF生成：/check/result/print を開いてPDF化（最安定）
@app.get("/check/result/pdf")
def result_pdf():
    print_url = request.url_root.rstrip("/") + "/check/result/print"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(print_url, wait_until="networkidle")
        page.wait_for_timeout(200)  # 念のため

        pdf_bytes = page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "12mm", "right": "12mm", "bottom": "12mm", "left": "12mm"},
        )
        browser.close()

    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = 'attachment; filename="security_check_result.pdf"'
    return resp


if __name__ == "__main__":
    validate_questions(raise_on_error=True)
    app.run(debug=True)
