#!/usr/bin/env python3
"""Royco Dawn Support Bot — static rule-based Telegram bot."""
from __future__ import annotations

import logging
import os

def _read_env_file(path: str) -> dict:
    """Read a .env file manually, tolerating BOM, quotes, and Windows line endings."""
    result = {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                result[key.strip()] = val.strip().strip('"').strip("'")
    except (FileNotFoundError, OSError):
        pass
    return result
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
_env = _read_env_file(_env_path)

BOT_TOKEN = _env.get("BOT_TOKEN") or os.environ.get("BOT_TOKEN")
SUPPORT_CHANNEL_ID = _env.get("SUPPORT_CHANNEL_ID") or os.environ.get("SUPPORT_CHANNEL_ID")

if not BOT_TOKEN:
    raise RuntimeError(f"BOT_TOKEN not set — .env path was: {_env_path}")
if not SUPPORT_CHANNEL_ID:
    raise RuntimeError(f"SUPPORT_CHANNEL_ID not set — .env path was: {_env_path}")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ── Conversation states ────────────────────────────────────────────────────
MENU, SUPPORT_NAME, SUPPORT_EMAIL, SUPPORT_WALLET, SUPPORT_ISSUE = range(5)

# ── FAQ content ────────────────────────────────────────────────────────────
FAQS = {
    "what_is_royco": (
        "What is Royco Dawn?",
        "Royco Dawn is a non-custodial protocol that splits lending positions into two tranches: "
        "a senior tranche that earns a fixed yield with first-loss protection, and a junior tranche "
        "that absorbs risk in exchange for leveraged upside. Think of it as risk-tranching for DeFi "
        "yield: you pick whether you want safety or amplified returns, and the protocol handles the split.",
    ),
    "senior_vs_junior": (
        "Senior vs Junior",
        "Senior Tranche: Earn a fixed, protected yield. Senior depositors have first-loss protection "
        "— if the protocol incurs losses, the Junior tranche absorbs them first.\n\n"
        "Junior Tranche: Accept higher risk in exchange for leveraged yield. Junior depositors earn "
        "a larger share of the risk premium but absorb losses before the Senior tranche is affected.\n\n"
        "Both tranches operate on top of Aave lending markets and are non-custodial.",
    ),
    "vault_products": (
        "Vault Products",
        "Royco Dawn — Senior Vault (srRoyUSDC)\n\n"
        "The Senior Vault is Royco Dawn's capital-preservation product. Depositors receive srRoyUSDC, "
        "a yield-bearing token that aggregates exposure across the Senior tranches of every Dawn market.\n\n"
        "Key properties:\n"
        "- Fixed-style yield: Senior earns a predictable rate, set by each market's risk premium paid by Junior depositors\n"
        "- Loss protection: Junior tranche absorbs first losses up to its buffer — Senior is only impaired if losses exceed the Junior buffer in a given market\n"
        "- Diversified: One deposit, exposure across all live Dawn markets (no need to pick)\n"
        "- Liquid: srRoyUSDC is a transferable ERC-20\n\n"
        'It\'s the "I want stablecoin yield without picking markets or taking first-loss risk" product.',
    ),
    "deposits_withdrawals": (
        "Deposits & Withdrawals",
        "• Deposits: Made directly via dawn.royco.org. KYC is required before depositing.\n"
        "• Withdrawals: Generally instant via the Aave idle buffer. If the buffer is depleted, "
        "withdrawals are processed as liquidity becomes available.",
    ),
    "kyc_eligibility": (
        "KYC & Eligibility",
        "To use Royco Dawn, you must complete KYC/KYB verification.\n"
        "Please note: U.S. persons are strictly prohibited from using the platform.\n"
        'If you are experiencing technical issues with KYC (and you are not a U.S. person), '
        'use the "Escalate to Support" option to contact us.',
    ),
    "fees": (
        "Fees",
        "Protocol fees depend on the tranche:\n"
        "• Senior: 10% performance fee on the yield generated.\n"
        "• Junior (v2): 45% yield share on the risk premium.",
    ),
    "security_audits": (
        "Security & Audits",
        "Royco Dawn has been fully audited by:\n"
        "• Hexens\n"
        "• Cantina\n"
        "• Halborn\n"
        "• Certora\n\n"
        "We also maintain a $250,000 active bug bounty on Immunefi.",
    ),
}

# ── Keyboards ──────────────────────────────────────────────────────────────
def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("What is Royco Dawn?",      callback_data="faq_what_is_royco")],
        [InlineKeyboardButton("Senior vs Junior",          callback_data="faq_senior_vs_junior")],
        [InlineKeyboardButton("Vault Products",            callback_data="faq_vault_products")],
        [InlineKeyboardButton("Deposits & Withdrawals",    callback_data="faq_deposits_withdrawals")],
        [InlineKeyboardButton("KYC & Eligibility",         callback_data="faq_kyc_eligibility")],
        [InlineKeyboardButton("Fees",                      callback_data="faq_fees")],
        [InlineKeyboardButton("Security & Audits",         callback_data="faq_security_audits")],
        [InlineKeyboardButton("🙋 Escalate to Support",   callback_data="support")],
    ])

def followup_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Yes, contact support",  callback_data="support")],
        [InlineKeyboardButton("No, I'm good",          callback_data="done")],
        [InlineKeyboardButton("↩ Return to Main Menu", callback_data="main_menu")],
    ])

# ── Shared helpers ─────────────────────────────────────────────────────────
async def send_main_menu(update: Update, text: str | None = None) -> int:
    msg = text or "Welcome to Royco Dawn Support. Please select a topic below to get started."
    if update.callback_query:
        await update.callback_query.edit_message_text(msg, reply_markup=main_menu_keyboard())
    else:
        await update.effective_message.reply_text(msg, reply_markup=main_menu_keyboard())
    return MENU

# ── Entry point ────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    return await send_main_menu(update)

# ── FAQ handlers ───────────────────────────────────────────────────────────
async def faq_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    key = query.data.removeprefix("faq_")
    _, text = FAQS[key]
    await query.edit_message_text(
        text + "\n\nDo you need to speak with human support?",
        reply_markup=followup_keyboard(),
    )
    return MENU

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await send_main_menu(update)

async def done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "Thanks for using Royco Dawn Support! If you have more questions, "
        "type /start any time. Have a great day!"
    )
    return ConversationHandler.END

# ── Support inquiry flow ───────────────────────────────────────────────────
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data["support"] = {}
    await update.callback_query.edit_message_text(
        "I'll connect you with our support team. Please answer a few quick questions.\n\n"
        "What is your name?"
    )
    return SUPPORT_NAME

async def support_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["support"]["name"] = update.message.text.strip()
    await update.message.reply_text(
        "What is your email address? (So our team can reply to you.)"
    )
    return SUPPORT_EMAIL

async def support_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["support"]["email"] = update.message.text.strip()
    await update.message.reply_text("What is your wallet address?")
    return SUPPORT_WALLET

async def support_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["support"]["wallet"] = update.message.text.strip()
    await update.message.reply_text(
        "Please describe your issue in as much detail as possible."
    )
    return SUPPORT_ISSUE

async def support_issue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data["support"]
    data["issue"] = update.message.text.strip()
    user = update.effective_user

    ticket = (
        "🆕 <b>New Support Request — Royco Dawn</b>\n\n"
        f"👤 <b>Name:</b> {data['name']}\n"
        f"📧 <b>Email:</b> {data['email']}\n"
        f"🔑 <b>Wallet:</b> <code>{data['wallet']}</code>\n"
        f"💬 <b>Issue:</b> {data['issue']}\n"
        f"📱 <b>Telegram:</b> @{user.username or 'N/A'} "
        f"(ID: <code>{user.id}</code>)"
    )

    try:
        await context.bot.send_message(
            chat_id=SUPPORT_CHANNEL_ID,
            text=ticket,
            parse_mode="HTML",
        )
    except Exception as exc:
        logging.error("Failed to send support ticket: %s", exc)

    await update.message.reply_text(
        "Your request has been submitted to our support team. "
        "Someone will follow up with you shortly. "
        "Thank you for reaching out to Royco Dawn Support.\n\n"
        "Type /start to return to the main menu."
    )
    return ConversationHandler.END

# ── Fallback for free text at menu ────────────────────────────────────────
async def free_text_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Please use the menu buttons to navigate, or tap \"Escalate to Support\" "
        "if you need a human. Type /start to bring the menu back.",
        reply_markup=main_menu_keyboard(),
    )
    return MENU

# ── App setup ──────────────────────────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            MENU: [
                CallbackQueryHandler(faq_callback,        pattern=r"^faq_"),
                CallbackQueryHandler(support_start,       pattern=r"^support$"),
                CallbackQueryHandler(main_menu_callback,  pattern=r"^main_menu$"),
                CallbackQueryHandler(done_callback,       pattern=r"^done$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, free_text_fallback),
            ],
            SUPPORT_NAME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, support_name)],
            SUPPORT_EMAIL:  [MessageHandler(filters.TEXT & ~filters.COMMAND, support_email)],
            SUPPORT_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_wallet)],
            SUPPORT_ISSUE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, support_issue)],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
    )

    app.add_handler(conv)
    logging.info("Bot started — polling for updates")
    app.run_polling()

if __name__ == "__main__":
    main()
