"""
RAG Pipeline
検索結果をコンテキストとしてLLMで回答生成
"""

import json
from pathlib import Path
from typing import Optional, AsyncGenerator
import google.generativeai as genai
from dotenv import load_dotenv
import os

from embedder import search_syllabi, get_query_embedding

load_dotenv()

# Gemini API設定
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# システムプロンプト
SYSTEM_PROMPT = """あなたは筑波大学の履修相談AIアシスタント「KdBアシスタント」です。
学生からの質問に対して、提供されたシラバス情報を基に、親切で分かりやすく回答してください。

## 回答のガイドライン
1. 具体的な科目名と科目番号を必ず記載してください
2. 単位数、開講時期、対象年次も含めてください
3. なぜその科目がおすすめなのか、授業概要を基に説明してください
4. 複数の選択肢がある場合は、それぞれの特徴を比較してください
5. 履修条件や前提知識がある場合は必ず言及してください

## 注意事項
- 提供された情報にない科目について憶測で回答しないでください
- 時間割の詳細や最新の変更については、必ずKdBで確認するよう促してください
- 必修/選択の判断は学群・学類によって異なるため、履修要覧の確認を勧めてください

学生の立場に立って、履修計画を立てる手助けをしてください。"""


def format_context(search_results: list[dict]) -> str:
    """検索結果をコンテキスト文字列に整形"""
    context_parts = []
    
    for i, result in enumerate(search_results, 1):
        context_parts.append(f"【科目{i}】\n{result['document']}")
    
    return "\n\n---\n\n".join(context_parts)


def generate_response_stream(
    query: str,
    db_path: str,
    category_filter: Optional[str] = None,
    year_filter: Optional[str] = None,
    n_results: int = 5,
):
    """ストリーミングで回答を生成（同期ジェネレータ）"""
    
    # 関連シラバスを検索
    search_results = search_syllabi(
        query=query,
        db_path=db_path,
        n_results=n_results,
        category_filter=category_filter,
        year_filter=year_filter,
    )
    
    if not search_results:
        yield "申し訳ありませんが、該当する科目が見つかりませんでした。検索条件を変えてお試しください。"
        return
    
    # デバッグログ
    print(f"[DEBUG] Search results for '{query}':")
    for r in search_results:
        print(f"  - {r['metadata'].get('course_name', 'unknown')}")
    
    # コンテキストを整形
    context = format_context(search_results)
    
    # プロンプトを構築
    user_prompt = f"""## 参考シラバス情報
{context}

## 学生からの質問
{query}

上記のシラバス情報を参考に、質問に回答してください。"""
    
    # Gemini APIでストリーミング生成
    try:
        model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
            system_instruction=SYSTEM_PROMPT,
        )
        
        response = model.generate_content(
            user_prompt,
            stream=True,
            generation_config=genai.GenerationConfig(
                temperature=0.7,
                max_output_tokens=2048,
            )
        )
        
        for chunk in response:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        yield f"エラーが発生しました: {str(e)}"


def generate_response(
    query: str,
    db_path: str,
    category_filter: Optional[str] = None,
    year_filter: Optional[str] = None,
    n_results: int = 5,
) -> str:
    """同期版の回答生成"""
    
    # 関連シラバスを検索
    search_results = search_syllabi(
        query=query,
        db_path=db_path,
        n_results=n_results,
        category_filter=category_filter,
        year_filter=year_filter,
    )
    
    if not search_results:
        return "申し訳ありませんが、該当する科目が見つかりませんでした。検索条件を変えてお試しください。"
    
    # コンテキストを整形
    context = format_context(search_results)
    
    # プロンプトを構築
    user_prompt = f"""## 参考シラバス情報
{context}

## 学生からの質問
{query}

上記のシラバス情報を参考に、質問に回答してください。"""
    
    # Gemini APIで生成
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=SYSTEM_PROMPT,
    )
    
    response = model.generate_content(
        user_prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.7,
            max_output_tokens=2048,
        )
    )
    
    return response.text


if __name__ == "__main__":
    # テスト実行
    db_path = str(Path(__file__).parent / "data" / "chromadb")
    
    test_queries = [
        "プログラミング初心者向けの授業を教えてください",
        "情報学群の1年生におすすめの科目は？",
        "AIや機械学習を学べる授業はありますか？",
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"質問: {query}")
        print(f"{'='*60}")
        response = generate_response(query, db_path)
        print(response)
