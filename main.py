from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient
from telethon.sessions import StringSession
import hashlib
import os
import shutil
import asyncio

app = FastAPI()

# 設定 CORS，讓你的 Nuxt 前端可以呼叫這個 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 實際上線建議改成你的 Vercel 網址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 從環境變數讀取機密資訊 (部署到 Render 時設定)
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
TARGET_GROUP_ID = int(os.environ.get("TARGET_GROUP_ID", 0))

# 初始化 Telegram Client
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

@app.on_event("startup")
async def startup_event():
    # 伺服器啟動時，自動連線到 Telegram
    await client.connect()

@app.post("/upload/")
async def upload_recording(
    file: UploadFile = File(...), 
    topic_id: int = Form(...) # 接收前端傳來的主題(月份) ID
):
    if not client.is_connected():
        await client.connect()

    # 1. 建立暫存檔路徑 (Render 允許寫入 /tmp 目錄)
    temp_file_path = f"/tmp/{file.filename}"
    
    try:
        # 2. 將大檔案分塊寫入暫存檔 (避免記憶體爆掉)
        sha256_hash = hashlib.sha256()
        with open(temp_file_path, "wb") as buffer:
            # 每次讀取 1MB
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)
                sha256_hash.update(chunk) # 同時計算法律防偽 Hash
        
        file_hash = sha256_hash.hexdigest()

        # 3. 透過 Telethon 上傳到指定的 Telegram Topic
        message = await client.send_file(
            TARGET_GROUP_ID,
            file=temp_file_path,
            reply_to=topic_id, # 放到指定的月份 Topic
            caption=f"📂 錄音檔：{file.filename}\n⚖️ SHA256 指紋：`{file_hash}`\n🕒 上傳時間：備份系統自動上傳",
            force_document=True # 強制以檔案傳送，保證音質不被壓縮
        )

        # 4. 回傳成功訊息與 Telegram 連結
        # 取得頻道連結格式 (去除 -100 前綴)
        chat_id_str = str(TARGET_GROUP_ID).replace("-100", "")
        tg_link = f"https://t.me/c/{chat_id_str}/{message.id}"

        return {
            "success": True,
            "filename": file.filename,
            "telegram_link": tg_link,
            "file_hash": file_hash
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        # 5. 無論成功或失敗，最後一定要刪除暫存檔，釋放 Render 空間
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

@app.get("/")
def read_root():
    return {"status": "Telegram Uploader API is running!"}