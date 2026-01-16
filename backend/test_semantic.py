"""セマンティック検索テスト"""
from embedder import search_syllabi

test_queries = [
    "レポート比率高い秋の授業",
    "文法が楽な第二外国語",
    "初心者向けのプログラミング",
    "弓道を学びたい",
]

for query in test_queries:
    print(f"\n{'='*60}")
    print(f"クエリ: {query}")
    print(f"{'='*60}")
    
    results = search_syllabi(query, "data/chromadb", n_results=3)
    
    for i, r in enumerate(results, 1):
        print(f"\n{i}. {r['metadata']['course_name']}")
        print(f"   スコア: {r.get('match_score', 0):.2f}")
        print(f"   理由: {r.get('match_reasons', [])}")
