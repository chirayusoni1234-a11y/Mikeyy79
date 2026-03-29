"""
📚 Free Books Telegram Bot
Similar to Ocean of Books — search and get free books via Telegram.

Sources:
- Open Library (openlibrary.org) — metadata + read links
- Project Gutenberg — free public domain books (full download)

Setup:
    pip install python-telegram-bot requests
    Set BOT_TOKEN in config.py or as env variable
"""

import os
import logging
import requests
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ─── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

RESULTS_PER_PAGE = 5

# ─── API Helpers ────────────────────────────────────────────────────────────────

def search_open_library(query: str, page: int = 1) -> dict:
    """Search Open Library for books."""
    url = "https://openlibrary.org/search.json"
    params = {
        "q": query,
        "fields": "key,title,author_name,first_publish_year,cover_i,isbn,number_of_pages_median,subject",
        "limit": RESULTS_PER_PAGE,
        "offset": (page - 1) * RESULTS_PER_PAGE,
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Open Library search error: {e}")
        return {}


def get_gutenberg_books(query: str) -> list:
    """Search Project Gutenberg for free downloadable books."""
    url = "https://gutendex.com/books/"
    params = {"search": query}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("results", [])[:5]
    except Exception as e:
        logger.error(f"Gutenberg search error: {e}")
        return []


def get_book_details(ol_key: str) -> dict:
    """Get full book details from Open Library."""
    url = f"https://openlibrary.org{ol_key}.json"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Book detail error: {e}")
        return {}


def cover_url(cover_id: int, size: str = "M") -> str:
    return f"https://covers.openlibrary.org/b/id/{cover_id}-{size}.jpg"


# ─── Formatters ────────────────────────────────────────────────────────────────

def format_book_card(book: dict) -> str:
    title = book.get("title", "Unknown Title")
    authors = ", ".join(book.get("author_name", ["Unknown Author"])[:3])
    year = book.get("first_publish_year", "N/A")
    pages = book.get("number_of_pages_median", "N/A")
    subjects = book.get("subject", [])
    genres = ", ".join(subjects[:3]) if subjects else "N/A"
    ol_key = book.get("key", "")
    ol_link = f"https://openlibrary.org{ol_key}" if ol_key else ""

    text = (
        f"📖 *{title}*\n"
        f"✍️ {authors}\n"
        f"📅 Year: {year}  |  📄 Pages: {pages}\n"
        f"🏷️ {genres}\n"
    )
    if ol_link:
        text += f"🔗 [Open Library]({ol_link})\n"
    return text


def format_gutenberg_card(book: dict) -> str:
    title = book.get("title", "Unknown")
    authors = ", ".join(a["name"] for a in book.get("authors", [])[:2]) or "Unknown"
    downloads = book.get("download_count", 0)
    formats = book.get("formats", {})

    # Pick best download link
    pdf_url = formats.get("application/pdf", "")
    epub_url = formats.get("application/epub+zip", "")
    txt_url = formats.get("text/plain; charset=utf-8", formats.get("text/plain", ""))

    links = []
    if pdf_url:
        links.append(f"[📄 PDF]({pdf_url})")
    if epub_url:
        links.append(f"[📱 EPUB]({epub_url})")
    if txt_url:
        links.append(f"[📝 TXT]({txt_url})")

    text = (
        f"📗 *{title}*\n"
        f"✍️ {authors}\n"
        f"⬇️ {downloads:,} downloads\n"
    )
    if links:
        text += "📥 Download: " + " | ".join(links)
    return text


# ─── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📚 *Welcome to Free Books Bot!*\n\n"
        "I help you find and download free books from:\n"
        "• 📖 Open Library — millions of books\n"
        "• 🏛️ Project Gutenberg — 70,000+ free classics\n\n"
        "Just send me a *book title*, *author name*, or *topic* to search!\n\n"
        "Commands:\n"
        "/search `<query>` — Search books\n"
        "/gutenberg `<query>` — Search free downloadable classics\n"
        "/help — Show this message"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usage: /search `<book title or author>`", parse_mode="Markdown")
        return
    await do_search(update, context, query, page=1)


async def gutenberg_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usage: /gutenberg `<title or author>`", parse_mode="Markdown")
        return
    await do_gutenberg_search(update, context, query)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Any plain text message triggers an Open Library search."""
    query = update.message.text.strip()
    if query.startswith("/"):
        return
    await do_search(update, context, query, page=1)


async def do_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str, page: int):
    msg = await (update.message or update.callback_query.message).reply_text(
        f"🔍 Searching for *{query}*...", parse_mode="Markdown"
    )

    data = search_open_library(query, page)
    books = data.get("docs", [])
    total = data.get("numFound", 0)

    if not books:
        await msg.edit_text("❌ No books found. Try a different query.")
        return

    # Store search state in context
    context.user_data["last_query"] = query
    context.user_data["last_page"] = page

    response = f"📚 *Results for \"{query}\"* (Page {page})\n\n"
    for i, book in enumerate(books, 1):
        response += f"{i}. {format_book_card(book)}\n"

    # Pagination buttons
    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page:{page-1}:{query}"))
    if total > page * RESULTS_PER_PAGE:
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"page:{page+1}:{query}"))

    keyboard = []
    if buttons:
        keyboard.append(buttons)
    keyboard.append([
        InlineKeyboardButton("🏛️ Search Gutenberg Too", callback_data=f"gutenberg:{query}")
    ])

    await msg.edit_text(
        response,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True,
    )


async def do_gutenberg_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
    msg_obj = update.message or update.callback_query.message
    msg = await msg_obj.reply_text(f"🏛️ Searching Gutenberg for *{query}*...", parse_mode="Markdown")

    books = get_gutenberg_books(query)

    if not books:
        await msg.edit_text("❌ No Gutenberg books found for that query.")
        return

    response = f"🏛️ *Free Books from Project Gutenberg*\n_Query: {query}_\n\n"
    for book in books:
        response += format_gutenberg_card(book) + "\n\n"

    await msg.edit_text(
        response,
        parse_mode="Markdown",
        disable_web_page_preview=False,
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("page:"):
        _, page_str, search_query = data.split(":", 2)
        await do_search(update, context, search_query, int(page_str))

    elif data.startswith("gutenberg:"):
        _, search_query = data.split(":", 1)
        await do_gutenberg_search(update, context, search_query)


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("gutenberg", gutenberg_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
