# questions.py
# ============================================================
# 弁護士事務所向け ITリスク自己診断
# 方針：
# - リスク判定は「設問ごとに固定」（回答で高/中を変えない）
# - 回答が yes の場合は「問題なし」なので結果表示しない
# - no / unknown はどちらも「対応が必要」扱い（表示する）
# ============================================================

from __future__ import annotations
from typing import Dict, List, Optional, TypedDict


# ----------------------------
# 回答選択肢（UI・ロジック共通）
# ----------------------------
CHOICES = [
    {"value": "yes", "label": "はい"},
    {"value": "no", "label": "いいえ"},
    {"value": "unknown", "label": "わからない"},
]

ANSWER_LABEL: Dict[str, str] = {c["value"]: c["label"] for c in CHOICES}
VALID_ANSWERS = set(ANSWER_LABEL.keys())

# 「結果に表示する」対象（= 対応が必要扱い）
DISPLAY_ANSWERS = {"no", "unknown"}


# ----------------------------
# リスク表現（点数は使わない）
# ----------------------------
RISK_LABELS = {
    "high": {
        "label": "高",
        "desc": "情報漏えい・業務停止に直結する可能性があります",
    },
    "medium": {
        "label": "中",
        "desc": "条件次第で事故につながる可能性があります",
    },
    "low": {
        "label": "低",
        "desc": "今すぐではありませんが、整理すると安心です",
    },
}
VALID_RISKS = set(RISK_LABELS.keys())


# ----------------------------
# 型（任意：なくても動くが、拡張時に事故りにくい）
# ----------------------------
class ResultBlock(TypedDict, total=False):
    title: str
    why: str
    next: List[str]


class Item(TypedDict, total=False):
    id: str
    q: str
    risk: str  # "high" | "medium" | "low"（設問固定）
    show_if_answer_in: List[str]  # 通常は ["no","unknown"]
    # 回答によって文章を変えたい場合は answer キーで分岐できるようにする
    # 例: "no" と "unknown" で title/why/next を変える
    result_by_answer: Dict[str, ResultBlock]
    # 共通の結果（no/unknownで同一ならこれだけでOK）
    result: ResultBlock


class Section(TypedDict, total=False):
    id: str
    title: str
    items: List[Item]


# ----------------------------
# 診断セクション定義（PDFの設問をこの形式に写経して増やしていく）
# ----------------------------
SECTIONS: List[Section] = [
    {
        "id": "device",
        "title": "① 端末・アカウント管理",
        "items": [
            # -------------------------
            # ①-1 端末の利用ルール
            # -------------------------
            {
                "id": "device_01",
                "group": "①-1 端末の利用ルール",
                "q": "業務に使うPC・スマートフォン・タブレットの範囲（事務所所有／個人所有など）が明確に決まっている",
                "risk": "medium",
                "show_if_answer_in": ["no", "unknown"],
                "result": {
                    "title": "端末の利用範囲が曖昧です（区分を決める）",
                    "why": "業務利用端末の範囲が曖昧だと、紛失・故障・退職時に回収や対応が遅れ、情報漏えいの入口になります。",
                    "next": [
                        "業務利用を「事務所支給端末／個人端末（例外）」に区分する",
                        "個人端末利用は原則禁止、例外時は所長承認制にする",
                        "一覧表（簡易でOK）を作成する",
                    ],
                },
            },
            {
                "id": "device_02",
                "group": "①-1 端末の利用ルール",
                "q": "個人所有端末を業務で使う場合のルール（申請方法・セキュリティ対策義務など）が定められている",
                "risk": "high",
                "show_if_answer_in": ["no", "unknown"],
                "result": {
                    "title": "BYOD（私物利用）の統制が不足しています",
                    "why": "私物端末は管理が難しく、紛失・第三者利用・設定不備がそのまま事故につながります。",
                    "next": [
                        "BYOD（私物利用）を許可する／しないを明文化する",
                        "許可する場合：パスコード設定必須／紛失時の即時報告ルールを定める",
                        "文書1枚で十分（所内共有）",
                    ],
                },
            },
            {
                "id": "device_03",
                "group": "①-1 端末の利用ルール",
                "q": "事務所で使うPCやスマートフォンにウイルス対策ソフトが導入され、常に最新の状態になっている",
                "risk": "high",
                "show_if_answer_in": ["no", "unknown"],
                "result": {
                    "title": "ウイルス対策の運用が不明確です（棚卸し→確認者決定）",
                    "why": "未導入・未更新はマルウェア感染や情報漏えいのリスクを高めます。",
                    "next": [
                        "利用中のセキュリティソフトを棚卸しする",
                        "「自動更新されているか」を確認する",
                        "管理者（誰が確認するか）を決める",
                    ],
                },
            },

            # -------------------------
            # ①-2 アカウント管理
            # -------------------------
            {
                "id": "device_04",
                "group": "①-2 アカウント管理",
                "q": "新しい職員が入所した際に、PCや各種システムのアカウントを発行する手順が決まっている",
                "risk": "high",
                "show_if_answer_in": ["no", "unknown"],
                "result": {
                    "title": "入所時のアカウント発行が属人化しています",
                    "why": "手順がないと発行漏れ・権限の過不足が発生しやすく、業務停滞や情報漏えいにつながります。",
                    "next": [
                        "入所時チェックリストを作成する",
                        "PC／メール／クラウドの発行有無を記載する",
                        "発行責任者を1名決める",
                    ],
                },
            },
            {
                "id": "device_05",
                "group": "①-2 アカウント管理",
                "q": "職員が退職・異動する際に、利用していたアカウントを速やかに停止・削除する手順が決まっている",
                "risk": "high",
                "show_if_answer_in": ["no", "unknown"],
                "result": {
                    "title": "退職・異動時の停止ルールが不十分です",
                    "why": "アカウントが残ると、なりすまし・持ち出し・誤操作のリスクが高まります。",
                    "next": [
                        "退職日当日に停止するルールを明文化する",
                        "メール／クラウド／VPNの停止対象を一覧化する",
                        "人事イベントとIT対応を紐づける",
                    ],
                },
            },
            {
                "id": "device_06",
                "group": "①-2 アカウント管理",
                "q": "事務所で利用しているクラウドサービス（ファイル共有、Web会議など）の一覧を把握している",
                "risk": "medium",
                "show_if_answer_in": ["no", "unknown"],
                "result": {
                    "title": "利用サービスの把握が不十分です（棚卸し）",
                    "why": "利用サービスが見えないと、権限・データ保管・退職時停止の対象が漏れます。",
                    "next": [
                        "Google Drive／OneDrive／Zoom等を洗い出す",
                        "「公式利用／個人利用」を区別する",
                        "不要なサービスは今後使わない方針にする",
                    ],
                },
            },

            # -------------------------
            # ①-3 パスワード・責任者
            # -------------------------
            {
                "id": "device_07",
                "group": "①-3 パスワード・責任者",
                "q": "パスワードの作り方や管理に関する簡単なルール（使い回しをしない等）がある",
                "risk": "high",
                "show_if_answer_in": ["no", "unknown"],
                "result": {
                    "title": "パスワード運用ルールが不足しています",
                    "why": "使い回し・弱いパスワードは不正ログインの典型的な入口になります。",
                    "next": [
                        "使い回し禁止を明文化する",
                        "推測されやすいパスワード禁止を明文化する",
                        "管理方法（紙NG等）を決める",
                    ],
                },
            },
            {
                "id": "device_08",
                "group": "①-3 パスワード・責任者",
                "q": "誰がPCやアカウント管理の最終的な責任者か明確に決まっている",
                "risk": "high",
                "show_if_answer_in": ["no", "unknown"],
                "result": {
                    "title": "最終責任者が不明確です（判断の迷いをなくす）",
                    "why": "責任者が曖昧だと、事故時の判断が遅れ、対応が属人化します。",
                    "next": [
                        "最終責任者を所長または指定職員に固定する",
                        "「判断に迷ったら誰か」を明文化する",
                    ],
                },
            },
        ],
    },
    {
        "id": "backup",
        "title": "② データ・バックアップ",
        "items": [
            {
                "id": "backup_01",
                "q": "重要データの保管場所が誰でも分かる形で決まっていますか？",
                "risk": "high",
                "show_if_answer_in": ["no", "unknown"],
                "result": {
                    "title": "データの保管場所が不明確です",
                    "why": "復旧時に探すところから始まり、業務再開が遅れます。",
                    "next": [
                        "重要データの保管先を一覧化する（フォルダ構成まで不要）",
                        "「案件データ／依頼者情報／保存先」を避ける項目を決める（例：PC内のみ保存を避ける）",
                    ],
                },
            },
        ],
    },
]


# ----------------------------
# 追加：ユーティリティ（app.py 側で使うと便利）
# ----------------------------
def iter_items():
    """全設問をフラットに回す（集計や結果生成で便利）"""
    for sec in SECTIONS:
        for item in sec.get("items", []):
            yield sec, item


def validate_questions(raise_on_error: bool = True) -> List[str]:
    """設問定義のミスを早期発見（ID重複や risk の誤字など）"""
    errors: List[str] = []
    seen_item_ids = set()

    for sec in SECTIONS:
        sid = sec.get("id")
        stitle = sec.get("title")
        if not sid or not stitle:
            errors.append("section に id/title がありません")
            continue

        for item in sec.get("items", []):
            iid = item.get("id")
            q = item.get("q")
            risk = item.get("risk")
            show = item.get("show_if_answer_in", ["no", "unknown"])

            if not iid or not q:
                errors.append(f"{sid}: item に id/q がありません")
                continue

            if iid in seen_item_ids:
                errors.append(f"設問IDが重複しています: {iid}")
            seen_item_ids.add(iid)

            if risk not in VALID_RISKS:
                errors.append(f"{iid}: risk が不正です: {risk}（{VALID_RISKS}）")

            for a in show:
                if a not in VALID_ANSWERS:
                    errors.append(f"{iid}: show_if_answer_in に不正な回答値: {a}")

            # result / result_by_answer のどちらかは欲しい
            if "result" not in item and "result_by_answer" not in item:
                errors.append(f"{iid}: result または result_by_answer がありません")

    if raise_on_error and errors:
        raise ValueError("questions.py 定義エラー:\n- " + "\n- ".join(errors))

    return errors
