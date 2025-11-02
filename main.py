import os
from flask import Flask, request, abort
from dotenv import load_dotenv

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent

# Google Drive imports - ใช้ OAuth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# โหลด environment variables
load_dotenv()

app = Flask(__name__)

# ตั้งค่า LINE Bot
configuration = Configuration(access_token=os.getenv("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("CHANNEL_SECRET"))

# Google Drive Scopes
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_google_drive_service():
    """สร้าง Google Drive service ด้วย OAuth"""
    creds = None

    # โหลด token ถ้ามี
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # ถ้าไม่มี credentials หรือหมดอายุ
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"⚠️ ไม่สามารถ refresh token: {e}")
                print("กรุณารัน: python auth_google_drive.py อีกครั้ง")
                raise
        else:
            print("⚠️ ไม่พบ token.json หรือ token ไม่ถูกต้อง")
            print("กรุณารัน: python auth_google_drive.py ก่อน")
            raise ValueError("Missing or invalid token.json")

        # บันทึก credentials
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    service = build("drive", "v3", credentials=creds)
    return service


def upload_to_google_drive(file_path, file_name, folder_id=None):
    """
    อัปโหลดไฟล์ไปยัง Google Drive

    Args:
        file_path: path ของไฟล์ที่จะอัปโหลด
        file_name: ชื่อไฟล์ที่ต้องการบน Google Drive
        folder_id: ID ของโฟลเดอร์ (ถ้าไม่ระบุจะอัปโหลดที่ My Drive)

    Returns:
        dict: ข้อมูลไฟล์ที่อัปโหลด (id, name, webViewLink)
    """
    try:
        service = get_google_drive_service()

        file_metadata = {"name": file_name}

        # ถ้าระบุ folder_id ให้อัปโหลดเข้าโฟลเดอร์นั้น
        if folder_id:
            file_metadata["parents"] = [folder_id]

        media = MediaFileUpload(file_path, mimetype="image/jpeg", resumable=True)

        file = (
            service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink, webContentLink",
            )
            .execute()
        )

        # ตั้งค่าให้ทุกคนดูไฟล์ได้ (ถ้าต้องการ)
        try:
            permission = {"type": "anyone", "role": "reader"}
            service.permissions().create(
                fileId=file.get("id"), body=permission
            ).execute()
            print("✅ ตั้งค่าให้ทุกคนดูไฟล์ได้")
        except Exception as e:
            print(f"⚠️ ไม่สามารถตั้งค่า permission: {e}")

        print(f"✅ อัปโหลดไฟล์สำเร็จ: {file.get('name')}")
        print(f"🔗 Link: {file.get('webViewLink')}")

        return file

    except HttpError as error:
        print(f"❌ เกิดข้อผิดพลาดจาก Google Drive API: {error}")
        raise
    except Exception as error:
        print(f"❌ เกิดข้อผิดพลาด: {error}")
        raise


@app.route("/callback", methods=["POST"])
def callback():
    # รับ signature จาก header
    signature = request.headers.get("X-Line-Signature")
    if not signature:
        app.logger.error("Missing X-Line-Signature header")
        abort(400)

    # รับ request body เป็น text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # จัดการ webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError as e:
        app.logger.error(f"Invalid signature: {e}")
        abort(400)
    except Exception as e:
        app.logger.error(f"Error handling webhook: {e}")
        abort(500)

    return "OK", 200


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    # อ่านข้อความที่ส่งมา
    received_text = event.message.text
    print(f"📩 ได้รับข้อความ: {received_text}")
    print(f"👤 จาก User ID: {event.source.user_id}")

    # สร้างข้อความตอบกลับ
    reply_text = f"คุณส่งมาว่า: {received_text}"

    # ส่งข้อความตอบกลับ
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token, messages=[TextMessage(text=reply_text)]
            )
        )


@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event):
    # อ่านข้อมูลรูปภาพ
    message_id = event.message.id
    print("🖼️ ได้รับรูปภาพ")
    print(f"📝 Message ID: {message_id}")
    print(f"👤 จาก User ID: {event.source.user_id}")

    # ดาวน์โหลดรูปภาพและอัปโหลดไปยัง Google Drive
    try:
        with ApiClient(configuration) as api_client:
            # ใช้ MessagingApiBlob สำหรับดาวน์โหลดไฟล์
            line_bot_blob_api = MessagingApiBlob(api_client)

            # ดาวน์โหลดรูปภาพ
            image_content = line_bot_blob_api.get_message_content(message_id)

            # บันทึกรูปภาพชั่วคราว
            image_path = f"images/{message_id}.jpg"
            os.makedirs("images", exist_ok=True)

            with open(image_path, "wb") as f:
                f.write(image_content)

            print(f"💾 บันทึกรูปภาพที่: {image_path}")

            # อัปโหลดไปยัง Google Drive
            folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")  # ถ้าไม่ระบุจะอัปโหลดที่ My Drive

            file_name = f"LINE_Image_{message_id}.jpg"
            drive_file = upload_to_google_drive(image_path, file_name, folder_id)

            # ลบไฟล์ชั่วคราว (ถ้าต้องการ)
            try:
                os.remove(image_path)
                print(f"🗑️ ลบไฟล์ชั่วคราวแล้ว: {image_path}")
            except Exception as e:
                print(f"⚠️ ไม่สามารถลบไฟล์ชั่วคราว: {e}")

            # ตอบกลับพร้อม link
            line_bot_api = MessagingApi(api_client)
            reply_text = f"✅ อัปโหลดรูปภาพไปยัง Google Drive แล้ว!\n\n📁 ชื่อไฟล์: {drive_file.get('name')}\n🔗 ดูไฟล์: {drive_file.get('webViewLink')}"

            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)],
                )
            )
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()

        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=f"เกิดข้อผิดพลาด: {str(e)}")],
                )
            )


@app.route("/", methods=["GET"])
def home():
    return "LINE Bot is running! 🤖", 200


@app.route("/callback", methods=["GET"])
def callback_get():
    return "This endpoint only accepts POST requests", 405


@app.route("/test-drive", methods=["GET"])
def test_drive():
    """ทดสอบการเชื่อมต่อ Google Drive"""
    try:
        service = get_google_drive_service()
        results = service.files().list(pageSize=5, fields="files(id, name)").execute()
        items = results.get("files", [])
        return {
            "status": "success",
            "message": "เชื่อมต่อ Google Drive สำเร็จ",
            "files": items,
        }, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


if __name__ == "__main__":
    # ตรวจสอบว่ามี environment variables หรือไม่
    if not os.getenv("CHANNEL_ACCESS_TOKEN") or not os.getenv("CHANNEL_SECRET"):
        print("⚠️ กรุณาตั้งค่า CHANNEL_ACCESS_TOKEN และ CHANNEL_SECRET ใน .env file")
        exit(1)

    # ตรวจสอบ credentials.json
    if not os.path.exists("credentials.json"):
        print("⚠️ ไม่พบไฟล์ credentials.json")
        print("กรุณาดาวน์โหลด OAuth credentials จาก Google Cloud Console")
        exit(1)

    # ตรวจสอบ token.json
    if not os.path.exists("token.json"):
        print("⚠️ ไม่พบไฟล์ token.json")
        print("🔧 กรุณารันคำสั่งนี้ก่อน:")
        print("   python auth_google_drive.py")
        exit(1)
    else:
        print("✅ พบไฟล์ token.json")

    # แสดง Folder ID (ถ้ามี)
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    if folder_id:
        print(f"✅ GOOGLE_DRIVE_FOLDER_ID: {folder_id}")
    else:
        print("💡 ไม่พบ GOOGLE_DRIVE_FOLDER_ID - จะอัปโหลดไปที่ My Drive")

    print("✅ LINE Bot เริ่มทำงานแล้ว")
    print("💡 ทดสอบ Google Drive ได้ที่: http://localhost:5000/test-drive")
    app.run(port=5000, debug=True)
