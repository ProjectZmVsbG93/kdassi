"""
KdB Assistant API Server
XLSXアップロード対応版
"""

import json
import uuid
import asyncio
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

# 必要なモジュールをインポート
from rag import generate_response_stream, generate_response
from embedder import search_syllabi, build_vector_db_from_xlsx, search_collection, suggest_courses_by_ai
from xlsx_parser import parse_xlsx, create_document_text
from scraper import fetch_details_for_courses

# データベースパス（レガシー用）
DB_PATH = str(Path(__file__).parent / "data" / "chromadb")
SYLLABI_PATH = Path(__file__).parent / "data" / "syllabi.json"

# セッションストレージ（本番ではRedis等を使用）
sessions = {}

# カテゴリ一覧
CATEGORIES = [
    {"id": "all", "name": "すべて", "type": "all"},
    {"id": "1", "name": "総合科目・学士基盤科目", "type": "共通科目"},
    {"id": "2", "name": "体育", "type": "共通科目"},
    {"id": "3", "name": "英語", "type": "共通科目"},
    {"id": "4", "name": "初修外国語（独・中）", "type": "共通科目"},
    {"id": "5", "name": "初修外国語（仏・露・西）", "type": "共通科目"},
    {"id": "6", "name": "情報", "type": "共通科目"},
    {"id": "7", "name": "芸術", "type": "共通科目"},
    {"id": "8", "name": "自由科目", "type": "共通科目"},
    {"id": "9", "name": "教職・博物館", "type": "共通科目"},
    {"id": "A", "name": "人文・文化学群", "type": "専門科目"},
    {"id": "B", "name": "社会・国際学群", "type": "専門科目"},
    {"id": "C", "name": "人間学群", "type": "専門科目"},
    {"id": "E", "name": "生命環境学群", "type": "専門科目"},
    {"id": "F", "name": "理工学群", "type": "専門科目"},
    {"id": "G", "name": "情報学群", "type": "専門科目"},
    {"id": "H", "name": "医学群", "type": "専門科目"},
    {"id": "WT", "name": "体育専門学群", "type": "専門科目"},
    {"id": "Y", "name": "芸術専門学群", "type": "専門科目"},
    {"id": "V", "name": "グローバル教育院", "type": "専門科目"},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """起動時の初期化処理"""
    print("KdB Assistant API starting...")
    yield
    # セッションのクリーンアップ
    sessions.clear()


app = FastAPI(
    title="KdB Assistant API",
    description="筑波大学履修相談AIチャットボットAPI（XLSXアップロード対応）",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    """チャットリクエスト"""
    message: str
    session_id: str  # セッションID必須
    category: Optional[str] = None
    year_level: Optional[str] = None
    course_type: Optional[str] = None  # "specialized" or "common"
    api_key: Optional[str] = None  # フロントエンドからのAPIキー
    stream: bool = True


class ChatResponse(BaseModel):
    """チャットレスポンス"""
    response: str
    sources: list[dict] = []


class UploadResponse(BaseModel):
    """アップロードレスポンス"""
    session_id: str
    course_count: int
    message: str


@app.get("/")
async def root():
    """フロントエンドのindex.htmlを返す"""
    index_path = Path(__file__).parent.parent / "frontend" / "index.html"
    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")
    return {"status": "ok", "message": "KdB Assistant API v2.0 is running"}


@app.get("/style.css")
async def serve_css():
    """CSSファイルを返す"""
    css_path = Path(__file__).parent.parent / "frontend" / "style.css"
    if css_path.exists():
        return FileResponse(css_path, media_type="text/css")
    raise HTTPException(status_code=404, detail="CSS not found")


@app.get("/app.js")
async def serve_js():
    """JSファイルを返す"""
    js_path = Path(__file__).parent.parent / "frontend" / "app.js"
    if js_path.exists():
        return FileResponse(js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="JS not found")


@app.get("/categories")
async def get_categories():
    """カテゴリ一覧を取得"""
    return {"categories": CATEGORIES}


@app.post("/upload", response_model=UploadResponse)
async def upload_xlsx(file: UploadFile = File(...)):
    """
    XLSXファイルをアップロードしてセッションを作成
    """
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="XLSXファイルをアップロードしてください")
    
    # ファイルを読み込み
    contents = await file.read()
    
    try:
        # XLSXを解析
        syllabi = parse_xlsx(contents, skip_header=True)
        
        if not syllabi:
            raise HTTPException(status_code=400, detail="有効な科目データが見つかりませんでした")
        
        # セッションID生成
        session_id = str(uuid.uuid4())[:8]
        
        # ベクトルDB構築（インメモリ）
        client, collection, syllabi_dict = build_vector_db_from_xlsx(syllabi, session_id)
        
        # セッションに保存
        sessions[session_id] = {
            "client": client,
            "collection": collection,
            "syllabi_dict": syllabi_dict,
            "course_count": len(syllabi),
        }
        
        print(f"Session {session_id} created with {len(syllabi)} courses")
        
        return UploadResponse(
            session_id=session_id,
            course_count=len(syllabi),
            message=f"{len(syllabi)}件の科目を読み込みました"
        )
        
    except Exception as e:
        print(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=f"ファイル処理エラー: {str(e)}")


@app.get("/session/{session_id}")
async def get_session_info(session_id: str):
    """セッション情報を取得"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    
    session = sessions[session_id]
    return {
        "session_id": session_id,
        "course_count": session["course_count"],
        "status": "active"
    }


@app.post("/chat")
async def chat(request: ChatRequest):
    """
    チャットエンドポイント（セッションベース）
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message is required")
    
    if not request.session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。XLSXを再アップロードしてください。")
    
    session = sessions[request.session_id]
    collection = session["collection"]
    syllabi_dict = session["syllabi_dict"]
    
    # ========== 検索処理 ==========
    
    # APIキーの有無でモードを分岐（フロントエンドから提供されたキーのみ考慮）
    has_api_key = bool(request.api_key)
    
    # パス1: 従来のDBキーワード検索
    # APIキーがない場合はセマンティック検索（expand_query）をスキップ
    traditional_results = search_collection(
        query=request.message,
        collection=collection,
        n_results=15 if has_api_key else 20,  # APIキーなしの場合は多めに取得
        use_semantic=has_api_key,  # APIキーなしの場合はセマンティック検索を無効化
        category_filter=request.category,
        year_filter=request.year_level,
        course_type_filter=request.course_type,
    )
    print(f"[PATH 1] Traditional search: {len(traditional_results)} results")
    
    # パス2: AI提案 → DB検索（APIキーがある場合のみ）
    ai_results = []
    if has_api_key:
        try:
            # 利用可能な科目名リストを取得
            all_course_names = [s.get("course_name", "") for s in syllabi_dict.values() if s.get("course_name")]
            
            # AIに科目名を提案してもらう
            suggested_names = suggest_courses_by_ai(request.message, all_course_names)
            
            if suggested_names:
                # 提案された科目名でDB検索（expand_queryをスキップしてAPI節約）
                for name in suggested_names:
                    name_results = search_collection(
                        query=name,
                        collection=collection,
                        n_results=2,  # 各提案から2件ずつ
                        use_semantic=False,  # expand_queryをスキップ
                        category_filter=request.category,
                        year_filter=request.year_level,
                        course_type_filter=request.course_type,
                    )
                    ai_results.extend(name_results)
            
            print(f"[PATH 2] AI suggestion search: {len(ai_results)} results")
        except Exception as e:
            print(f"AI path error: {e}")
    
    # 結果をマージ（重複排除）
    seen_courses = set()
    merged_results = []
    
    # 従来の検索結果を優先（15件）
    for r in traditional_results:
        course_num = r["course_number"]
        if course_num not in seen_courses:
            seen_courses.add(course_num)
            merged_results.append(r)
            if len(merged_results) >= 15:
                break
    
    # AI提案結果を追加（10件まで）
    ai_added = 0
    for r in ai_results:
        course_num = r["course_number"]
        if course_num not in seen_courses:
            seen_courses.add(course_num)
            merged_results.append(r)
            ai_added += 1
            if ai_added >= 10:
                break
    
    search_results = merged_results
    print(f"[MERGED] Total unique results: {len(search_results)}")
    
    if not search_results:
        if request.stream:
            def generate():
                yield f"data: {json.dumps({'text': '該当する科目が見つかりませんでした。'}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(generate(), media_type="text/event-stream")
        else:
            return ChatResponse(response="該当する科目が見つかりませんでした。")
    
    # Step 2: 上位科目の詳細をオンデマンドでスクレイピング
    course_numbers = [r["course_number"] for r in search_results]
    print(f"[DEBUG] Fetching details for: {course_numbers}")
    
    try:
        detailed_syllabi = await fetch_details_for_courses(
            course_numbers=course_numbers,
            base_syllabi=syllabi_dict,
        )
    except Exception as e:
        print(f"Scraping error: {e}")
        # スクレイピング失敗時はXLSXの基本情報のみ使用
        detailed_syllabi = [syllabi_dict.get(cn, {}) for cn in course_numbers if cn in syllabi_dict]
    
    # Step 3: コンテキストを整形してLLMへ
    context_parts = []
    for i, syllabus in enumerate(detailed_syllabi, 1):
        parts = [
            f"科目名: {syllabus.get('course_name', '')}",
            f"科目番号: {syllabus.get('course_number', '')}",
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
        if syllabus.get("grading"):
            parts.append(f"成績評価: {syllabus['grading']}")
        if syllabus.get("keywords"):
            parts.append(f"キーワード: {syllabus['keywords']}")
        if syllabus.get("prerequisites"):
            parts.append(f"履修条件: {syllabus['prerequisites']}")
        
        context_parts.append(f"【科目{i}】\n" + "\n".join(parts))
    
    context = "\n\n---\n\n".join(context_parts)
    
    # ========== APIキーがない場合: 検索結果を整形して返す ==========
    if not has_api_key:
        def generate_simple():
            # ヘッダー
            header = f"🔍 「{request.message}」の検索結果（{len(detailed_syllabi)}件）\n\n"
            yield f"data: {json.dumps({'text': header}, ensure_ascii=False)}\n\n"
            
            # 各科目を整形して出力
            for i, syllabus in enumerate(detailed_syllabi, 1):
                course_num = syllabus.get('course_number', '')
                course_name = syllabus.get('course_name', '')
                credits = syllabus.get('credits', '')
                year_level = syllabus.get('year_level', '')
                term = syllabus.get('term', '')
                day_period = syllabus.get('day_period', '')
                instructor = syllabus.get('instructor', '')
                
                # リンク付きの科目情報
                course_text = f"**{i}. [{course_name}](https://kdb.tsukuba.ac.jp/syllabi/2025/{course_num}/jpn)**（{course_num}）\n"
                course_text += f"<details>\n<summary>📖 詳細を見る</summary>\n\n"
                course_text += f"- 📊 単位: {credits}\n"
                course_text += f"- 📚 対象年次: {year_level}\n"
                course_text += f"- 📅 開講: {term} {day_period}\n"
                course_text += f"- 👤 教員: {instructor}\n"
                
                if syllabus.get('classroom'):
                    course_text += f"- 🏫 教室: {syllabus['classroom']}\n"
                if syllabus.get('overview'):
                    overview = syllabus['overview'][:150] + "..." if len(syllabus.get('overview', '')) > 150 else syllabus.get('overview', '')
                    course_text += f"- 📝 概要: {overview}\n"
                
                course_text += "</details>\n\n"
                
                yield f"data: {json.dumps({'text': course_text}, ensure_ascii=False)}\n\n"
            
            # フッター
            footer = "\n---\n💡 **ヒント**: サイドバーの設定からGemini APIキーを入力すると、AIがあなたの質問に合った科目を選んで詳しく説明してくれます。"
            yield f"data: {json.dumps({'text': footer}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            generate_simple(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    
    # ========== APIキーがある場合: LLMで応答を生成 ==========
    if request.stream:
        def generate():
            import google.generativeai as genai
            
            # ユーザープロフィール情報
            user_profile = []
            if request.category:
                user_profile.append(f"所属: {request.category}")
            if request.year_level:
                user_profile.append(f"年次: {request.year_level}年次")
            profile_str = "、".join(user_profile) if user_profile else "指定なし"
            
            system_prompt = f"""あなたは筑波大学の履修相談AIアシスタント「KdBアシスタント」です。
提供されたシラバス情報から質問に最適な科目を選んで回答してください。

## 学生のプロフィール
{profile_str}

## 回答フォーマット（必須）
質問に最も関連する3〜5科目を以下の形式で紹介:

おすすめ科目

**1. [科目名](https://kdb.tsukuba.ac.jp/syllabi/2025/科目番号/jpn)**（科目番号）- 一言説明
<details>
<summary>📖 詳細を見る</summary>

- 📅 開講: 春AB 月1,2
- 🏫 教室: ○○棟
- 👤 教員: ○○先生
- 📊 単位: 2.0
- 📚 対象年次: 1・2年次
- 📝 概要: （2-3文で説明）
- ⚠️ 備考: （履修条件があれば）
</details>

💡 まとめ
簡潔な総括（1-2文）

## 重要な注意事項
1. **年次に適した科目を選ぶ**: 学生が1年次なら、前提科目（「〇〇履修済」）が必要な科目は避け、入門・基礎レベルの科目を優先
2. **重複を避ける**: 同じ科目名で対象クラスが違うだけの科目は1つだけ紹介（代表的なものを選ぶ）
3. 必ず<details>タグを使用すること
4. 提供情報にない科目は言及しない
5. 見出しに#記号を使わない（「おすすめ科目」「まとめ」のみ）"""

            user_prompt = f"""## 候補科目（最大25件：従来検索15件+AI提案10件）
{context}

## 質問
{request.message}

上記の候補から質問に最も適した科目を10〜15個選んで紹介してください。
- 学生は{profile_str}です
- 同じ科目名の重複は省いてください
- 必ず<details>タグを使った折りたたみ形式で出力してください"""

            try:
                # フロントエンドからのAPIキーがあればそれを使用、なければ環境変数を使用
                if request.api_key:
                    genai.configure(api_key=request.api_key)
                else:
                    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
                
                model = genai.GenerativeModel(
                    model_name="gemini-2.5-flash",
                    system_instruction=system_prompt,
                )
                
                response = model.generate_content(
                    user_prompt,
                    stream=True,
                    generation_config=genai.GenerationConfig(
                        temperature=0.7,
                        max_output_tokens=65536,  # gemini-2.5-flashの最大値
                    )
                )
                
                for chunk in response:
                    if chunk.text:
                        yield f"data: {json.dumps({'text': chunk.text}, ensure_ascii=False)}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'text': f'エラーが発生しました: {str(e)}'}, ensure_ascii=False)}\n\n"
            
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    else:
        # 非ストリーミング（簡易実装）
        return ChatResponse(response="ストリーミングモードを使用してください")


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """セッションを削除"""
    if session_id in sessions:
        del sessions[session_id]
        return {"message": "セッションを削除しました"}
    raise HTTPException(status_code=404, detail="セッションが見つかりません")


# レガシーエンドポイント（既存のsyllabi.json用）
@app.get("/stats")
async def get_stats():
    """統計情報を取得（レガシー）"""
    if not SYLLABI_PATH.exists():
        return {"total_courses": 0, "categories": {}, "message": "レガシーデータなし"}
    
    with open(SYLLABI_PATH, "r", encoding="utf-8") as f:
        syllabi = json.load(f)
    
    categories = {}
    for s in syllabi:
        cat = s.get("category", "その他")
        categories[cat] = categories.get(cat, 0) + 1
    
    return {
        "total_courses": len(syllabi),
        "categories": categories
    }


# ========== 静的ファイル配信（本番用） ==========
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
