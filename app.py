from __future__ import annotations

from collections import defaultdict

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    make_response,
    send_from_directory,
)
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
from ai_questions_short import AI_SECTIONS_SHORT

# --------------------------
# Flask 初期化
# --------------------------
app = Flask(__name__, static_folder="static")
app.secret_key = "change-me"  # 本番は環境変数へ


from flask import send_from_directory

@app.route("/favicon.ico")
def favicon():
    return send_from_directory("static", "favicon.ico", mimetype="image/x-icon")


# --------------------------
# robots / sitemap
# --------------------------
@app.get("/robots.txt")
def robots_txt():
    return send_from_directory(app.static_folder, "robots.txt", mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap_xml():
    return send_from_directory(
        app.static_folder, "sitemap.xml", mimetype="application/xml"
    )


# --------------------------
# 集計・結果生成ロジック
# --------------------------
RISK_RESULT_LABELS = {
    "high": "優先的に整理したい項目があります",
    "medium": "確認したい項目があります",
    "low": "おおむね整理されています",
}


def overall_judgement(counts: dict) -> dict:
    if counts["high"] > 0:
        return {
            "code": RISK_RESULT_LABELS["high"],
            "tone": "high",
            "message": "優先的に整理したい項目があります。",
            "lead": "すべてを一度に進めるのではなく、管理者・記録場所・相談先から整理するのがおすすめです。",
        }
    if counts["medium"] > 0:
        return {
            "code": RISK_RESULT_LABELS["medium"],
            "tone": "medium",
            "message": "いくつか確認しておきたい項目があります。",
            "lead": "現在の運用状況を言語化し、無理なく確認できる形にしていきましょう。",
        }
    if counts["low"] > 0:
        return {
            "code": RISK_RESULT_LABELS["low"],
            "tone": "low",
            "message": "おおむね整理されています。",
            "lead": "運用が変わったタイミングで、記録や担当を見直しておくと安心です。",
        }
    return {
        "code": RISK_RESULT_LABELS["low"],
        "tone": "low",
        "message": "おおむね整理されています。",
        "lead": "現在の運用を維持しつつ、定期的に見直しましょう。",
    }


def build_section_summary(answers: dict, sections=SECTIONS):
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

    for sec, item in iter_items(sections):
        sid = sec["id"]
        qid = item["id"]

        ans = answers.get(qid, "unknown")
        if ans not in VALID_ANSWERS:
            ans = "unknown"

        risk = item.get("risk", "medium")
        if risk not in RISK_LABELS:
            risk = "medium"

        s = summary[sid]
        s["section_id"] = sid
        s["title"] = sec["title"]
        s["total"] += 1
        s["answers"][ans] += 1

        show_if = item.get("show_if_answer_in", ["no", "unknown"])
        if ans in show_if:
            s["hit_total"] += 1
            s["hit_by_risk"][risk] += 1

    rows = [summary[sec["id"]] for sec in sections]
    by_id = {r["section_id"]: r for r in rows}
    return rows, by_id


def build_rows_by_section(answers: dict, summary_by_id: dict, sections=SECTIONS):
    buckets = []

    for sec in sections:
        rows = []
        for item in sec["items"]:
            qid = item["id"]
            ans = answers.get(qid, "unknown")
            if ans not in VALID_ANSWERS:
                ans = "unknown"

            risk = item.get("risk", "medium")
            if risk not in RISK_LABELS:
                risk = "medium"

            res = {}
            if "result_by_answer" in item:
                res = item["result_by_answer"].get(ans, {}) or {}
            if not res:
                res = item.get("result", {}) or {}

            rows.append(
                {
                    "risk": risk,
                    "risk_label": RISK_RESULT_LABELS.get(
                        risk, RISK_RESULT_LABELS["medium"]
                    ),
                    "question": item["q"],
                    "answer": ans,
                    "answer_label": ANSWER_LABEL.get(ans, ans),
                    "title": res.get("title", ""),
                    "why": res.get("why", ""),
                    "next": res.get("next", []),
                }
            )

        ssum = summary_by_id.get(sec["id"], {})
        buckets.append(
            {
                "section_id": sec["id"],
                "title": sec["title"],
                "total": ssum.get("total", len(rows)),
                "hit_total": ssum.get("hit_total", 0),
                "ok_total": ssum.get("answers", {}).get("yes", 0),
                "confirm_total": ssum.get("hit_total", 0),
                "hit_by_risk": ssum.get(
                    "hit_by_risk", {"high": 0, "medium": 0, "low": 0}
                ),
                "answers": ssum.get(
                    "answers", {"yes": 0, "no": 0, "unknown": 0}
                ),
                "rows": rows,
            }
        )

    return buckets


def build_result_context(
    sections=SECTIONS,
    answers: dict | None = None,
    is_pdf: bool = False,
) -> dict:
    if answers is None:
        answers = session.get("answers", {}) or {}
    counts = {"high": 0, "medium": 0, "low": 0}

    for _, item in iter_items(sections):
        ans = answers.get(item["id"])
        if ans in ("no", "unknown", None):
            risk = item.get("risk", "medium")
            if risk not in counts:
                risk = "medium"
            counts[risk] += 1

    overall = overall_judgement(counts)
    section_summary, section_summary_by_id = build_section_summary(answers, sections)
    rows = build_rows_by_section(answers, section_summary_by_id, sections)
    total_ok = sum(s["answers"]["yes"] for s in section_summary)
    total_confirm = sum(counts.values())

    return {
        "overall": overall,
        "counts": counts,
        "total_ok": total_ok,
        "total_confirm": total_confirm,
        "section_summary": section_summary,
        "sections": rows,
        "is_pdf": is_pdf,
        "contact_url": "https://aokishoji.com/contact",
        "lawoffice_url": "https://aokishoji.com/lawoffice",
    }


# =====================================================
# 診断エンジン共通処理（設問セットを引数で受け取る）
# =====================================================
#
# 既存の弁護士向け診断と新規のAI診断は、設問セット（SECTIONS）と
# セッションキー・ルート名・テンプレ用の見た目（kind）が違うだけなので、
# 中身のロジックは下記の共通関数に集約する。
# -----------------------------------------------------


def _render_section(
    idx: int,
    sections: list,
    answers_key: str,
    section_endpoint: str,
    start_url: str,
    result_endpoint: str,
    kind: str,
):
    """設問ページの共通処理（弁護士／AI 共用）。"""
    if idx < 0:
        return redirect(start_url)
    if idx >= len(sections):
        return redirect(url_for(result_endpoint))

    answers = session.get(answers_key, {}) or {}
    sec = sections[idx]

    if request.method == "POST":
        for item in sec["items"]:
            key = item["id"]
            val = request.form.get(key)
            if val in VALID_ANSWERS:
                answers[key] = val

        session[answers_key] = answers

        if "prev" in request.form:
            return redirect(url_for(section_endpoint, idx=idx - 1))
        if "next" in request.form:
            return redirect(url_for(section_endpoint, idx=idx + 1))
        return redirect(url_for(result_endpoint))

    progress = {"current": idx + 1, "total": len(sections)}
    return render_template(
        "section.html",
        sec=sec,
        sec_items=sec["items"],
        idx=idx,
        answers=answers,
        progress=progress,
        choices=CHOICES,
        section_endpoint=section_endpoint,
        start_url=start_url,
        kind=kind,
    )


def _render_result(
    sections: list,
    answers_key: str,
    is_pdf: bool,
    kind: str,
    start_url: str,
    pdf_url: str,
    branch: str | None = None,
):
    """結果ページの共通処理（弁護士／AI 共用）。"""
    answers = session.get(answers_key, {}) or {}
    ctx = build_result_context(sections=sections, answers=answers, is_pdf=is_pdf)
    ctx.update(
        kind=kind,
        start_url=start_url,
        pdf_url=pdf_url,
        branch=branch,
    )
    return render_template("result.html", **ctx)


def _generate_result_pdf(print_path: str, filename: str):
    """結果HTMLをPlaywrightでPDF化する共通処理（弁護士／AI 共用）。"""
    print_url = request.url_root.rstrip("/") + print_path
    session_cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
    session_cookie = request.cookies.get(session_cookie_name)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        if session_cookie:
            context.add_cookies(
                [
                    {
                        "name": session_cookie_name,
                        "value": session_cookie,
                        "url": request.url_root.rstrip("/"),
                    }
                ]
            )
        page = context.new_page()
        page.goto(print_url, wait_until="networkidle")
        page.wait_for_timeout(200)

        pdf_bytes = page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "12mm", "right": "12mm", "bottom": "12mm", "left": "12mm"},
        )
        context.close()
        browser.close()

    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


# =====================================================
# ルーティング（★重複なし）
# =====================================================

# ① トップ → SEO LP
@app.get("/")
def index():
    return redirect(url_for("start_lawyer_it_risk"), code=302)


# =====================================================
# A. 弁護士事務所向け ITリスク・セキュリティ自己診断
# =====================================================

# ② SEO用 LP
@app.get("/lawyer-it-risk")
def start_lawyer_it_risk():
    return render_template(
        "start_lawyer_it_risk.html",
        total_sections=len(SECTIONS),
        choices=CHOICES,
    )


# ③ 診断スタート
@app.route("/check", methods=["GET", "POST"])
def start_check():
    if request.method == "POST":
        session["answers"] = {}
        return redirect(url_for("check_section", idx=0))

    return render_template(
        "start.html",
        total_sections=len(SECTIONS),
        choices=CHOICES,
    )


# ④ 設問ページ
@app.route("/check/q/<int:idx>", methods=["GET", "POST"])
def check_section(idx: int):
    return _render_section(
        idx=idx,
        sections=SECTIONS,
        answers_key="answers",
        section_endpoint="check_section",
        start_url=url_for("start_check"),
        result_endpoint="result",
        kind="lawyer",
    )


# ⑤ 結果画面
@app.get("/check/result")
def result():
    return _render_result(
        sections=SECTIONS,
        answers_key="answers",
        is_pdf=False,
        kind="lawyer",
        start_url=url_for("start_check"),
        pdf_url=url_for("result_pdf"),
    )


# ⑥ PDF表示用（HTML）
@app.get("/check/result/print")
def result_print():
    return _render_result(
        sections=SECTIONS,
        answers_key="answers",
        is_pdf=True,
        kind="lawyer",
        start_url=url_for("start_check"),
        pdf_url=url_for("result_pdf"),
    )


# ⑦ PDF生成
@app.get("/check/result/pdf")
def result_pdf():
    return _generate_result_pdf(
        print_path="/check/result/print",
        filename="security_check_result.pdf",
    )


# =====================================================
# B. 士業向け AI安全活用 セルフチェック
# =====================================================

# ① SEO用 LP
@app.get("/shigyo-ai-check")
def start_shigyo_ai_check():
    total_questions = sum(len(sec["items"]) for sec in AI_SECTIONS_SHORT)
    return render_template(
        "start_shigyo_ai_check.html",
        total_sections=len(AI_SECTIONS_SHORT),
        total_questions=total_questions,
        choices=CHOICES,
    )


# ② 診断スタート（LPのボタンから POST）
@app.post("/shigyo-ai-check/start")
def ai_start_check():
    session["ai_answers"] = {}
    return redirect(url_for("ai_check_section", idx=0))


# ③ 設問ページ
@app.route("/shigyo-ai-check/q/<int:idx>", methods=["GET", "POST"])
def ai_check_section(idx: int):
    return _render_section(
        idx=idx,
        sections=AI_SECTIONS_SHORT,
        answers_key="ai_answers",
        section_endpoint="ai_check_section",
        start_url=url_for("start_shigyo_ai_check"),
        result_endpoint="ai_result",
        kind="ai",
    )


# ④ 結果画面
@app.get("/shigyo-ai-check/result")
def ai_result():
    return _render_result(
        sections=AI_SECTIONS_SHORT,
        answers_key="ai_answers",
        is_pdf=False,
        kind="ai",
        start_url=url_for("start_shigyo_ai_check"),
        pdf_url=url_for("ai_result_pdf"),
        branch="ai",
    )


# ⑤ PDF表示用（HTML）
@app.get("/shigyo-ai-check/result/print")
def ai_result_print():
    return _render_result(
        sections=AI_SECTIONS_SHORT,
        answers_key="ai_answers",
        is_pdf=True,
        kind="ai",
        start_url=url_for("start_shigyo_ai_check"),
        pdf_url=url_for("ai_result_pdf"),
        branch="ai",
    )


# ⑥ PDF生成
@app.get("/shigyo-ai-check/result/pdf")
def ai_result_pdf():
    return _generate_result_pdf(
        print_path="/shigyo-ai-check/result/print",
        filename="shigyo_ai_check_result.pdf",
    )


# --------------------------
# 起動
# --------------------------
if __name__ == "__main__":
    validate_questions(raise_on_error=True)
    validate_questions(raise_on_error=True, sections=AI_SECTIONS_SHORT)
    app.run(debug=True)
