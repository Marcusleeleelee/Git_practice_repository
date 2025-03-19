import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from pymongo import MongoClient
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8151273440:AAHIzOtA8sSJLmjrIWZLtefoPlptldfIWbQ"

OPENROUTER_API_KEY = "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"

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


MONGO_URI = "mongodb://localhost:27017/"
client = MongoClient(MONGO_URI)
db = client["chatbot_db"]
chat_collection = db["chat_history"]
print("Connected to MongoDB successfully!")


total_tokens_used = 0


async def ask_gemma(question: str, user_id: int, chat_id: int) -> str:
    global total_tokens_used  
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "google/gemma-3-1b-it:free",
        "messages": [{"role": "user", "content": question}]
    }

    try:
        response = requests.post(OPENROUTER_API_URL, json=data, headers=headers)

        if response.status_code == 200:
            response_json = response.json()
            print(response_json)  

            total_tokens_used = response_json.get("usage", {}).get("completion_tokens", 0)

            if "choices" in response_json and len(response_json["choices"]) > 0:
                bot_response = response_json["choices"][0]["message"]["content"]
                
                chat_data = {
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "message": question,
                    "response": bot_response,
                    "timestamp": datetime.utcnow()
                }
                chat_collection.insert_one(chat_data)

                return bot_response
            else:
                return "Error: No AI response received."

        elif response.status_code == 401:
            return "Error 401: Unauthorized. Please check your OpenRouter API key."
        elif response.status_code == 429:
            return "Error 429: Rate limit exceeded. Please wait and try again."
        else:
            return f"API Error: {response.status_code} - {response.text}"

    except requests.RequestException as e:
        return f"Request failed: {str(e)}"

async def hello_world(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'{update.effective_user.first_name}, welcome!')

async def usage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Total completion tokens used by Gemma: {total_tokens_used}")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    chat_history = chat_collection.find({"user_id": user_id}).sort("timestamp", -1).limit(10)

    history_text = "**Here are the most recent 10 messages in this chat:**\n"
    messages = []
    for i, entry in enumerate(chat_history, start=1):
        messages.append(f"{i}. {entry['message']} - {entry['response']}")
    
    if messages:
        history_text += "\n".join(messages)
    else:
        history_text = "No chat history found."

    await update.message.reply_text(history_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    user_id = update.effective_user.id
    chat_id = update.message.chat_id

    bot_response = await ask_gemma(user_message, user_id, chat_id)
    
    MAX_TELEGRAM_MESSAGE_LENGTH = 4096

    if len(bot_response) > MAX_TELEGRAM_MESSAGE_LENGTH:
        bot_response = bot_response[:MAX_TELEGRAM_MESSAGE_LENGTH]

    await update.message.reply_text(bot_response)

def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("hello", hello_world))
    app.add_handler(CommandHandler("usage", usage))     
    app.add_handler(CommandHandler("history", history)) 

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()