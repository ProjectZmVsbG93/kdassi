"""検索テスト"""
from embedder import search_syllabi

print("=== 弓道 検索テスト ===")
results = search_syllabi("弓道", "data/chromadb", n_results=10)
print(f"検索結果: {len(results)}件\n")

for i, r in enumerate(results, 1):
    meta = r["metadata"]
    print(f"{i}. {meta['course_number']} - {meta['course_name']}")
    print(f"   カテゴリ: {meta['category']}")
    print(f"   類似度スコア: {1 - r['distance']:.3f}")
    print()
