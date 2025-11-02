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

# โหลด environment variables
load_dotenv()

app = Flask(__name__)

# ตั้งค่า LINE Bot
configuration = Configuration(access_token=os.getenv("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("CHANNEL_SECRET"))


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

    # ดาวน์โหลดรูปภาพ (ถ้าต้องการ)
    try:
        with ApiClient(configuration) as api_client:
            # ใช้ MessagingApiBlob สำหรับดาวน์โหลดไฟล์
            line_bot_blob_api = MessagingApiBlob(api_client)

            # ดาวน์โหลดรูปภาพ
            image_content = line_bot_blob_api.get_message_content(message_id)

            # บันทึกรูปภาพ
            image_path = f"images/{message_id}.jpg"
            os.makedirs("images", exist_ok=True)

            with open(image_path, "wb") as f:
                f.write(image_content)

            print(f"💾 บันทึกรูปภาพที่: {image_path}")

            # ตอบกลับ
            line_bot_api = MessagingApi(api_client)
            reply_text = "ได้รับรูปภาพแล้วค่ะ! 📸\nบันทึกไว้แล้ว"
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
                    messages=[
                        TextMessage(text=f"ได้รับรูปภาพแล้วค่ะ แต่เกิดข้อผิดพลาด: {str(e)}")
                    ],
                )
            )


@app.route("/", methods=["GET"])
def home():
    return "LINE Bot is running! 🤖", 200


@app.route("/callback", methods=["GET"])
def callback_get():
    return "This endpoint only accepts POST requests", 405


if __name__ == "__main__":
    # ตรวจสอบว่ามี environment variables หรือไม่
    if not os.getenv("CHANNEL_ACCESS_TOKEN") or not os.getenv("CHANNEL_SECRET"):
        print("⚠️ กรุณาตั้งค่า CHANNEL_ACCESS_TOKEN และ CHANNEL_SECRET ใน .env file")
    else:
        print("✅ LINE Bot เริ่มทำงานแล้ว")
        app.run(port=5000, debug=True)
