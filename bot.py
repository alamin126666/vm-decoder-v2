"""
bot.py — Main Telegram Bot
2-Step VM Decoder Bot
"""
import os
import json
import asyncio
import tempfile
import re
from pathlib import Path
from telegram import Update, Document
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

from decoder import decode_outer_layer, apply_patches, inject_capture_script, reconstruct_from_capture, extract_body_css
from browser_worker import run_with_cdp

TOKEN = os.getenv('BOT_TOKEN', '')
ADMIN_IDS = list(map(int, os.getenv('ADMIN_IDS', '0').split(',')))

# User state storage
user_states = {}

# ── /start ───────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "😈 *VM DECODER BOT*\n\n"
        "*কীভাবে ব্যবহার করবে:*\n\n"
        "📌 *Step 1:*\n"
        "Encrypted HTML file পাঠাও\n"
        "→ Bot automatically:\n"
        "  • Outer layer decode করবে\n"
        "  • Anti-debug blocks remove করবে\n"
        "  • Capture script inject করবে\n"
        "  • Ready HTML ফেরত দেবে\n\n"
        "📌 *Step 2:*\n"
        "Ready HTML টা browser এ open করো\n"
        "Login/key দাও, সব interact করো\n"
        "60s পর auto-download হবে\n\n"
        "📌 *Step 3:*\n"
        "Downloaded JSON file পাঠাও\n"
        "→ Bot original JS + clean HTML দেবে!\n\n"
        "🔥 *CDP Mode:* Fully automatic (no manual browser needed)\n"
        "Use /cdp command after sending HTML",
        parse_mode=ParseMode.MARKDOWN
    )

# ── /help ────────────────────────────────────────────────────
async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *Commands:*\n\n"
        "/start — শুরু করো\n"
        "/help — এই message\n"
        "/cdp — CDP auto mode (HTML পাঠানোর পর)\n"
        "/status — current status\n"
        "/reset — reset state\n\n"
        "📁 *Supported files:*\n"
        "• Encrypted HTML → Step 1\n"
        "• Runtime JSON → Step 2 (Final output)",
        parse_mode=ParseMode.MARKDOWN
    )

# ── /status ──────────────────────────────────────────────────
async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = user_states.get(uid, {})
    if not state:
        await update.message.reply_text("📊 No active session. Send an HTML file to start!")
    else:
        await update.message.reply_text(
            f"📊 *Current Status:*\n\n"
            f"Step: {state.get('step', 'N/A')}\n"
            f"File: {state.get('filename', 'N/A')}\n"
            f"Mode: {state.get('mode', 'manual')}",
            parse_mode=ParseMode.MARKDOWN
        )

# ── /reset ───────────────────────────────────────────────────
async def reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_states.pop(uid, None)
    await update.message.reply_text("✅ State reset! Send a new HTML file.")

# ── /cdp — Auto mode ─────────────────────────────────────────
async def cdp_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = user_states.get(uid, {})

    if not state.get('patched_html'):
        await update.message.reply_text("❌ আগে HTML file পাঠাও!")
        return

    await update.message.reply_text(
        "🚀 *CDP Auto Mode শুরু হচ্ছে...*\n\n"
        "Playwright Chromium চালু হচ্ছে...\n"
        "VM execution হবে automatically\n"
        "90 সেকেন্ড লাগতে পারে ⏳",
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        html = state['patched_html']
        msg = await update.message.reply_text("⏳ Chromium চালু হচ্ছে...")

        # Run with CDP
        capture = await run_with_cdp(html, timeout=75)

        await msg.edit_text(
            f"✅ CDP Capture সম্পন্ন!\n\n"
            f"Strings: {len(capture.get('unique_strings', []))}\n"
            f"Network calls: {len(capture.get('network', []))}\n"
            f"Eval calls: {len(capture.get('eval_calls', []))}\n"
            f"Dynamic scripts: {len(capture.get('scripts_executed', []))}\n\n"
            f"Processing..."
        )

        # Process capture
        await process_capture(update, ctx, capture, state)

    except Exception as e:
        await update.message.reply_text(f"❌ CDP Error: {str(e)[:200]}")

# ── File Handler ─────────────────────────────────────────────
async def handle_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    doc: Document = update.message.document

    if not doc:
        return

    filename = doc.file_name or ''
    ext = Path(filename).suffix.lower()

    # HTML file → Step 1
    if ext == '.html' or ext == '.htm':
        await handle_html(update, ctx, doc, filename)

    # JSON file → Step 2
    elif ext == '.json':
        await handle_json(update, ctx, doc, filename)

    else:
        await update.message.reply_text(
            "❌ শুধু .html বা .json file পাঠাও!"
        )

# ── STEP 1: HTML Processing ───────────────────────────────────
async def handle_html(update: Update, ctx: ContextTypes.DEFAULT_TYPE, doc, filename):
    uid = update.effective_user.id

    msg = await update.message.reply_text("🔍 HTML file processing শুরু...")

    try:
        # Download file
        file = await ctx.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            await file.download_to_drive(f.name)
            html_content = open(f.name, 'r', errors='replace').read()

        await msg.edit_text("🔍 Step 1: Outer layer detecting...")

        # Step 1: Decode outer layer
        result = decode_outer_layer(html_content)

        if result['decoded']:
            working_html = result['html']
            await msg.edit_text("✅ Outer layer decoded!\n🛡️ Anti-debug patches applying...")
        else:
            working_html = html_content
            await msg.edit_text("ℹ️ No outer encryption found.\n🛡️ Anti-debug patches applying...")

        # Step 2: Apply patches
        patch_result = apply_patches(working_html)
        if isinstance(patch_result, tuple):
            patched_html, patches = patch_result
        else:
            patched_html = patch_result
            patches = []

        # Step 3: Inject capture script
        final_html = inject_capture_script(patched_html)

        # Save state
        user_states[uid] = {
            'step': 'waiting_json',
            'filename': filename,
            'original_html': html_content,
            'decoded_html': working_html,
            'patched_html': patched_html,
            'capture_injected_html': final_html,
            'mode': 'manual'
        }

        # Send patched HTML
        with tempfile.NamedTemporaryFile(suffix='_ready.html', delete=False, mode='w', encoding='utf-8') as tf:
            tf.write(final_html)
            ready_path = tf.name

        patches_text = '\n'.join([f"✅ {p}" for p in patches]) if patches else "✅ Standard patches applied"

        await msg.edit_text(
            f"✅ *Step 1 Complete!*\n\n"
            f"*Patches applied:*\n{patches_text}\n\n"
            f"*Now:*\n"
            f"1️⃣ নিচের HTML file টা download করো\n"
            f"2️⃣ Browser এ open করো\n"
            f"3️⃣ Login করো / Key দাও / সব interact করো\n"
            f"4️⃣ 60s পর JSON auto-download হবে\n"
            f"5️⃣ সেই JSON file আমাকে পাঠাও\n\n"
            f"🤖 *অথবা /cdp লিখলে automatic করব!*",
            parse_mode=ParseMode.MARKDOWN
        )

        # ── File 1: Script injected (for browser capture) ──
        await ctx.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(ready_path, 'rb'),
            filename=f'READY_{filename}',
            caption=(
                "📄 *File 1 — READY HTML*\n\n"
                "✅ 6 blocks bypassed\n"
                "✅ Capture script injected\n\n"
                "👉 Browser এ open করো\n"
                "👉 Login/key দাও, interact করো\n"
                "👉 60s পর JSON auto-download হবে\n"
                "👉 সেই JSON আমাকে পাঠাও"
            )
        )

        # ── File 2: Body + CSS only (no scripts) ──
        body_css_html = extract_body_css(working_html)
        with tempfile.NamedTemporaryFile(suffix='_body_css.html', delete=False, mode='w', encoding='utf-8') as tf2:
            tf2.write(body_css_html)
            body_css_path = tf2.name

        await ctx.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(body_css_path, 'rb'),
            filename=f'BODY_CSS_{filename}',
            caption=(
                "📄 *File 2 — BODY + CSS ONLY*\n\n"
                "✅ সব scripts removed\n"
                "✅ শুধু Body + CSS\n\n"
                "👉 এই file + JSON দিলে\n"
                "   Claude/ChatGPT final HTML বানাবে\n"
                "👉 অথবা /cdp দিলে bot নিজেই করবে"
            )
        )

    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)[:300]}")

# ── STEP 2: JSON Processing ───────────────────────────────────
async def handle_json(update: Update, ctx: ContextTypes.DEFAULT_TYPE, doc, filename):
    uid = update.effective_user.id
    state = user_states.get(uid, {})

    msg = await update.message.reply_text("🔬 JSON processing শুরু...")

    try:
        file = await ctx.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            await file.download_to_drive(f.name)
            capture_data = json.loads(open(f.name, 'r').read())

        await process_capture(update, ctx, capture_data, state, msg)

    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)[:300]}")

# ── PROCESS CAPTURE ───────────────────────────────────────────
async def process_capture(update, ctx, capture_data, state, msg=None):
    uid = update.effective_user.id

    if msg:
        await msg.edit_text("🔬 Strings analyzing...")

    # Extract data
    extracted = reconstruct_from_capture(capture_data, state.get('decoded_html', ''))

    apis = extracted.get('apis', [])
    keys = extracted.get('keys', [])
    functions = extracted.get('functions', [])
    fetch_calls = extracted.get('fetch_calls', [])
    xhr_calls = extracted.get('xhr_calls', [])
    ls_data = extracted.get('localStorage', [])
    eval_calls = extracted.get('eval_calls', [])
    all_strings = extracted.get('all_strings', [])

    # Build summary
    summary_lines = []
    if keys: summary_lines.append(f"🔑 Keys: `{'`, `'.join(keys[:5])}`")
    if apis: summary_lines.append(f"🌐 APIs found: {len(apis)}")
    for api in apis[:5]:
        summary_lines.append(f"   → `{api[:80]}`")
    if functions: summary_lines.append(f"⚙️ Functions: {len(functions)}")
    if fetch_calls: summary_lines.append(f"📡 Fetch calls: {len(fetch_calls)}")
    if xhr_calls: summary_lines.append(f"📡 XHR calls: {len(xhr_calls)}")
    if ls_data: summary_lines.append(f"💾 localStorage ops: {len(ls_data)}")
    if eval_calls: summary_lines.append(f"⚡ Eval calls: {len(eval_calls)}")
    summary_lines.append(f"📝 Total strings: {len(all_strings)}")

    summary_text = '\n'.join(summary_lines)

    # Build clean HTML if we have original
    if state.get('decoded_html'):
        decoded_html = state['decoded_html']

        # Extract CSS + body from decoded HTML
        styles = re.findall(r'<style[^>]*>(.*?)</style>', decoded_html, re.DOTALL)
        css = styles[0] if styles else ""
        body_match = re.search(r'<body[^>]*>(.*?)</body>', decoded_html, re.DOTALL)
        body_clean = re.sub(r'<script[^>]*>.*?</script>', '', body_match.group(1) if body_match else '', flags=re.DOTALL)
        head_match = re.search(r'<head[^>]*>(.*?)</head>', decoded_html, re.DOTALL)
        head_clean = re.sub(r'<script[^>]*>.*?</script>', '', head_match.group(1) if head_match else '', flags=re.DOTALL)
        head_clean = re.sub(r'<style[^>]*>.*?</style>', '', head_clean, flags=re.DOTALL)

        # Build JS from captured data
        js_parts = ['/* 😈 RECONSTRUCTED FROM VM RUNTIME CAPTURE */\n"use strict";\n']

        if apis:
            js_parts.append(f'// APIs\nconst __APIS__ = {json.dumps(apis, indent=2)};\n')
        if keys:
            js_parts.append(f'// Keys\nconst __KEYS__ = {json.dumps(keys, indent=2)};\n')
        if functions:
            js_parts.append(f'// Functions found: {", ".join(functions[:20])}\n')
        if ls_data:
            js_parts.append(f'// localStorage: {json.dumps([x for x in ls_data if x.get("op")=="set"][:10], indent=2)}\n')
        if eval_calls:
            js_parts.append('\n// ── EVAL\'D CODE (original logic) ──\n')
            for i, ev in enumerate(eval_calls[:10]):
                code = ev.get('code', '') if isinstance(ev, dict) else str(ev)
                js_parts.append(f'// Eval {i+1} ({len(code)} chars):\n{code}\n\n')

        # Add fetch responses (most valuable!)
        fetch_responses = [x for x in fetch_calls if x.get('response')]
        if fetch_responses:
            js_parts.append('\n// ── API RESPONSES ──\n')
            for fr in fetch_responses[:5]:
                js_parts.append(f'// {fr.get("url","")}\n// Response: {str(fr.get("response",""))[:200]}\n\n')

        full_js = '\n'.join(js_parts)

        # Build final HTML
        final_html = f"""<!DOCTYPE html>
<html lang="bn">
<head>
{head_clean}
<style>
{css}
</style>
</head>
<body>
{body_clean}
<script>
{full_js}
</script>
</body>
</html>"""

        # Save and send
        with tempfile.NamedTemporaryFile(suffix='_decoded.html', delete=False, mode='w', encoding='utf-8') as tf:
            tf.write(final_html)
            out_path = tf.name

        if msg:
            await msg.edit_text(
                f"✅ *Step 2 Complete!*\n\n{summary_text}",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                f"✅ *Decode Complete!*\n\n{summary_text}",
                parse_mode=ParseMode.MARKDOWN
            )

        await ctx.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(out_path, 'rb'),
            filename='DECODED_FINAL.html',
            caption="😈 Original decoded HTML! সব কিছু আছে!"
        )

    else:
        # No HTML, just send analysis
        if msg:
            await msg.edit_text(
                f"✅ *Capture Analyzed!*\n\n{summary_text}",
                parse_mode=ParseMode.MARKDOWN
            )

        # Send full JSON report
        report = json.dumps(extracted, indent=2, ensure_ascii=False)
        with tempfile.NamedTemporaryFile(suffix='_analysis.json', delete=False, mode='w') as tf:
            tf.write(report)
            report_path = tf.name

        await ctx.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(report_path, 'rb'),
            filename='vm_analysis.json',
            caption="📊 Full analysis report"
        )

    # Update state
    if uid in user_states:
        user_states[uid]['step'] = 'complete'


# ── Main ──────────────────────────────────────────────────────
def main():
    if not TOKEN:
        print("❌ BOT_TOKEN not set! Add it to Railway environment variables.")
        return

    print("🚀 VM Decoder Bot starting...")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("cdp", cdp_mode))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    print("✅ Bot running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
