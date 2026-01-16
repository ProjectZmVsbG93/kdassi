"""
Test scraper with limited data
"""

import asyncio
import json
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from scraper import scrape_syllabi, load_course_numbers_from_excel


async def test_scrape():
    """テスト用に少量のデータをスクレイピング"""
    
    # Excelから科目番号を読み込み
    excel_path = Path(__file__).parent.parent / "courses.xlsx"
    
    if not excel_path.exists():
        print(f"Error: {excel_path} not found")
        return
    
    course_numbers = load_course_numbers_from_excel(str(excel_path))
    print(f"Found {len(course_numbers)} unique course numbers")
    
    # テスト用に50件だけ取得
    # いくつかのカテゴリからバランスよく選択
    test_courses = []
    categories_seen = set()
    
    for cn in course_numbers:
        prefix = cn[0] if cn else ""
        if prefix not in categories_seen or len([c for c in test_courses if c[0] == prefix]) < 5:
            test_courses.append(cn)
            categories_seen.add(prefix)
        if len(test_courses) >= 50:
            break
    
    print(f"Testing with {len(test_courses)} courses")
    print(f"Sample: {test_courses[:10]}")
    
    # スクレイピング実行
    print("\nStarting scrape...")
    syllabi = await scrape_syllabi(test_courses, max_concurrent=5, delay=0.3)
    
    # 結果を保存
    output_path = Path(__file__).parent / "data" / "syllabi.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(syllabi, f, ensure_ascii=False, indent=2)
    
    print(f"\nSaved {len(syllabi)} syllabi to {output_path}")
    
    # 統計表示
    if syllabi:
        print("\n--- Sample syllabus ---")
        sample = syllabi[0]
        for key, value in sample.items():
            if value:
                print(f"{key}: {str(value)[:100]}...")


if __name__ == "__main__":
    asyncio.run(test_scrape())
