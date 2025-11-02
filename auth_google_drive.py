from google_auth_oauthlib.flow import InstalledAppFlow
import os

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def main():
    if not os.path.exists("credentials.json"):
        print("❌ ไม่พบไฟล์ credentials.json")
        return

    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)
    with open("token.json", "w") as token:
        token.write(creds.to_json())

    print("✅ สร้าง token.json สำเร็จแล้ว!")

if __name__ == "__main__":
    main()
