"""
KdB Syllabus Scraper
筑波大学のKdBからシラバス情報をスクレイピングするスクリプト
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Optional
import httpx
from bs4 import BeautifulSoup
import pandas as pd


# 科目分類マッピング
CATEGORY_MAP = {
    "1": "総合科目・学士基盤科目",
    "2": "体育",
    "3": "英語",
    "4": "初修外国語（独・中）",
    "5": "初修外国語（仏・露・西）",
    "6": "情報",
    "7": "芸術",
    "8": "自由科目",
    "9": "教職・博物館",
    "A": "人文・文化学群",
    "B": "社会・国際学群",
    "C": "人間学群",
    "E": "生命環境学群",
    "F": "理工学群",
    "G": "情報学群",
    "H": "医学群",
    "W": "体育専門学群",
    "T": "体育専門学群",
    "Y": "芸術専門学群",
    "V": "グローバル教育院",
}


def get_category(course_number: str) -> str:
    """科目番号から分類を取得"""
    if not course_number:
        return "その他"
    first_char = course_number[0].upper()
    return CATEGORY_MAP.get(first_char, "その他")


def get_category_type(course_number: str) -> str:
    """科目番号から共通/専門を判定"""
    if not course_number:
        return "その他"
    first_char = course_number[0]
    if first_char.isdigit():
        return "共通科目"
    elif first_char.isalpha():
        return "専門科目"
    return "その他"


async def fetch_syllabus(client: httpx.AsyncClient, course_number: str, year: int = 2025) -> Optional[dict]:
    """シラバス詳細を取得"""
    url = f"https://kdb.tsukuba.ac.jp/syllabi/{year}/{course_number}/jpn/0/"
    
    try:
        response = await client.get(url, timeout=30.0)
        if response.status_code != 200:
            return None
        
        # Decode content as UTF-8
        html_content = response.content.decode('utf-8')
        soup = BeautifulSoup(html_content, "html.parser")
        
        # タイトル抽出 (例: "GA10101   情報社会と法制度")
        title_elem = soup.find("h1")
        if not title_elem:
            return None
        
        title_text = title_elem.get_text(strip=True)
        # 科目番号と科目名を分離
        parts = title_text.split(None, 1)
        course_name = parts[1] if len(parts) > 1 else title_text
        
        # 基本情報抽出 (例: "2.0 単位, 2 年次, 秋AB 月5,6 髙良 幸哉")
        subtitle_elem = soup.find("h1").find_next_sibling(string=True) or soup.find("h1").find_next("p")
        subtitle = ""
        if subtitle_elem:
            if hasattr(subtitle_elem, 'get_text'):
                subtitle = subtitle_elem.get_text(strip=True)
            else:
                subtitle = str(subtitle_elem).strip()
        
        # 各セクションを抽出
        sections = {}
        current_section = None
        
        for elem in soup.find_all(["h2", "p"]):
            if elem.name == "h2":
                current_section = elem.get_text(strip=True)
                sections[current_section] = ""
            elif elem.name == "p" and current_section:
                text = elem.get_text(strip=True)
                if text:
                    sections[current_section] += text + "\n"
        
        # 単位・年次の抽出
        credits = ""
        year_level = ""
        term = ""
        instructor = ""
        
        if subtitle:
            # "2.0 単位" パターン
            credits_match = re.search(r"([\d.]+)\s*単位", subtitle)
            if credits_match:
                credits = credits_match.group(1)
            
            # "2 年次" パターン
            year_match = re.search(r"(\d+)\s*年次", subtitle)
            if year_match:
                year_level = year_match.group(1)
            
            # 開講時期 (春AB, 秋ABC など)
            term_match = re.search(r"[春秋通][ABC]+", subtitle)
            if term_match:
                term = term_match.group(0)
        
        return {
            "course_number": course_number,
            "course_name": course_name,
            "credits": credits,
            "year_level": year_level,
            "term": term,
            "instructor": sections.get("担当教員", "").strip() or subtitle.split()[-1] if subtitle else "",
            "category": get_category(course_number),
            "category_type": get_category_type(course_number),
            "overview": sections.get("授業概要", "").strip(),
            "objectives": sections.get("授業の到達目標・学修成果", "").strip(),
            "keywords": sections.get("キーワード", "").strip(),
            "schedule": sections.get("授業計画", "").strip(),
            "grading": sections.get("成績評価方法", "").strip(),
            "prerequisites": sections.get("履修条件", "").strip(),
            "remarks": sections.get("備考", "").strip(),
            "competence": sections.get("コンピテンス", "").strip(),
            "study_time": sections.get("学修時間の割当・授業外における学修方法", "").strip(),
            "materials": sections.get("教材・参考文献・配付資料等", "").strip(),
            "office_hours": sections.get("オフィスアワー等・連絡先", "").strip(),
            "method": sections.get("授業方法", "").strip(),
        }
        
    except Exception as e:
        print(f"Error fetching {course_number}: {e}")
        return None


async def scrape_syllabi(course_numbers: list[str], max_concurrent: int = 10, delay: float = 0.1) -> list[dict]:
    """複数のシラバスを非同期でスクレイピング"""
    results = []
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch_with_semaphore(client: httpx.AsyncClient, course_number: str) -> Optional[dict]:
        async with semaphore:
            result = await fetch_syllabus(client, course_number)
            await asyncio.sleep(delay)  # サーバー負荷軽減
            return result
    
    async with httpx.AsyncClient() as client:
        tasks = [fetch_with_semaphore(client, cn) for cn in course_numbers]
        
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            result = await coro
            if result:
                results.append(result)
            
            # 進捗表示
            if (i + 1) % 100 == 0:
                print(f"Progress: {i + 1}/{len(course_numbers)} ({len(results)} successful)")
    
    return results


async def fetch_details_for_courses(
    course_numbers: list[str],
    base_syllabi: dict[str, dict] = None,
    year: int = 2025,
) -> list[dict]:
    """
    指定した科目番号の詳細情報をオンデマンドでスクレイピング
    
    Args:
        course_numbers: 科目番号のリスト（上位5件など）
        base_syllabi: XLSXから取得した基本情報（科目番号→シラバス辞書）
        year: 年度
        
    Returns:
        詳細情報を追加したシラバスリスト
    """
    if base_syllabi is None:
        base_syllabi = {}
    
    results = []
    
    async with httpx.AsyncClient() as client:
        for course_number in course_numbers:
            # KdBから詳細をスクレイピング
            detailed = await fetch_syllabus(client, course_number, year)
            
            if detailed:
                # XLSXの基本情報があればマージ
                base_info = base_syllabi.get(course_number, {})
                
                # XLSXから取得できる情報を優先し、足りない情報をスクレイピングで補完
                merged = {
                    "course_number": course_number,
                    "course_name": base_info.get("course_name") or detailed.get("course_name", ""),
                    "credits": base_info.get("credits") or detailed.get("credits", ""),
                    "year_level": base_info.get("year_level") or detailed.get("year_level", ""),
                    "term": base_info.get("term") or detailed.get("term", ""),
                    "day_period": base_info.get("day_period", ""),
                    "classroom": base_info.get("classroom", ""),
                    "instructor": base_info.get("instructor") or detailed.get("instructor", ""),
                    "delivery_method": base_info.get("delivery_method", ""),
                    "category": base_info.get("category") or detailed.get("category", ""),
                    "category_type": base_info.get("category_type") or detailed.get("category_type", ""),
                    # スクレイピングでのみ取得できる詳細情報
                    "overview": base_info.get("overview") or detailed.get("overview", ""),
                    "objectives": detailed.get("objectives", ""),
                    "keywords": detailed.get("keywords", ""),
                    "schedule": detailed.get("schedule", ""),
                    "grading": detailed.get("grading", ""),
                    "prerequisites": detailed.get("prerequisites", ""),
                    "remarks": detailed.get("remarks", ""),
                    "competence": detailed.get("competence", ""),
                    "study_time": detailed.get("study_time", ""),
                    "materials": detailed.get("materials", ""),
                    "office_hours": detailed.get("office_hours", ""),
                    "method": detailed.get("method", ""),
                }
                results.append(merged)
            else:
                # スクレイピング失敗時はXLSXの基本情報のみ使用
                if course_number in base_syllabi:
                    results.append(base_syllabi[course_number])
    
    return results


def load_course_numbers_from_excel(excel_path: str) -> list[str]:
    """ExcelファイルからSyllabus番号を読み込む"""
    df = pd.read_excel(excel_path, header=None, skiprows=5)
    course_numbers = df[0].dropna().astype(str).tolist()
    # 重複を除去
    return list(set(course_numbers))


async def main():
    """メイン実行"""
    # Excelから科目番号を読み込み
    excel_path = Path(__file__).parent.parent / "courses.xlsx"
    
    if not excel_path.exists():
        print(f"Error: {excel_path} not found")
        return
    
    course_numbers = load_course_numbers_from_excel(str(excel_path))
    print(f"Found {len(course_numbers)} unique course numbers")
    
    # テスト用に最初の50件だけ取得（本番では全件）
    # course_numbers = course_numbers[:50]
    
    # スクレイピング実行
    print("Starting scrape...")
    syllabi = await scrape_syllabi(course_numbers, max_concurrent=5, delay=0.2)
    
    # 結果を保存
    output_path = Path(__file__).parent / "data" / "syllabi.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(syllabi, f, ensure_ascii=False, indent=2)
    
    print(f"Saved {len(syllabi)} syllabi to {output_path}")
    
    # 統計表示
    categories = {}
    for s in syllabi:
        cat = s["category"]
        categories[cat] = categories.get(cat, 0) + 1
    
    print("\nCategory breakdown:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    asyncio.run(main())
