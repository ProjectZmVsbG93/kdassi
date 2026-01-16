"""
XLSX Parser Module
KdBからエクスポートしたXLSXファイルを解析
"""

import pandas as pd
from pathlib import Path
from typing import Optional
import io


# XLSXの列マッピング
COLUMN_MAPPING = {
    0: "course_number",    # A列: 科目番号
    1: "course_name",      # B列: 科目名
    3: "credits",          # D列: 単位数
    4: "year_level",       # E列: 標準履修年次
    5: "term",             # F列: 実施時期
    6: "day_period",       # G列: 曜時限
    7: "classroom",        # H列: 教室
    8: "instructor",       # I列: 担当教員
    9: "overview",         # J列: 授業概要
    10: "delivery_method", # K列: 対面/オンライン
}


def parse_xlsx(file_path_or_bytes, skip_header: bool = True) -> list[dict]:
    """
    XLSXファイルを解析してシラバス情報のリストを返す
    
    Args:
        file_path_or_bytes: ファイルパスまたはバイトデータ
        skip_header: ヘッダー行をスキップするかどうか
        
    Returns:
        シラバス情報のリスト
    """
    # ファイルまたはバイトデータを読み込み
    if isinstance(file_path_or_bytes, (str, Path)):
        df = pd.read_excel(file_path_or_bytes, header=None)
    else:
        # バイトデータの場合
        df = pd.read_excel(io.BytesIO(file_path_or_bytes), header=None)
    
    # ヘッダー行をスキップ
    if skip_header and len(df) > 0:
        df = df.iloc[1:]
    
    syllabi = []
    
    for _, row in df.iterrows():
        syllabus = {}
        
        for col_idx, field_name in COLUMN_MAPPING.items():
            if col_idx < len(row):
                value = row.iloc[col_idx]
                # NaN を空文字列に変換
                if pd.isna(value):
                    value = ""
                else:
                    value = str(value).strip()
                syllabus[field_name] = value
            else:
                syllabus[field_name] = ""
        
        # 科目番号が空の行はスキップ
        if not syllabus.get("course_number"):
            continue
        
        # カテゴリを推定（科目番号の先頭文字から）
        syllabus["category"] = estimate_category(syllabus["course_number"])
        syllabus["category_type"] = estimate_category_type(syllabus["course_number"])
        
        syllabi.append(syllabus)
    
    return syllabi


def estimate_category(course_number: str) -> str:
    """科目番号からカテゴリを推定"""
    if not course_number:
        return "その他"
    
    prefix = course_number[0].upper()
    
    category_map = {
        "1": "総合科目・学士基盤科目",
        "2": "体育",
        "3": "英語",
        "A": "人文・文化学群",
        "B": "社会・国際学群",
        "C": "人間学群",
        "E": "生命環境学群",
        "F": "理工学群",
        "G": "情報学群",
        "H": "医学群",
        "W": "体育専門学群",
        "Y": "芸術専門学群",
        "V": "グローバル教育院",
    }
    
    return category_map.get(prefix, "その他")


def estimate_category_type(course_number: str) -> str:
    """科目番号からカテゴリタイプを推定"""
    if not course_number:
        return "その他"
    
    prefix = course_number[0].upper()
    
    # 1-9で始まる: 共通科目
    # アルファベットで始まる: 専門科目
    if prefix.isdigit():
        return "共通科目"
    else:
        return "専門科目"


def create_document_text(syllabus: dict) -> str:
    """シラバスから検索用ドキュメントテキストを生成"""
    parts = [
        f"科目名: {syllabus.get('course_name', '')}",
        f"科目番号: {syllabus.get('course_number', '')}",
        f"分類: {syllabus.get('category', '')} ({syllabus.get('category_type', '')})",
        f"単位: {syllabus.get('credits', '')}単位",
        f"対象年次: {syllabus.get('year_level', '')}年次",
        f"開講時期: {syllabus.get('term', '')}",
        f"曜時限: {syllabus.get('day_period', '')}",
        f"教室: {syllabus.get('classroom', '')}",
        f"担当教員: {syllabus.get('instructor', '')}",
        f"授業形態: {syllabus.get('delivery_method', '')}",
    ]
    
    if syllabus.get("overview"):
        parts.append(f"授業概要: {syllabus['overview']}")
    
    return "\n".join(parts)


if __name__ == "__main__":
    # テスト
    import sys
    
    if len(sys.argv) > 1:
        xlsx_path = sys.argv[1]
        syllabi = parse_xlsx(xlsx_path)
        print(f"Parsed {len(syllabi)} courses")
        
        if syllabi:
            print("\nFirst course:")
            for key, value in syllabi[0].items():
                print(f"  {key}: {value[:50] if len(str(value)) > 50 else value}")
    else:
        print("Usage: python xlsx_parser.py <xlsx_file>")
