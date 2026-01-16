"""
Embedding & Vector Database Setup
シラバスデータをベクトル化してChromaDBに格納
"""

import json
from pathlib import Path
from typing import Optional
import chromadb
from chromadb.config import Settings
import google.generativeai as genai
from dotenv import load_dotenv
import os

load_dotenv()

# Gemini API設定
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def create_document_text(syllabus: dict) -> str:
    """シラバスから検索用ドキュメントテキストを生成"""
    parts = [
        f"科目名: {syllabus.get('course_name', '')}",
        f"科目番号: {syllabus.get('course_number', '')}",
        f"分類: {syllabus.get('category', '')} ({syllabus.get('category_type', '')})",
        f"単位: {syllabus.get('credits', '')}単位",
        f"対象年次: {syllabus.get('year_level', '')}年次",
        f"開講時期: {syllabus.get('term', '')}",
        f"授業方法: {syllabus.get('method', '')}",
    ]
    
    if syllabus.get("overview"):
        parts.append(f"授業概要: {syllabus['overview']}")
    
    if syllabus.get("objectives"):
        parts.append(f"到達目標: {syllabus['objectives']}")
    
    if syllabus.get("keywords"):
        parts.append(f"キーワード: {syllabus['keywords']}")
    
    if syllabus.get("grading"):
        parts.append(f"成績評価: {syllabus['grading']}")
    
    if syllabus.get("prerequisites"):
        parts.append(f"履修条件: {syllabus['prerequisites']}")
    
    if syllabus.get("competence"):
        parts.append(f"コンピテンス: {syllabus['competence']}")
    
    return "\n".join(parts)


def get_embedding(text: str) -> list[float]:
    """Gemini APIでテキストをベクトル化"""
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        task_type="retrieval_document"
    )
    return result["embedding"]


def get_query_embedding(text: str) -> list[float]:
    """クエリ用のベクトル化"""
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        task_type="retrieval_query"
    )
    return result["embedding"]


def suggest_courses_by_ai(query: str, available_courses: list[str]) -> list[str]:
    """
    LLMに質問に合いそうな科目名を提案してもらう
    
    Args:
        query: ユーザーの質問
        available_courses: 利用可能な科目名リスト（サンプル）
        
    Returns:
        提案された科目名のリスト
    """
    import json
    import re
    
    model = genai.GenerativeModel(model_name="gemini-2.5-flash")
    
    # 科目リストのサンプルを作成（最初の200件程度）
    sample_courses = available_courses[:200] if len(available_courses) > 200 else available_courses
    courses_text = "\n".join(sample_courses)
    
    prompt = f"""以下の質問に合いそうな大学の授業科目名を10個提案してください。

## 質問
{query}

## 利用可能な科目の例
{courses_text}

上記の例にない科目も含めて、質問に合いそうな一般的な大学科目名を提案してください。
科目名のみを1行ずつ出力してください（番号や説明は不要）。
"""

    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.7,
                max_output_tokens=500,
            )
        )
        
        # 行ごとに分割して科目名リストを取得
        suggested = []
        for line in response.text.strip().split("\n"):
            line = line.strip()
            # 番号や記号を除去
            line = re.sub(r'^[\d\.\-\*]+\s*', '', line)
            if line and len(line) > 1:
                suggested.append(line)
        
        print(f"[AI SUGGEST] Query: '{query}' -> Suggested: {suggested[:10]}")
        return suggested[:10]
        
    except Exception as e:
        print(f"AI suggestion error: {e}")
        return []


def expand_query(query: str) -> dict:
    """
    クエリを拡張して検索に必要な情報を抽出
    あいまいな質問から具体的な検索条件とフィルターを生成
    """
    import json
    import re
    
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
    )
    
    # 高度なフィルター抽出プロンプト
    prompt = f"""授業検索クエリからキーワードとフィルター条件を抽出してください。

クエリ: {query}

JSON形式で出力:
{{
  "keywords": ["キーワード1", "キーワード2"],
  "category": "カテゴリ名",
  "filters": {{
    "delivery_method": null,
    "weekdays": [],
    "include_periods": [],
    "exclude_periods": [],
    "terms": [],
    "department": null,
    "year_includes": null
  }}
}}

## フィルターの説明
- delivery_method: "対面", "オンライン", またはnull（指定なし）
- weekdays: 曜日リスト ["月", "火", "水", "木", "金"]
- include_periods: 含める時限 ["1", "2", "3", "4", "5", "6"]
- exclude_periods: 除外する時限
- terms: 開講時期 ["春A", "春AB", "秋ABC"]など
- department: 開講学類名（"生物資源", "情報科学"など）
- year_includes: 指定年次を含む（"1", "2", "3", "4"）

## 例
- "オンラインでプログラミング" → {{"keywords": ["プログラミング"], "filters": {{"delivery_method": "オンライン"}}}}
- "1限以外の英語" → {{"keywords": ["英語"], "filters": {{"exclude_periods": ["1"]}}}}
- "金曜5限" → {{"keywords": [], "filters": {{"weekdays": ["金"], "include_periods": ["5"]}}}}
- "秋ABCの理系科目" → {{"keywords": ["数学", "統計", "情報"], "filters": {{"terms": ["秋ABC"]}}}}
- "生物資源学類開講" → {{"keywords": [], "filters": {{"department": "生物資源"}}}}
- "1年次対象" → {{"keywords": [], "filters": {{"year_includes": "1"}}}}
- "月水金の対面授業" → {{"keywords": [], "filters": {{"weekdays": ["月", "水", "金"], "delivery_method": "対面"}}}}

JSONのみ出力:"""

    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.0,
                max_output_tokens=500,
            )
        )
        
        # JSONをパース
        text = response.text.strip()
        # ```json ... ``` を除去
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        # コメントを除去
        text = re.sub(r'//.*$', '', text, flags=re.MULTILINE)
        
        result = json.loads(text)
        
        # フィルターを取得（存在しない場合は空のdict）
        filters = result.get("filters", {})
        
        # 正規化
        return {
            "keywords": result.get("keywords", []),
            "related_terms": result.get("related_terms", []),
            "category_hint": result.get("category", ""),
            "search_intent": query,
            # 高度なフィルター
            "filters": {
                "delivery_method": filters.get("delivery_method"),
                "weekdays": filters.get("weekdays", []),
                "include_periods": filters.get("include_periods", []),
                "exclude_periods": filters.get("exclude_periods", []),
                "terms": filters.get("terms", []),
                "department": filters.get("department"),
                "year_includes": filters.get("year_includes"),
            }
        }
    except Exception as e:
        print(f"Query expansion error: {e}")
        
        # フォールバック: 簡易的なキーワード抽出とフィルター検出
        fallback_keywords = []
        fallback_filters = {
            "delivery_method": None,
            "weekdays": [],
            "include_periods": [],
            "exclude_periods": [],
            "terms": [],
            "department": None,
            "year_includes": None,
        }
        
        # 簡易フィルター検出
        if "オンライン" in query:
            fallback_filters["delivery_method"] = "オンライン"
        elif "対面" in query:
            fallback_filters["delivery_method"] = "対面"
        
        # 曜日検出
        for day in ["月", "火", "水", "木", "金"]:
            if day in query:
                fallback_filters["weekdays"].append(day)
        
        # 時限検出
        for period in ["1", "2", "3", "4", "5", "6"]:
            if f"{period}限" in query:
                if "以外" in query:
                    fallback_filters["exclude_periods"].append(period)
                else:
                    fallback_filters["include_periods"].append(period)
        
        # キーワード
        if "外国語" in query and "英語以外" in query:
            fallback_keywords = ["ドイツ語", "フランス語", "中国語", "韓国語", "スペイン語"]
        elif "プログラミング" in query:
            fallback_keywords = ["プログラミング", "情報", "コンピュータ"]
        
        return {
            "keywords": fallback_keywords,
            "related_terms": [],
            "category_hint": "",
            "search_intent": query,
            "filters": fallback_filters,
        }


def build_vector_db(syllabi_path: str, db_path: str, batch_size: int = 100):
    """シラバスデータからChromaDBを構築"""
    
    # シラバスデータ読み込み
    with open(syllabi_path, "r", encoding="utf-8") as f:
        syllabi = json.load(f)
    
    print(f"Loaded {len(syllabi)} syllabi")
    
    # ChromaDB初期化
    client = chromadb.PersistentClient(path=db_path)
    
    # 既存のコレクションがあれば削除
    try:
        client.delete_collection("syllabi")
    except:
        pass
    
    collection = client.create_collection(
        name="syllabi",
        metadata={"hnsw:space": "cosine"}
    )
    
    # バッチ処理でエンベディング
    for i in range(0, len(syllabi), batch_size):
        batch = syllabi[i:i + batch_size]
        
        ids = []
        documents = []
        embeddings = []
        metadatas = []
        
        for syllabus in batch:
            course_number = syllabus.get("course_number", "")
            if not course_number:
                continue
            
            doc_text = create_document_text(syllabus)
            
            try:
                embedding = get_embedding(doc_text)
            except Exception as e:
                print(f"Error embedding {course_number}: {e}")
                continue
            
            ids.append(course_number)
            documents.append(doc_text)
            embeddings.append(embedding)
            metadatas.append({
                "course_number": course_number,
                "course_name": syllabus.get("course_name", ""),
                "category": syllabus.get("category", ""),
                "category_type": syllabus.get("category_type", ""),
                "credits": syllabus.get("credits", ""),
                "year_level": syllabus.get("year_level", ""),
                "term": syllabus.get("term", ""),
                "method": syllabus.get("method", ""),
            })
        
        if ids:
            collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas
            )
        
        print(f"Processed {min(i + batch_size, len(syllabi))}/{len(syllabi)}")
    
    print(f"Vector database built with {collection.count()} documents")
    return collection


def build_vector_db_from_xlsx(syllabi: list[dict], session_id: str = "default") -> tuple:
    """
    XLSXから読み込んだシラバスデータでインメモリChromaDBを構築
    
    高速化のため、最初はエンベディングなしでドキュメントのみ登録
    ベクトル検索が必要な場合は後から追加
    
    Args:
        syllabi: xlsx_parser.parse_xlsx()で取得したシラバスリスト
        session_id: セッションID（コレクション名に使用）
        
    Returns:
        (client, collection, syllabi_dict) のタプル
    """
    from xlsx_parser import create_document_text as xlsx_create_doc_text
    import time
    
    start_time = time.time()
    print(f"Building in-memory DB for session {session_id} with {len(syllabi)} courses")
    
    # インメモリChromaDB（デフォルトのエンベディング関数を無効化）
    client = chromadb.Client()
    
    # 既存のコレクションがあれば削除
    collection_name = f"syllabi_{session_id}"
    try:
        client.delete_collection(collection_name)
    except:
        pass
    
    # エンベディングなしでコレクション作成
    # ChromaDBのデフォルト動作を上書きするためにダミーの埋め込み関数を使用
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
    
    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )
    
    # シラバス辞書（科目番号→シラバス情報）
    syllabi_dict = {}
    
    # バッチ処理で登録（エンベディングなし、ドキュメントとメタデータのみ）
    batch_size = 500  # エンベディングがないので大きなバッチでOK
    
    for i in range(0, len(syllabi), batch_size):
        batch = syllabi[i:i + batch_size]
        
        ids = []
        documents = []
        metadatas = []
        # ダミーのエンベディング（768次元のゼロベクトル）
        embeddings = []
        
        for syllabus in batch:
            course_number = syllabus.get("course_number", "")
            if not course_number:
                continue
            
            # 重複チェック
            if course_number in syllabi_dict:
                continue
            
            # ドキュメントテキスト生成
            doc_text = xlsx_create_doc_text(syllabus)
            
            ids.append(course_number)
            documents.append(doc_text)
            # ダミーエンベディング（キーワード検索のみ使用するため）
            embeddings.append([0.0] * 768)
            metadatas.append({
                "course_number": course_number,
                "course_name": syllabus.get("course_name", ""),
                "category": syllabus.get("category", ""),
                "category_type": syllabus.get("category_type", ""),
                "credits": syllabus.get("credits", ""),
                "year_level": syllabus.get("year_level", ""),
                "term": syllabus.get("term", ""),
                "day_period": syllabus.get("day_period", ""),
                "instructor": syllabus.get("instructor", ""),
                "delivery_method": syllabus.get("delivery_method", ""),
            })
            
            # 辞書にも保存
            syllabi_dict[course_number] = syllabus
        
        if ids:
            collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas
            )
        
        if (i + batch_size) % 2000 == 0 or i + batch_size >= len(syllabi):
            elapsed = time.time() - start_time
            print(f"Registered {min(i + batch_size, len(syllabi))}/{len(syllabi)} courses ({elapsed:.1f}s)")
    
    elapsed = time.time() - start_time
    print(f"In-memory DB built with {collection.count()} documents in {elapsed:.1f}s")
    return client, collection, syllabi_dict


def search_syllabi(
    query: str,
    db_path: str,
    n_results: int = 5,
    category_filter: Optional[str] = None,
    year_filter: Optional[str] = None,
    use_semantic: bool = True,
) -> list[dict]:
    """
    シラバスを検索（セマンティック検索対応）
    
    あいまいなクエリ（例: 「レポート比率高い秋の授業」）も理解可能
    """
    import re
    
    client = chromadb.PersistentClient(path=db_path)
    collection = client.get_collection("syllabi")
    
    # Step 1: クエリを拡張（LLMで意図を理解）
    expanded = None
    if use_semantic:
        try:
            expanded = expand_query(query)
            print(f"Query expanded: {expanded}")
        except Exception as e:
            print(f"Query expansion failed: {e}")
            expanded = None
    
    # Step 2: 検索用キーワードを収集
    all_keywords = []
    
    # 基本のキーワード抽出（助詞で分割）
    split_query = re.split(r'[はがをにでとのもへやから]', query)
    for part in split_query:
        part = part.strip()
        if len(part) >= 2:
            all_keywords.append(part.lower())
    
    # LLM拡張からキーワード追加
    if expanded:
        all_keywords.extend([k.lower() for k in expanded.get("keywords", [])])
        all_keywords.extend([k.lower() for k in expanded.get("related_terms", [])])
    
    # 重複を除去
    all_keywords = list(set(all_keywords))
    
    # Step 3: 全ドキュメントを取得してスコアリング
    all_docs = collection.get(include=["documents", "metadatas"])
    scored_results = []
    
    for i, doc in enumerate(all_docs["documents"]):
        meta = all_docs["metadatas"][i]
        course_name = meta.get("course_name", "").lower()
        doc_lower = doc.lower()
        
        score = 0.0
        match_reasons = []
        
        # キーワードマッチング
        for keyword in all_keywords:
            if keyword in course_name:
                score += 3.0
                match_reasons.append(f"科目名に'{keyword}'")
            elif keyword in doc_lower:
                score += 1.0
                match_reasons.append(f"内容に'{keyword}'")
        
        # セマンティックマッチング（LLM拡張情報を使用）
        if expanded:
            # 評価方法の希望をチェック
            eval_pref = expanded.get("evaluation_preference", "").lower()
            if eval_pref:
                if "レポート" in eval_pref and "レポート" in doc_lower:
                    score += 2.0
                    match_reasons.append("レポート評価あり")
                if "試験なし" in eval_pref and "試験" not in doc_lower:
                    score += 1.5
                    match_reasons.append("試験なし")
                if "出席" in eval_pref and "出席" in doc_lower:
                    score += 1.5
                    match_reasons.append("出席評価あり")
            
            # 時間の希望をチェック
            time_pref = expanded.get("time_preference", "").lower()
            if time_pref:
                for time_word in ["春", "秋", "月曜", "火曜", "水曜", "木曜", "金曜"]:
                    if time_word in time_pref and time_word in doc_lower:
                        score += 2.0
                        match_reasons.append(f"{time_word}開講")
            
            # 難易度の希望をチェック
            diff_pref = expanded.get("difficulty_preference", "").lower()
            if diff_pref:
                if any(x in diff_pref for x in ["楽", "簡単", "初心者"]):
                    if any(x in doc_lower for x in ["入門", "基礎", "初級", "初歩"]):
                        score += 2.0
                        match_reasons.append("初心者向け")
            
            # カテゴリヒントをチェック
            cat_hint = expanded.get("category_hint", "").lower()
            if cat_hint:
                category = meta.get("category", "").lower()
                if cat_hint in category or cat_hint in doc_lower:
                    score += 1.5
                    match_reasons.append(f"カテゴリ:{cat_hint}")
        
        if score > 0:
            scored_results.append({
                "course_number": all_docs["ids"][i],
                "document": doc,
                "metadata": meta,
                "distance": 0.0,
                "match_score": score,
                "match_reasons": match_reasons,
            })
    
    # スコア順にソート
    scored_results.sort(key=lambda x: x["match_score"], reverse=True)
    
    # 十分な結果があればそれを返す
    if len(scored_results) >= n_results:
        return scored_results[:n_results]
    
    # Step 4: ベクトル検索で補完
    # 拡張されたクエリでエンベディング
    search_query = query
    if expanded and expanded.get("search_intent"):
        search_query = f"{query} {expanded.get('search_intent', '')} {' '.join(expanded.get('keywords', []))}"
    
    query_embedding = get_query_embedding(search_query)
    
    # フィルタ条件
    where_filter = None
    if category_filter or year_filter:
        conditions = []
        if category_filter:
            conditions.append({"category": category_filter})
        if year_filter:
            conditions.append({"year_level": year_filter})
        if len(conditions) == 1:
            where_filter = conditions[0]
        else:
            where_filter = {"$and": conditions}
    
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results * 2,
        where=where_filter,
        include=["documents", "metadatas", "distances"]
    )
    
    # ベクトル検索結果を追加
    scored_ids = {r["course_number"] for r in scored_results}
    
    for i in range(len(results["ids"][0])):
        course_id = results["ids"][0][i]
        if course_id not in scored_ids:
            scored_results.append({
                "course_number": course_id,
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
                "match_score": 1.0 - results["distances"][0][i],  # 類似度をスコアに変換
                "match_reasons": ["ベクトル類似度"],
            })
    
    # 再度スコア順にソート
    scored_results.sort(key=lambda x: x["match_score"], reverse=True)
    return scored_results[:n_results]


def search_collection(
    query: str,
    collection,
    n_results: int = 5,
    use_semantic: bool = True,
    category_filter: str = None,
    year_filter: str = None,
    course_type_filter: str = None,  # "specialized" or "common"
) -> list[dict]:
    """
    インメモリコレクションを検索（XLSXアップロード用）
    
    Args:
        query: 検索クエリ
        collection: ChromaDBコレクション
        n_results: 返す結果数
        use_semantic: クエリ拡張を使用するか
        category_filter: 学群フィルタ（例: "情報学群", "G"）
        year_filter: 年次フィルタ（例: "1", "2"）
        course_type_filter: "specialized"=専門科目のみ, "common"=共通科目のみ
        
    Returns:
        検索結果のリスト
    """
    import re
    
    # Step 1: クエリを拡張
    expanded = None
    if use_semantic:
        try:
            expanded = expand_query(query)
            print(f"Query expanded: {expanded}")
        except Exception as e:
            print(f"Query expansion failed: {e}")
    
    # Step 2: キーワード収集（拡張キーワードと元クエリを分離）
    original_keywords = []
    expanded_keywords = []
    
    # 元のクエリから抽出
    split_query = re.split(r'[はがをにでとのもへやから？]', query)
    for part in split_query:
        part = part.strip()
        if len(part) >= 2:
            original_keywords.append(part.lower())
    
    # 拡張キーワード（LLMが生成した具体的な科目名キーワード）
    if expanded:
        expanded_keywords = [k.lower() for k in expanded.get("keywords", [])]
        expanded_keywords.extend([k.lower() for k in expanded.get("related_terms", [])])
    
    print(f"[SEARCH] Original: {original_keywords}, Expanded: {expanded_keywords}")
    
    # Step 3: 全ドキュメントを取得
    all_docs = collection.get(include=["documents", "metadatas"])
    scored_results = []
    
    # 共通科目のカテゴリ（学群に関係なく検索対象に含める）
    common_categories = {
        "体育", "英語", "総合科目・学士基盤科目", "情報", "芸術", "自由科目", "教職・博物館",
        "初修外国語（独・中）", "初修外国語（仏・露・西）", "外国語"
    }
    
    # 高度なフィルターを取得
    adv_filters = expanded.get("filters", {}) if expanded else {}
    
    for i, doc in enumerate(all_docs["documents"]):
        meta = all_docs["metadatas"][i]
        
        # Step 3a: カテゴリ/年次フィルタリング
        course_category = meta.get("category", "")
        course_year = meta.get("year_level", "")
        course_term = meta.get("term", "")
        course_day_period = meta.get("day_period", "")
        course_delivery = meta.get("delivery_method", "")
        course_number = meta.get("course_number", "")
        
        # フィルタが指定されている場合、マッチしないものはスキップ
        # ただし共通科目は常に含める
        is_common = course_category in common_categories
        
        # 科目番号の先頭文字で共通科目かどうかを判定
        # 1,3,4,5,6,8,9で始まる = 共通科目・必修外国語・教職
        is_common_by_number = False
        is_graduate = False  # 大学院科目（0Aで始まる）
        if course_number:
            first_char = course_number[0]
            if first_char in "1345689":
                is_common_by_number = True
            # 0Aで始まる = 大学院科目
            if course_number.startswith("0A"):
                is_graduate = True
        
        # 大学院科目は、明示的に「0A」フィルタを選択しない限り除外
        if is_graduate and category_filter != "0A":
            continue
        
        # 科目種類フィルタ
        if course_type_filter == "specialized":
            # 専門科目のみ: 共通科目を除外
            if is_common or is_common_by_number:
                continue
        elif course_type_filter == "common":
            # 共通科目のみ: 専門科目を除外
            if not is_common and not is_common_by_number:
                continue
        
        if category_filter and not is_common and not is_common_by_number:
            # カテゴリフィルタ：学群名または先頭文字でマッチ
            if category_filter not in course_category:
                # 科目番号の先頭文字でもチェック
                if course_number and not course_number.upper().startswith(category_filter.upper()):
                    continue
        
        if year_filter and not is_common and not is_common_by_number:
            # 年次フィルタ：指定年次を含むかチェック
            if year_filter not in course_year:
                continue
        
        # Step 3a-2: 高度なフィルター適用
        skip_course = False
        
        # 授業形態フィルタ（オンライン/対面）
        if adv_filters.get("delivery_method"):
            filter_method = adv_filters["delivery_method"]
            if filter_method == "オンライン":
                if "オンライン" not in course_delivery:
                    skip_course = True
            elif filter_method == "対面":
                if "対面" not in course_delivery and "オンライン" in course_delivery:
                    skip_course = True
        
        # 曜日フィルタ
        if adv_filters.get("weekdays"):
            has_day = False
            for day in adv_filters["weekdays"]:
                if day in course_day_period:
                    has_day = True
                    break
            if not has_day:
                skip_course = True
        
        # 時限フィルタ（含める）
        if adv_filters.get("include_periods"):
            has_period = False
            for period in adv_filters["include_periods"]:
                if period in course_day_period:
                    has_period = True
                    break
            if not has_period:
                skip_course = True
        
        # 時限フィルタ（除外）
        if adv_filters.get("exclude_periods"):
            for period in adv_filters["exclude_periods"]:
                # 例: "1" が "月1,2" に含まれるかチェック
                if period in course_day_period:
                    skip_course = True
                    break
        
        # 開講時期フィルタ
        if adv_filters.get("terms"):
            has_term = False
            for term in adv_filters["terms"]:
                if term in course_term or course_term in term:
                    has_term = True
                    break
            if not has_term:
                skip_course = True
        
        # 開講学類フィルタ
        if adv_filters.get("department"):
            dept = adv_filters["department"]
            if dept not in doc and dept not in course_category:
                skip_course = True
        
        # 年次含むフィルタ
        if adv_filters.get("year_includes"):
            target_year = adv_filters["year_includes"]
            if target_year not in course_year:
                skip_course = True
        
        if skip_course:
            continue
        
        # Step 3b: キーワードスコアリング（拡張キーワードを優先）
        course_name = meta.get("course_name", "")
        doc_lower = doc.lower()
        
        # デバッグ: 最初の5件だけ科目名を出力
        if i < 5 and original_keywords:
            print(f"[DEBUG] Checking course: '{course_name}' for keywords: {original_keywords}")
        
        score = 0.0
        match_reasons = []
        
        # 拡張キーワード（高スコア）- 科目名マッチを重視
        for keyword in expanded_keywords:
            if keyword in course_name:
                score += 5.0  # 拡張キーワードが科目名にマッチ = 最高スコア
                match_reasons.append(f"科目名に'{keyword}'")
            elif keyword in doc_lower:
                score += 2.0  # 拡張キーワードが内容にマッチ
                match_reasons.append(f"内容に'{keyword}'")
        
        # 元のクエリのキーワード - 科目名マッチは高スコア
        for keyword in original_keywords:
            if keyword in course_name:
                score += 5.0  # 科目名マッチは高スコア（use_semantic=Falseでも動作）
                match_reasons.append(f"科目名に'{keyword}'")
            # 内容マッチは控えめに（「理系分野」など偶然マッチを防ぐ）
            elif keyword in doc_lower:
                score += 0.3  # 非常に低いスコア
        
        # フィルターマッチのボーナススコア
        if adv_filters:
            if adv_filters.get("delivery_method"):
                score += 1.0
                match_reasons.append(f"授業形態:{adv_filters['delivery_method']}")
            if adv_filters.get("weekdays"):
                score += 1.0
                match_reasons.append(f"曜日:{','.join(adv_filters['weekdays'])}")
            if adv_filters.get("include_periods"):
                score += 1.0
                match_reasons.append(f"時限:{','.join(adv_filters['include_periods'])}")
        
        if expanded:
            cat_hint = expanded.get("category_hint") or ""
            if cat_hint:
                cat_hint = cat_hint.lower()
                category = meta.get("category", "").lower()
                if cat_hint in category or cat_hint in doc_lower:
                    score += 1.5
                    match_reasons.append(f"カテゴリ:{cat_hint}")
        
        # フィルタのみ（キーワードなし）でもスコア付与
        if score == 0 and adv_filters and not expanded_keywords and not original_keywords:
            score = 1.0  # フィルタマッチ最低スコア
        
        if score > 0:
            scored_results.append({
                "course_number": all_docs["ids"][i],
                "document": doc,
                "metadata": meta,
                "distance": 0.0,
                "match_score": score,
                "match_reasons": match_reasons,
            })
    
    scored_results.sort(key=lambda x: x["match_score"], reverse=True)
    
    # フィルタ情報をログ
    filter_info = []
    if category_filter:
        filter_info.append(f"category={category_filter}")
    if year_filter:
        filter_info.append(f"year={year_filter}")
    
    print(f"[SEARCH] Query: '{query}' | Filters: {filter_info or 'none'} | Found: {len(scored_results)} matches")
    
    return scored_results[:n_results]


if __name__ == "__main__":
    # ベクトルDB構築
    syllabi_path = Path(__file__).parent / "data" / "syllabi.json"
    db_path = str(Path(__file__).parent / "data" / "chromadb")
    
    if syllabi_path.exists():
        build_vector_db(str(syllabi_path), db_path)
    else:
        print(f"Syllabi file not found: {syllabi_path}")
        print("Run scraper.py first to collect syllabi data.")
