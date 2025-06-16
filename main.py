from flask import Flask, request
import os
import telebot
from pdf2docx import Converter

TOKEN = '7386617987:AAGounvetKHtmtqCxEbY_Idc5M2IfUNSst4'  # Replace with your bot token
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@app.route('/', methods=['POST'])
def webhook():
    update = request.get_json()
    if update:
        bot.process_new_updates([telebot.types.Update.de_json(update)])
    return 'ok'

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 Welcome to Document Converter Bot!\n\n📎 Send me a *PDF* file and I'll convert it to *DOCX* for you!\n\nMore formats coming soon!")

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    file_name = message.document.file_name
    if not file_name.endswith('.pdf'):
        bot.reply_to(message, "⚠️ Please send a valid PDF file.")
        return

    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    input_path = f"./{file_name}"
    output_path = input_path.replace('.pdf', '.docx')

    with open(input_path, 'wb') as f:
        f.write(downloaded_file)

    try:
        bot.send_message(message.chat.id, "⏳ Converting your file, please wait...")
        cv = Converter(input_path)
        cv.convert(output_path)
        cv.close()
        bot.send_document(message.chat.id, open(output_path, 'rb'), caption="✅ Here's your DOCX file!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error converting file: {e}")
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)

if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url='https://your-app-url.onrender.com')  # Replace with your deployed URL
    app.run(host="0.0.0.0", port=5000)
