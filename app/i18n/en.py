"""English messages for bot/API/services."""

from __future__ import annotations

MESSAGES: dict[str, dict] = {
    "common": {
        "yes": "Yes",
        "no": "No",
        "ok": "OK",
        "cancel": "Cancel",
        "back": "Back",
        "close": "Close",
        "save": "Save",
        "open": "Open",
        "edit": "Edit",
        "delete": "Delete",
        "loading": "Loading…",
        "error": "Error",
        "success": "Done",
        "on": "On",
        "off": "Off",
        "enabled": "Enabled",
        "disabled": "Disabled",
        "configure": "Set up",
        "manage": "Manage",
        "more": "More",
        "open_app": "Open app",
        "open_panel": "Open Mini App",
        "support": "Support",
        "premium": "Premium",
        "free": "Free",
    },
    "lang": {
        "ru": "Русский",
        "en": "English",
        "picker_title": "App language",
        "picker_hint": "Choose the language for the bot and Mini App",
        "saved_ru": "Language updated: Русский",
        "saved_en": "Language updated: English",
        "invalid": "Only ru and en are supported",
    },
    "bot": {
        "welcome": {
            "title": "AntiSpam Guard",
            "intro": (
                "Hi 👋\n\n"
                "I am [AntiSpam Guard](https://t.me/GuardAntiSpam_Bot) 🛡️\n\n"
                "I keep your group clean.\n"
                "I cut spam, links, raids, scams and noise.\n\n"
                "Guard features:\n"
                "Languages\n"
                "Donations\n"
                "Referral program\n"
                "Account balance\n\n"
                "Full guide is inside the app under the *i* icon.\n\n"
                "Support: @Help_guard"
            ),
        },
        "profile": {
            "description": (
                "🔥 AntiSpam Guard — a new format of serious chat protection.\n\n"
                "Spam, links, casino, scams, raids, shady schemes — cleaned up automatically.\n\n"
                "Flexible setup for any community: stopwords, anti-boost, newcomers, hard dictionary, "
                "antispam base, admin reports — all inside Mini App, no command rituals.\n\n"
                "Add the bot as admin, tap Menu, and set the rules for your chat in minutes.\n\n"
                "Support: @Help_guard"
            ),
            "short_description": (
                "AntiSpam Guard: flexible group protection in a Mini App. @Help_guard"
            ),
            "name": "AntiSpam Guard",
            "welcome_banner_caption": "Support: @Help_guard",
        },
        "lang_cmd": {
            "prompt": "Choose interface language:",
            "btn_ru": "Русский",
            "btn_en": "English",
            "saved": "Language saved.",
        },
        "start": {
            "connect_text": (
                "➕ *Connect protection*\n\n"
                "Two steps:\n\n"
                "1️⃣ Add the bot to your group\n\n"
                "2️⃣ Grant admin rights:\n"
                "✅ delete messages\n"
                "➕ preferably ban members\n\n"
                "After that the group will appear in the Mini App automatically."
            ),
            "rules_text": (
                "📜 *Guard*\n\n"
                "The guide and feature overview are in the app under the *i* icon."
            ),
            "addgroup_text": (
                "➕ *Add the bot to a group*\n\n"
                "Tap the *button below the input field* — you’ll pick a group, then Telegram will prompt you to promote the bot.\n"
            ),
            "btn_add_bot": "➕ Add bot to group",
            "btn_connect": "➕ Connect protection",
            "btn_panel": "🧨 Control panel",
            "btn_rules": "📜 What I do",
            "btn_back": "⬅️ Back",
            "addgroup_step1": "1️⃣ Tap the *button below the input* — the group picker opens.",
            "addgroup_step2": "2️⃣ Pick a group and grant the bot admin rights.",
            "inline_pick_group_admin": "📋 Pick group and grant rights",
            "group_reports_connected": (
                "✅ Reports chat connected.\n"
                "Reports for «{title}» will be sent here."
            ),
            "group_need_bot_admin": "To enable protection, make me an administrator in this group.",
            "group_actor_denied": (
                "Only an *administrator* can connect protection from the group, "
                "or a message *from the linked channel* (if this is a channel discussion group).\n\n"
                "If “anonymous admin” is on and the post is not from the channel — disable anonymity for admins "
                "or send /start from your personal Telegram (group creator)."
            ),
            "group_creator_resolve_fail": (
                "Could not resolve the group creator for Guard. "
                "Open the panel from a private chat with the bot or try again after granting the bot admin rights."
            ),
            "group_limit_reached": (
                "❌ Connected chat limit reached for your plan.\n"
                "Open the panel → Plan & billing or remove extra groups in Connected chats."
            ),
            "group_owner_conflict": (
                "ℹ️ This group is already linked to another Guard account (not this group’s creator).\n\n"
                "To transfer access — only the current cabinet owner: *Admins & access*."
            ),
            "group_log_conflict": "ℹ️ This group is used as a reports chat or can’t be protected. Check messages in DMs.",
            "group_connect_fail": "Could not enable protection. Open the panel from a private chat with the bot or try later.",
            "cleanup_done": "🧹 *Deleted-account cleanup*\n\nChecked: {checked}\nRemoved deleted accounts: {kicked}",
            "cleanup_error": "Cleanup error: {error}",
            "no_access_chat": "No access to this group.",
            "reports_no_access": "No access to this group. Open *Reports* in the panel for the right chat.",
            "reports_select_group_first": (
                "First select a group in the app: *Connected chats* → *Reports*, "
                "or *Pick* the group you need, then “Connect reports chat” again."
            ),
            "reports_pick_hint": (
                "⬅️ *Use Guard via the «Menu» button above.*\n\n"
                "The button under the input is disabled.\n"
                "Tap below and pick the group for reports."
            ),
            "reports_pick_btn": "📋 Pick reports chat",
            "reports_pick_open_fail": "Could not open the reports chat picker. Open *Reports* in the app and try again.",
            "cabinet_added": (
                "✅ You were added as admin to shared cabinet(s): *{n}*.\n"
                "Open the shared cabinet and go to the *Access* tab."
            ),
            "cabinet_open_btn": "🚀 Open shared cabinet",
            "panel_open_fail": "❌ Could not open the panel. Send /panel or try later.\n\nError: {error}",
            "preview_fail": "Could not send preview: {error}",
        },
        "onboarding": {
            "intro": (
                "😈 *AntiSpam Guard*\n\n"
                "I protect Telegram chats from:\n\n"
                "• spam\n"
                "• links\n"
                "• raids\n"
                "• bots\n\n"
                "Pick an action:"
            ),
            "btn_connect": "➕ Connect protection",
            "btn_panel": "🧨 Control panel",
            "btn_reports": "🧾 How to enable reports",
            "btn_test": "🧪 Test the bot",
            "btn_back": "⬅️ Back",
            "add_chat": (
                "➕ *Connect protection*\n\n"
                "1️⃣ Add the bot to your group\n\n"
                "2️⃣ Grant admin rights:\n"
                "✅ Delete messages\n"
                "➕ Preferably ban members\n\n"
                "3️⃣ In the group send:\n"
                "`/check`\n\n"
                "After that the chat will show up in the panel."
            ),
            "logs": (
                "🧾 *Moderation reports*\n\n"
                "It’s best to use a separate group.\n\n"
                "1️⃣ Create a group (e.g. AntiSpam Logs)\n"
                "2️⃣ Add the bot there\n"
                "3️⃣ Grant admin rights\n\n"
                "Then pick that group\n"
                "in the control panel."
            ),
            "test": (
                "🧪 *Bot check*\n\n"
                "In the protected chat send:\n\n"
                "🔗 a link\n"
                "`https://t.me/test`\n\n"
                "🏷 a mention\n"
                "`@username`\n\n"
                "If Anti-edit is on:\n"
                "1️⃣ send text\n"
                "2️⃣ edit it\n"
                "3️⃣ add a link"
            ),
            "setlog_reply": (
                "Connecting a reports chat is now done from the panel.\n"
                "Open the group settings and tap *Connect reports chat*."
            ),
            "check_reply": (
                "Connecting groups is now done from the panel.\n"
                "Open a private chat with the bot and tap *{btn_add}* (or *{btn_connect}*)."
            ),
        },
    },
    "billing_panel": {
        "title": "🛡 *Guard Premium*",
        "tariff_line": "Plan: *{label}*",
        "chats_count": "Connected chats: *{count} / {limit}*",
        "subscription_until": "Subscription until: *{until}*",
        "description_body": (
            "Basic protection is free.\n"
            "But if you have several chats or need serious protection —\n"
            "enable Guard Premium.\n\n"
            "Premium unlocks advanced features:\n\n"
            "📈 Anti-boost\n"
            "👶 Newbies mode\n"
            "🔕 Silence mode\n"
            "📊 Advanced filter settings\n"
            "📡 More connected chats\n"
            "⚙ Flexible punishments and spam control\n\n"
            "Guard becomes a full moderator for your group.\n\n"
            "Pick a subscription period:"
        ),
        "promo_btn": "🎁 Enter promo code",
        "back_btn": "⬅️ Back",
        "promo_prompt": "🎁 Send the *promo code* in one message. Cancel: /cancel",
        "plan_invalid": "Invalid plan.",
        "yookassa_fail": "Failed to create payment. Try later or open the “Plan & billing” section.",
        "pay_screen": (
            "💳 *{label}*\n\n"
            "Tap the button below — the YooKassa payment page will open.\n"
            "After a successful payment, Premium will activate automatically within a few seconds."
        ),
        "pay_btn": "Open payment",
        "back_to_plans": "⬅️ Back to plans",
        "no_yookassa": (
            "💳 *{label}*\n\n"
            "Payment in the bot is not configured (no YooKassa keys in env).\n"
            "For now, you can subscribe via @pastukh_viscera."
        ),
        "months_singular": "1 month",
        "months_few": "{n} months",
        "months_many": "{n} months",
        "cmd_premium_screen": (
            "🛡 *Guard Premium*\n\n"
            "*Free tier:*\n"
            "• 1 chat\n"
            "• basic protection\n\n"
            "*Premium:*\n"
            "• up to 20 chats\n"
            "• anti-boost\n"
            "• newbie mode\n"
            "• advanced filters\n"
            "• stronger protection\n\n"
            "Pick a subscription period:"
        ),
        "feature_block": (
            "⚠ This feature is only available in *Guard Premium*.\n\n"
            "Basic protection is free,\n"
            "but advanced tools require a subscription.\n\n"
            "Guard can protect up to 20 chats\n"
            "and enable advanced filtering modes.\n\n"
            "Get Premium?"
        ),
        "open_subscription": "💳 Open subscription",
        "plan_btn": {
            "1": "🛡 1 month — 490 ₽",
            "3": "⚡ 3 months — 990 ₽",
            "6": "📅 6 months — 1590 ₽",
            "12": "👑 12 months — 2790 ₽",
            "24": "💎 24 months — 4790 ₽",
            "72": "🚀 72 months — 10 990 ₽",
        },
    },
    "panel": {
        "status_title": "Status",
        "tariff_label": "Plan",
        "tariff_premium": "Premium",
        "tariff_free": "Free",
        "open_app_short": "Open app",
        "open_panel_short": "Open panel",
        "buttons": {
            "support": "Support",
            "language": "Language",
            "settings": "Settings",
            "protection": "Protection",
            "account": "Account",
            "chats": "Connected chats",
            "filters": "Filters",
            "tokens": "Tokens",
        },
    },
    "inline": {
        "main_menu": {
            "open_panel": "Open panel",
            "protection": "Protection",
            "account": "Account",
            "partner": "Partner",
            "broadcast": "Broadcast",
            "support": "Support",
            "connected_chats": "Connected chats",
            "settings": "Settings",
            "filters": "Filters",
            "punishments": "Punishments",
            "newbies": "Newcomers",
            "stopwords": "Stopwords",
            "reports": "Reports",
            "back": "Back",
            "configure": "Set up",
            "manage": "Manage",
            "buy_premium": "Buy Premium",
            "renew_premium": "Renew Premium",
            "get_premium": "Get Premium",
            "tokens": "Tokens",
            "balance": "Balance",
            "history": "History",
            "channels": "Channels",
            "groups": "Groups",
            "autoposts": "Autoposts",
            "broadcasts": "Broadcasts",
            "title_main": "Guard panel",
            "title_protection": "🛡 Protection",
            "title_account": "👤 Account",
            "title_chats": "💬 Connected chats",
            "title_filters": "🧰 Filters",
            "title_punishments": "⚖️ Punishments",
            "title_newbies": "🧑‍🚀 Newcomers",
            "title_stopwords": "🚫 Stopwords",
            "title_settings": "⚙️ Settings",
            "language": "🌐 Language",
            "deeplink_hint": "Tap the button below to open in Mini App.",
            "no_chats_admin": "No chats where you are an admin.",
            "chats_hint": "Pick a chat to open its settings.",
        },
        "moderation": {
            "log": {
                "unban": "Unban",
                "unmute": "Unmute",
                "details": "Details",
            },
        },
        "protection": {
            "open": "Open protection",
            "rules": "Rules",
            "test": "Test",
            "view_reports": "View reports",
            "screen_title": "🛡 *Protection*",
            "chat_label": "Chat",
            "current_settings": "*Current section settings:*",
            "links": "🔗 Links",
            "media": "🖼 Media / stickers",
            "buttons": "🔘 Buttons",
            "join_msg": "👥 “joined the group” messages",
            "left_msg": "🚪 “left the group” messages",
            "silence": "🔇 Silence mode",
            "antispam": "🛡 Anti-spam",
            "punishments": "😈 Punishments",
            "newbies": "👶 Newbies",
            "stopwords_label": "🧠 Stop words",
            "guard_messages": "📢 Guard messages",
            "antinakrutka": "📈 Anti-boost",
            "antispam_db": "📋 Anti-spam DB (on join)",
            "hard_dict": "🚫 Hard dictionary",
            "profanity_short": "profanity",
            "jobs_short": "side jobs",
            "casino_short": "casino",
            "select_below": "_Pick an item below to change._",
            "delete_act": "Delete",
            "keep_act": "Keep",
            "on": "ON",
            "off": "OFF",
            "mute_for": "mute",
            "newbie_window_min": "window",
            "stopwords_words": "{count} words",
            "stopwords_not_set": "not configured",
            "every_n_deletions": "every *{n}* deletions, interval *{m}* min",
            "kb_filters": "⚙ Filters",
            "kb_punishments": "🔨 Punishments",
            "kb_newbies": "👶 Newbies",
            "kb_stopwords": "🧠 Stop words",
            "kb_public_alerts": "📢 Public messages",
            "kb_antinakrutka": "📈 Anti-boost",
            "kb_back": "⬅️ Back",
        },
    },
    "billing": {
        "premium": {
            "active": "Premium is active",
            "inactive": "Premium is inactive",
            "until": "Active until {date}",
            "extend": "Renew Premium",
            "buy": "Buy Premium",
            "renew_failed": "Couldn't renew the subscription",
            "trial_left": "Trial Premium: {days_left}",
        },
        "promo": {
            "applied": "Promo applied: +{days} day(s)",
            "invalid": "Promo code not found or already used",
            "expired": "Promo code has expired",
        },
        "plans_title": "Premium plans",
        "panel_active": "Premium is active",
        "panel_inactive": "Premium is inactive",
        "panel_until": "Active until: {date}",
        "panel_no_chats": "No connected chats.",
        "panel_chats_count": "Connected chats: {count}",
        "guardian": {
            "subscription_until_none": "—",
            "payment_success": (
                "✅ *Payment successful*\n\n"
                "*Guard Premium* activated for *{period}*\n"
                "Amount: *{amount}* ₽\n"
                "Subscription valid until: *{until}*\n\n"
                "Subscription gift (AURUM ✨): *{gift_aurum}*\n"
                "AURUM balance: *{aurum_balance}* ✨\n"
                "Partner tokens: *{bonus_tokens}* ⚡\n\n"
                "Now available:\n"
                "👶 newcomers mode · 🔕 silence mode\n"
                "📊 advanced filters · 📈 anti-boost\n"
                "📡 up to *20 chats* and flexible protection"
            ),
            "subscription_renewal_header": (
                "✅ *Guard* renewal successful.\n\n"
                "Thanks for staying with us — we’ll keep your chats protected 🛡"
            ),
            "tokens_payment_success": (
                "✅ *AURUM payment successful*\n\n"
                "Added: *{added}* ✨AURUM\n"
                "Amount: *{amount}* ₽\n\n"
                "AURUM is spent on broadcasts and future AI features. "
                "When it runs out, buy another pack in *Tokens*."
            ),
            "probe_binding_success": (
                "✅ Test plan *2 days / 1 ₽* activated.\n\n"
                "Card saved: *{saved}*{card_tail}\n\n"
                "Use this flow to verify renewal reminders."
            ),
            "probe_card_saved_yes": "yes",
            "probe_card_saved_no": "no",
            "btn_configure_broadcast": "🔵 Set up broadcast",
            "btn_receipt": "🧾 Receipt",
            "promo_confirm_sub": (
                "✅ *Guard activation confirmed*\n\n"
                "Promo code: *{code}*\n"
                "Guard Premium: *{period}*\n"
                "Valid until: *{until}*{bonus}\n\n"
                "Protection is on — you can open broadcasts."
            ),
            "promo_confirm_tokens": (
                "✅ *Guard applied promo bonuses*\n\n"
                "Promo code: *{code}*{bonus}\n\n"
                "Tokens are ready to use in broadcasts."
            ),
            "promo_period_forever": "open-ended",
            "promo_period_days": "for {days} days",
            "promo_bonus_line": "\nCredited: *{parts}*",
            "partner_commission": (
                "🎉 *Guard: partner payout*\n\n"
                "Level: *{level}*\n"
                "Rate: *{rate_pct}%*\n"
                "Credited: *{reward_tokens}* ⚡ (*{reward_rub}* ₽)\n"
                "Current balance: *{balance_tokens}* ⚡ (*{balance_rub}* ₽)"
            ),
            "autorenew_card_revoked": (
                "⚠️ *Guard*\n\n"
                "Premium auto-renew failed: your bank or YooKassa revoked consent for recurring charges.\n\n"
                "The saved card link was cleared. To enable auto-renew again, pay for a subscription in the app "
                "and save the payment method."
            ),
            "yk_desc_premium_months": "Guard Premium — {months} mo.",
            "yk_desc_tokens": "Guard AURUM ×{count}",
            "yk_desc_binding_probe": "Guard — card link test 2d / 1 ₽",
            "yk_desc_autorenew": "Guard Premium auto-renewal — {months} mo.",
            "admin_missing_receipt_dm": (
                "⚠️ *Guard billing alert*\n\n"
                "Successful payment arrived without a `receipt_url`.\n"
                "user_tg_id: `{user_tg_id}`\n"
                "payment_db_id: `{payment_db_id}`\n"
                "yookassa_payment_id: `{yookassa_payment_id}`\n"
                "amount: `{amount}` RUB"
            ),
            "incident_payment_notify_failed": (
                "After a successful payment, the bot could not send a DM to the user (Telegram or network). "
                "Common reasons: the user never pressed Start with the bot, or blocked the bot. "
                "Also verify BOT_TOKEN on the API service."
            ),
        },
    },
    "guard": {
        "spam_spike": {
            "group_ping": (
                "⚠️ <b>Guard</b>: a <b>spam activity</b> spike was detected (filters fired many times in a short window).\n"
                "💀 The chat owner has been notified. Guard is holding the line and pressing spam waves."
            ),
            "dm_group_ping_footer": (
                "\n\nA short notice was also posted <b>in the group chat</b> — "
                "local Telegram admins will see it in the feed."
            ),
            "dm_title": "⚠️ <b>Spam spike</b>\n\n",
            "dm_stats": (
                "Chat: <b>{chat_title}</b>\n"
                "In the last ~{window_min} min: spam filters fired <b>{spam_cnt}</b> time(s), "
                "new members — <b>{joins_cnt}</b>.\n\n"
                "<b>Consider tightening in settings:</b>\n{hints}"
            ),
            "btn_protection": "🛡 Protection",
            "hint_default": (
                "• Turn on core filters under Protection and review the punishment mode (delete/mute)."
            ),
            "hint_newbie": "• Newcomer mode — stricter on early messages after join.",
            "hint_silence": "• Post-join silence — reduce spam in the first minutes.",
            "hint_antinakrutka": "• Anti-boost — react to mass joins.",
            "hint_antispam_db": "• Anti-spam DB on join — block known offenders.",
            "hint_captcha": "• First-message captcha — for raids and bots.",
            "hint_fallback": "• Check stopword thresholds and links in Protection — filters are already catching the spike.",
        },
        "antinakrutka": {
            "alert": (
                "⚠ <b>Anti-boost</b>\n\n"
                "Mass join detected in <b>{chat_title}</b>.\n"
                "In the last <b>{window_min}</b> min, <b>{joins}</b> members joined (threshold {threshold})."
            ),
        },
        "member_welcome_simple": (
            "{name}, welcome to «{chat_title}»! Before posting, check the group description or pinned messages (if any)."
        ),
        "log": {
            "header_observe": "👁 <b>Guard — OBSERVED</b>\n<i>(message left in chat)</i>\n",
            "header_combat": "😈 <b>Guard: Enforcement</b>\n",
            "line_chat": "🏷 <b>Chat:</b> {title}",
            "line_who": "👤 <b>Offender:</b> {who} (<code>{user_id}</code>)",
            "line_reason": "🧠 <b>Trigger:</b> {reason}",
            "line_detail": "🔎 <b>Detail:</b> <code>{details}</code>",
            "line_action": "⚔️ <b>Action:</b> {action}",
            "extra_line": "\n<i>{extra}</i>\n",
            "text_block": "\n💬 <b>Text:</b>\n<code>{src}</code>\n",
            "extra_delete_failed": "⚠️ couldn’t delete (missing Delete messages right)",
            "extra_punish_failed": "⚠️ couldn’t restrict (missing Ban/Restrict or Telegram limit)",
            "extra_observe_note": "message was not removed — observe mode",
            "btn_unban": "✅ Unban",
            "btn_unmute": "🔊 Unmute",
            "action_observe": "👁 Observed (no deletion)",
            "action_delete": "🧹 Delete",
            "action_mute_day": "🔇 Mute 1 day",
            "action_mute_min": "🔇 Mute {mm} min",
            "action_kick": "👢 Kicked (can rejoin)",
            "action_ban": "⛔ Ban",
            "action_unknown": "⚠️ Unknown action",
            "reason": {
                "stopword": "🧨 stop word",
                "stopword_newbie": "🧨 stop word (newbie)",
                "profanity": "🚫 profanity",
                "profanity_newbie": "🚫 profanity (newbie)",
                "jobs": "🕵️ sketchy job ads",
                "jobs_newbie": "🕵️ sketchy job ads (newbie)",
                "casino": "🎰 casino/betting",
                "casino_newbie": "🎰 casino/betting (newbie)",
                "ads": "📢 ads",
                "ads_newbie": "📢 ads (newbie)",
                "insult": "👎 insults",
                "insult_newbie": "👎 insults (newbie)",
                "racism": "🚫 racism",
                "racism_newbie": "🚫 racism (newbie)",
                "nazi": "⛔ nazism/fascism",
                "nazi_newbie": "⛔ nazism/fascism (newbie)",
                "vulgar": "🔞 lewd content",
                "vulgar_newbie": "🔞 lewd content (newbie)",
                "link": "🔗 link",
                "link_newbie": "🔗 link (newbie)",
                "link_blacklist": "🔗 link (blacklist)",
                "link_blacklist_newbie": "🔗 link (blacklist, newbie)",
                "global_bad_url": "🌐 bad URL (global list)",
                "global_bad_url_newbie": "🌐 bad URL (global list, newbie)",
                "mention": "🏷 mention",
                "mention_newbie": "🏷 mention (newbie)",
                "media": "🖼 media/sticker",
                "media_newbie": "🖼 media/sticker (newbie)",
                "buttons": "🔘 message with buttons",
                "buttons_newbie": "🔘 message with buttons (newbie)",
                "channel_post_actor": "📣 channel/chat post",
                "silence": "🔇 join silence",
                "edited_clean": "✏️ edited (clean)",
            },
        },
        "join_captcha": {
            "member": "Member",
            "ok_passed": "✅ Verified. Welcome!",
            "btn_bot": "I'm a bot 🤖",
            "btn_human": "I'm human ✅",
            "button_intro": (
                "😈 <b>{name}</b> — quick check that you're not a bot.\n"
                "Pick an option honestly. Time: <b>{ttl}</b> min.\n\n"
                "<i>Others can't tap for you — I verify the Telegram ID of whoever presses.</i>"
            ),
            "math": (
                "😈 <b>{name}</b>, what is <b>{a} + {b}</b>?\n"
                "Time: <b>{ttl}</b> min.\n\n"
                "<i>Someone else's tap won't count.</i>"
            ),
            "emoji": (
                "😈 <b>{name}</b>, tap the same emoji I picked:\n<b>{target}</b>\n"
                "Time: <b>{ttl}</b> min.\n\n"
                "<i>Everyone can see group text — only you should press (ID check).</i>"
            ),
            "word_emoji": (
                "😈 <b>{name}</b>, the word on screen is <b>{word}</b>.\n"
                "Tap the emoji that matches it. Time: <b>{ttl}</b> min.\n\n"
                "<i>As always: wrong person, wrong tap — no credit.</i>"
            ),
            "digits": (
                "😈 <b>{name}</b>, send the <b>digits from the image</b> as one <b>text</b> message to this chat.\n"
                "Time: <b>{ttl}</b> min. Digits only — no spaces or letters.\n"
                "<i>Until you pass, only this text reply is allowed in the group; no photos, stickers or files.</i>\n\n"
                "<i>Everyone sees answers in the group; \"typing for you\" is usually moderators.</i>"
            ),
            "word_send": (
                "😈 <b>{name}</b>, send this word in one <b>text</b> message:\n<b>{word}</b>\n"
                "Time: <b>{ttl}</b> min. Case doesn't matter.\n"
                "<i>Until you pass, only a text reply in the group; no photos, stickers or links.</i>\n\n"
                "<i>Only messages from your account count.</i>"
            ),
            "word_guess": (
                "😈 <b>{name}</b>, guess the word and send the <b>full</b> word in one <b>text</b> message.\n"
                "Hint: <b>{hint}</b> (stars hide letters).\n"
                "Time: <b>{ttl}</b> min.\n"
                "<i>Until you pass, only a text reply in the group; no photos, stickers or files.</i>\n\n"
                "<i>It must be the whole dictionary word.</i>"
            ),
            "digits_plain_fallback": (
                "😈 <b>{name}</b>, couldn't send the image — here are the digits as text.\n"
                "Send them <b>in a row with no spaces</b>: <code>{digits}</code>\n"
                "Time: <b>{ttl}</b> min."
            ),
            "cb_stale": "This check is no longer valid.",
            "cb_timeout": "Time is up. Join the chat again.",
            "cb_wrong_user": "Not your captcha — only the new member who just joined can answer.",
            "cb_wrong_answer": "Not quite. Try again.",
            "cb_ok": "✅ All set — you can chat now.",
        },
    },
    "reminders": {
        "expired_warning": (
            "Hey 🥹\n\n"
            "🔔 Hello!\n"
            "Your Guard subscription has expired.\n\n"
            "To get full access to all protection tools again,\n"
            "please renew in the app using the button below 😇"
        ),
        "expired_warning_named": (
            "Hey 🥹\n\n"
            "🔔 Hello, {name}!\n"
            "Your Guard subscription has expired.\n\n"
            "To get full access to all protection tools again,\n"
            "please renew in the app using the button below 😇"
        ),
        "trial_preview_guard": (
            "⚠ *Guard: subscription ended*{name_block}\n\n"
            "Guard can stay in the chat, but without an active subscription it can't stay in full automatic mode.\n"
            "Some risky content may need manual cleanup.\n\n"
            "Without full protection, feeds often see more\n"
            "⛔ casino, scams and crypto pitches\n"
            "❌ banned-substance chatter\n"
            "👎 links to illegal content\n\n"
            "*Legally:* admins may be liable if they knew about such posts and didn't act (check your local laws).\n\n"
            "Renew and bring Guard back to full strength."
        ),
        "guard_payment_sub_expired": (
            "🛡 *Guard: paid Premium period ended*{name_block}\n\n"
            "The bot *stays* in your chats, but without an active subscription Guard only runs in *basic* mode: limits and some rules won't match full Premium.\n\n"
            "YooKassa card auto-renew only runs if you saved a payment method and charging is enabled on the provider side. "
            "If the period simply ended, it isn't necessarily a \"bank error\": usually you just *renew manually* in the mini app.\n\n"
            "Without full protection you'll see more\n"
            "⛔ casinos and scammers\n"
            "❌ forbidden topics\n"
            "👎 sketchy links\n\n"
            "*Legally:* risky content shouldn't sit without a response — check your local regulations.\n\n"
            "Restore Premium in one tap — button below."
        ),
        "trial_name_block": "\n\nHello, {name}.",
        "payment_name_block": "\n\nHello, {name}.",
        "guard_25_days": (
            "🛡 *Guard has been with you for 25 days* — here's what we did together:\n\n"
            "• Stopped & removed: *{moderation_count}*\n"
            "• Chats under protection now: *{chats_count}*\n"
            "• Members who joined your chats: *{joins_count}*\n\n"
            "If this were done by hand,\n"
            "it would take about *{hours_saved} h* and cost roughly *{human_cost_rub} ₽*.\n\n"
            "Thanks for trusting Guard with your communities 💚"
        ),
        "sub_end_5d": (
            "Hi 👋\n\n"
            "*Guard Premium* ends in *5 days*.\n\n"
            "If a YooKassa card is linked, we *try to charge in rotation* during the "
            "*last {charge_window_hours} h* before the end (the server walks subscribers on a schedule — not only in the final hour).\n\n"
            "Make sure the card has funds.\n\n"
            "💡 Renewing for *12 months* saves about *{discount_percent}%*.\n\n"
            "All settings are under Billing & plan."
        ),
        "sub_end_1h_autorenew": (
            "Gentle reminder 💛\n\n"
            "*Guard Premium* ends in *less than an hour*.\n\n"
            "If a card is linked, the service will *try to charge renewal soon* "
            "— same mechanics as background YooKassa tries (the up-to-*{charge_window_hours} h* window may have started earlier).\n\n"
            "Check your card balance. Turn off auto-charge in Billing & plan.\n\n"
            "Thanks for using Guard 🛡"
        ),
        "sub_end_1h_manual": (
            "Gentle reminder 💛\n\n"
            "*Guard Premium* ends in *less than an hour*.\n\n"
            "Card auto-charge isn't available now (no saved payment method) — "
            "renew manually under Billing & plan so protection doesn't pause.\n\n"
            "Thanks for using Guard 🛡"
        ),
        "promo_ended": (
            "Your promo *Guard Premium* period is over.\n\n"
            "If you have a new promo code — redeem it under Account → Promo code.\n"
            "Or enable Premium under Billing & plan to get back:\n"
            "• broadcasts\n"
            "• AI features\n"
            "• flexible admin controls\n"
            "• inviting admins to manage groups via their bot."
        ),
        "autopay_fail": (
            "The Guard renewal charge via YooKassa *didn't go through* (bank or YooKassa response).\n\n"
            "We added *1 more day* of access and can retry later (at most about once per day per provider rules).\n\n"
            "If the retry also fails, Premium features will turn off — you can still renew manually."
        ),
        "autopay_retry_fail": (
            "Unfortunately the second Guard auto-charge attempt failed too 💛\n\n"
            "To keep Premium protection,\n"
            "renew manually — button below."
        ),
        "no_group_12h": (
            "😈 AntiSpam Guard here.\n\n"
            "You started the bot but haven't connected a group yet.\n\n"
            "I can protect chats from:\n"
            "• spam\n"
            "• link clutter\n"
            "• raids\n"
            "• bots\n\n"
            "🎁 Gift: 7 days of Premium free — turn it on in the app "
            "(no card, no payment), then connect a group.\n\n"
            "Connecting takes about 10 seconds."
        ),
        "no_group_24h": (
            "😈 Still waiting.\n\n"
            "Until I'm added, spammers relax a bit more.\n"
            "Connect a group and I'll get to work."
        ),
        "no_group_3d": (
            "😈 Last reminder.\n\n"
            "I can protect your chats automatically.\n"
            "Add me as admin and I'll start."
        ),
        "reports_reminder": (
            "😈 *AntiSpam Guard*\n\n"
            "Connect a reports chat so you don't miss:\n"
            "• 🧹 message deletions\n"
            "• 🔇 mutes\n"
            "• ⛔ bans\n"
            "• ✅ unmute buttons\n\n"
            "You'll see in one place who Guard stopped and why."
        ),
        "auto_report": (
            "📊 *Guard auto-report*\n\n"
            "Chat: *{title}*\n"
            "Last 24 h: actions logged — *{total}*\n\n"
            "_Detailed logs are sent here on each delete/mute/ban._"
        ),
        "owner_daily_head": "📊 Guard daily summary",
        "owner_daily_block": (
            "{head}\n\n"
            "Last {window_h} h:\n"
            "• Group joins: {joins}\n"
            "• /start taps: {starts}\n"
            "• Payments: {pay_count} for {pay_sum:.2f} ₽\n"
            "• Referral shares: {shares}\n\n"
            "Referral levels ({window_h}h):\n{lvl_block}"
        ),
        "owner_daily_lvl_line": "• L{level}: payments {payments_count} / sales {sales_sum:.2f} ₽",
        "owner_daily_no_lvl": "• No referral-level payments",
        "owner_join_title": "📈 Guard quick report\n\n",
        "owner_join_body": (
            "Over the {period}, *{joins}* people joined your groups.\n"
            "Your active groups: *{groups}*"
        ),
        "owner_join_period_day": "day",
        "owner_join_period_3d": "3 days",
        "owner_join_period_week": "week",
        "owner_join_period_month": "month",
        "flex_event": {
            "window_group_joins": "Group joins",
            "window_starts": "/start taps",
            "window_payments": "Payments",
            "window_referral_shares": "Referral shares",
        },
        "flex_default_window_joins": "🔔 {event_label}\n\nLast {hours} h: {count}\nDate: {date}",
        "flex_default_window_starts": "🔔 {event_label}\n\nLast {hours} h: {count}\nDate: {date}",
        "flex_default_window_payments": "🔔 {event_label}\n\nLast {hours} h: {count}\nPayments sum: {payments_sum} ₽\nDate: {date}",
        "flex_default_window_referral": "🔔 {event_label}\n\nLast {hours} h: {count}\nDate: {date}",
        "btn_extend_premium": "✅ Renew Premium",
        "btn_extend_protection": "✅ Renew protection",
        "btn_extend_sub": "✅ Renew subscription",
        "btn_billing": "💳 Billing & plan",
        "btn_go_tariffs": "💳 Open plans",
        "btn_connect_group": "➕ Connect group",
        "btn_connect_group_shield": "🛡 Connect group",
        "btn_reports_connect": "📊 Connect reports chat",
        "btn_open_guard_premium": "🛡 Open Guard Premium",
        "btn_trial_activate": "🚀 Try 7 days free",
        "btn_trial_billing": "👑 Get Premium",
        "trial_window_left": {
            "generic": (
                "😈 AntiSpam Guard here.\n\n"
                "You have {n} day(s) left to try Premium protection for free. "
                "One-click activation, no card required."
            ),
            "9": (
                "😈 AntiSpam Guard here.\n\n"
                "You have 9 days to try Premium protection for free.\n\n"
                "What Premium gives you:\n"
                "• up to 20 groups and channels\n"
                "• advanced filters (media, mentions, buttons)\n"
                "• delegates with granular permissions\n"
                "• dedicated reports chat\n\n"
                "One-click activation, no card required."
            ),
            "8": (
                "🛡 2 days have passed — but protection is still off.\n\n"
                "8 days left to try Premium for free. A large antispam DB and "
                "precise filters can be enabled in one tap."
            ),
            "7": (
                "📅 7 days of trial Premium left.\n\n"
                "Every unguarded day means missed spam, DM ads to your members, "
                "and bot raids. Activate now — it's free."
            ),
            "6": (
                "⚡ 6 days left to claim the free gift.\n\n"
                "If you haven't tried Premium yet — now is the time. No payment: "
                "activate the gift and get Premium for 7 days."
            ),
            "5": (
                "⏳ 5 days already gone.\n\n"
                "5 days left to try Premium for free. After that, the activation "
                "window closes — you'll only be able to subscribe."
            ),
            "4": (
                "🛎 4 days until the trial window closes.\n\n"
                "Activate Premium now — it's free. Protection will turn on "
                "instantly across all your chats."
            ),
            "3": (
                "⚠️ 3 days of free Premium left.\n\n"
                "After that, advanced protection is subscription-only. "
                "Don't miss out — try it now."
            ),
            "2": (
                "⏰ 2 days until the trial window closes.\n\n"
                "If you haven't tried yet — now is the moment. After that, "
                "Premium is paid-only."
            ),
            "1": (
                "🚨 Last day to try Premium for free.\n\n"
                "Tomorrow the window closes. Activate now — it takes 5 seconds."
            ),
        },
        "trial_active_left": {
            "generic": (
                "👑 Premium is active.\n\n"
                "You have {n} day(s) of free Premium left. "
                "Subscribe in advance so you don't lose protection."
            ),
            "9": (
                "👑 Premium trial activated — thank you!\n\n"
                "You have 9 days to set up protection to the max:\n"
                "• tune filters for your chat\n"
                "• connect all your groups\n"
                "• assign delegates with role-based access\n"
                "• enable the reports chat\n\n"
                "By the end of the trial — decide if you want to continue."
            ),
            "8": (
                "🛡 8 days of Premium trial ahead.\n\n"
                "If something is unclear — message support from the Mini App, "
                "we'll help you tune it for your chat."
            ),
            "7": (
                "📈 7 days of Premium still in your pocket.\n\n"
                "Check the reports — see how much spam and how many violations "
                "the protection has caught since activation."
            ),
            "6": (
                "⚡ 6 days of Premium trial left.\n\n"
                "Time to see which filters work best for your chat and "
                "fine-tune them to your needs."
            ),
            "5": (
                "⏳ Half-way mark — 5 days of Premium left.\n\n"
                "If protection fits — subscribe in advance for a seamless transition."
            ),
            "4": (
                "🛎 4 days until the Premium trial ends.\n\n"
                "In 4 days the plan reverts to Free: limits — 3 groups / 1 channel, "
                "advanced filters off. Subscribe to keep your settings."
            ),
            "3": (
                "⚠️ 3 days until the Premium trial ends.\n\n"
                "Don't lose protection — subscribe so your settings stay "
                "and filters keep working."
            ),
            "2": (
                "⏰ 2 days until the Premium trial ends.\n\n"
                "To keep protection on — subscribe. All your filter and delegate "
                "settings will be preserved."
            ),
            "1": (
                "🚨 Last day of your Premium trial.\n\n"
                "Tomorrow the plan reverts to Free and some filters turn off. "
                "Subscribe now — your settings will be preserved."
            ),
        },
    },
    "captcha": {
        "title": "Confirm you are a human",
        "prompt": "Pick the correct answer:",
        "ok": "All set, welcome!",
        "failed": "Wrong answer. Try again.",
        "kicked": "User failed the captcha.",
    },
    "errors": {
        "generic": "Something went wrong. Try again later.",
        "not_admin": "Admin rights are required in this chat.",
        "rate_limit": "Too many requests. Slow down a bit.",
        "session_invalid": "Session ended. Open the app again.",
    },
    "stats": {
        "deleted_today": "Removed today: {count}",
        "protected_today": "Protected: {count} groups",
        "active": "Active",
        "inactive": "Inactive",
    },
    "punishments": {
        "delete": "Delete",
        "mute": "Mute",
        "kick": "Kick",
        "ban": "Ban",
        "observe": "Observe",
    },
    "panel": {
        "main": {
            "body": (
                "Hi 👋\n\n"
                "😈 I am [AntiSpam Guard](https://t.me/GuardAntiSpam_Bot)\n\n"
                "*My job* — keep moderation of comments and groups under control.\n"
                "*Advanced features* unlock with a subscription ⚡\n\n"
                "I instantly remove *spam* and shady links\n"
                "Block users with *spammy nicknames*\n"
                "Stop *flood and boost* before they ruin the chat — and more.\n\n"
                "Plan: *{tariff_label}*\n"
                "Groups in protection: *{groups_count} / {groups_limit}*\n"
                "Channels in protection: *{channels_count} / {channels_limit}*\n"
                "Subscription until: *{sub_until}*\n"
                "AURUM ✨ *{aurum}*\n"
                "Partner tokens *{bonus}* ⚡\n\n"
                "Everything is easy to set up in the app via the buttons below 👇🏻"
            ),
            "trial_gift_hint": (
                "🎁 *Gift:* 7 days of Premium free — turn it on in the app, "
                "no card, no payment."
            ),
        },
        "kb": {
            "chats": "📂 Connected chats",
            "plan": "💳 Plan & billing",
            "ref": "🎁 Referral program",
            "connect_group": "➕ Connect group",
            "connect_chat": "➕ Connect chat",
            "back": "⬅️ Back",
            "open_protection": "🛡 Open protection",
            "connect_reports": "📊 Connect reports chat",
            "open_panel": "⚙ Open panel",
            "protection_selected": "🛡 Protection for selected group",
            "change_chat": "🔄 Switch chat",
            "cancel": "✖️ Cancel",
        },
        "reply_kb": {
            "pick_group": "📋 Choose a group",
            "pick_reports_chat": "📋 Choose reports chat",
            "quick_open_menu": "⚙️ Main menu",
            "quick_change_lang": "🌍 Language",
            "quick_support_tip": "🤝 Support the bot",
            "footer": "⬇️ Quick actions — below the input bar",
        },
        "cmd": {
            "private_only": "This command only works in a private chat with the bot.",
            "panel_dm_only": "😈 Panel only in DMs. Send */panel*.",
            "group_pick": "😈 *Manage one group*\n\nPick a group:",
            "groups_all_body": (
                "🌐 *Manage all groups*\n\n"
                "Selected actions will be applied to every connected chat."
            ),
            "groups_btn_protection": "🛡 Protection for all",
            "groups_btn_reports": "🧾 Reports for all",
            "groups_btn_back": "⬅️ Back",
        },
        "error": {
            "open_panel": (
                "❌ Could not open the panel.{hint}\n\nError: {error}\n\nTry /panel again."
            ),
            "db_migration_hint": (
                "\n\n_Hint: if the database is old, run migration: migrations/001_add_user_and_is_log_chat.sql_"
            ),
        },
        "chat_manage": {
            "title": "🛡 *Connected chats*",
            "settings_for": "Settings for",
            "protection": "Protection",
            "mode": "Mode",
            "silence": "Silence",
            "silence_off": "off",
            "footer": "_Open protection for this chat:_",
        },
        "master_on": "ON",
        "master_off": "OFF",
        "pick_chat": {"connect": "➕ Connect chat"},
        "alert_pick_chat_first": "Pick a chat first 😈",
        "action": {
            "ban": "🚫 Kick out",
            "kick": "👢 Kick",
            "mute": "🔇 Mute",
            "observe": "👁 Watch",
            "delete": "🧹 Sweep",
        },
        "mute": {"one_day": "1 day", "minutes": "{m} min", "btn_1d": "1d", "btn_min": "{m}m"},
        "filter_policy": {
            "forbid": "FORBIDDEN",
            "captcha": "CAPTCHA CHECK",
            "allow": "ALLOWED",
        },
        "filter_links": {
            "allow": "ALLOWED",
            "captcha": "CAPTCHA CHECK",
            "forbid": "EXCEPT TRUSTED",
            "delete_all": "BLOCK ALL LINKS",
            "telegram_only": "TELEGRAM ONLY",
            "smart": "SMART MODE",
            "open_blacklist": "EXCEPT BLACKLIST",
            "allow_except_global": "EXCEPT GLOBAL URL",
        },
        "plan": {"months_short": "{months} months"},
        "connect": {
            "limit": "❌ Chat limit: {current} of {limit}. Upgrade your plan: 💳 Plan & billing.",
            "owner_conflict": (
                "ℹ️ This group is already linked to another Telegram account in Guard, not yours.\n\n"
                "If you are the group creator — connect from the panel or tap /start here: the cabinet is tied to the *creator* of the group, not whoever sent the command.\n"
                "Otherwise the owner can grant access in «Admins & access»."
            ),
            "welcome_group": (
                "😈 AntiSpam Guard is here.\n\n"
                "The group *«{title}»* is now protected.\n\n"
                "I keep things tidy:\n• cutting spam\n• blocking suspicious links\n"
                "• stopping junk, raids and noise\n\n"
                "_Keep in mind:_\n1. No spam.\n2. No random links.\n"
                "3. Don’t turn the chat into a dump.\n4. No hostility or provocations.\n\n"
                "Regular folks — chat in peace.\nSpammers — it will hurt.\n\n_Admins control protection._"
            ),
            "connected_user_msg": "✅ Group connected to protection. Manage it in the panel.",
            "connected_user_fallback": "✅ Group connected. Open the panel: /panel",
            "db_error_alert": "Database error. Apply migrations (008). See DEPLOY-RAILWAY.md.",
            "db_error_dm": "Database error. An admin should apply migration 008 (see DEPLOY-RAILWAY.md).",
            "owner_bind_alert": (
                "This group is already linked to another Telegram account in Guard. Only the owner can delegate."
            ),
            "owner_dm": (
                "✅ *Group connected*\n\n"
                "🏷 Group: *{title}*\n"
                "🛡 Protection is on and ready.\n\n"
                "Next steps:\n"
                "• open *Protection* and review filters;\n"
                "• connect a reports chat to see removals/mutes/bans."
            ),
            "menu_title": "➕ *Connect a chat*",
            "menu_body": (
                "• Tap *«Choose group from list»* — Telegram opens a picker with groups where the bot is already added.\n"
                "• Or pick a group from the list below (one you already added the bot to)."
            ),
            "btn_pick_modal": "📋 Choose group from Telegram list",
            "pick_modal_prompt": (
                "Tap the button below — you’ll see your groups where the bot is already a member. Pick one to connect."
            ),
            "pick_modal_fallback": (
                "The «Choose group» button might not open in this client. "
                "Add the bot as admin to the right group, then return here and pick the group *from the list under the message above* — chats you added the bot to will show up there."
            ),
            "unnamed_chat": "Chat",
        },
        "addgroup": {
            "body": (
                "➕ *Add the bot to a group*\n\n"
                "Tap the *button below the input field* — you’ll pick a group, then Telegram will prompt you to grant admin rights to the bot."
            ),
            "fallback_btn": "➕ Add bot to group (with admin rights)",
            "fallback_hint": (
                "If the blue button under the input is missing — tap below to open group pick. With this link you’ll grant admin rights manually in the group. The “promote to admin” modal only appears when using the blue button under the input."
            ),
        },
        "referral": {
            "link_fail": "Could not build the link. Try again later.",
            "share_text": "Guard protects chats from spam and schedules broadcasts. Connect and set up in minutes.",
            "access_months": "{months} mo.",
            "access_none": "no active period",
            "access_levels_free": "Level {levels} — direct referrals only",
            "access_levels_full": "Levels {levels} — full network",
            "premium_extra": "├ Premium days left: *{days_left}*\n└ Active until: *{active_until}*\n",
            "premium_extra_promo": "├ Premium via promo *{code}*, *{days_left}* days left\n└ Active until: *{active_until}*\n",
            "premium_extra_forever": "└ Premium with no expiry (promo / forever access)\n",
            "premium_extra_active": "└ Premium active\n",
            "premium_extra_none": "└ Levels 2–3 unlock with Premium\n",
            "body": (
                "🎁 *Guard referral program*\n\n"
                "Partner tiers: {access_line}\n"
                "{premium_extra}\n"
                "Balance:\n"
                "├ AURUM: *{aurum}* ✨\n"
                "└ Partner pool: *{bonus}* ⚡\n\n"
                "{partner_breakdown}\n\n"
                "Your partner link:\n"
                "└ `{ref_link}`\n\n"
                "⬆️ Tap to copy and share with friends! 🎁\n\n"
                "Invited users:\n"
                "└ Total: *{invited}*, Paying: *{paid}*"
            ),
            "partner": {
                "network_head": "👥 *Your network*",
                "net_l1_solo": "└ L1 (direct invites): *{n}*",
                "network_levels_premium_hint": "_Network levels 2–3 and commissions from those tiers unlock with Premium._",
                "net_l1": "├ L1 (direct invites): *{n}*",
                "net_l2": "├ L2 (invites by your referrals): *{n}*",
                "net_l3": "├ L3 (third level): *{n}*",
                "net_total": "└ Network total: *{n}* people",
                "confirmed_head": "💰 *Confirmed rewards*",
                "pending_head": "⏳ *Awaiting confirmation*",
                "avail_head": "💎 *Available to use*",
                "avail_row": "└ *{bonus}* ⚡",
                "comm_row": "├ L{l} · {pct}% · {pay} payments · {rub} → *{tok}* ⚡",
                "confirmed_total": "└ Total: *{tok}* ⚡",
                "pending_total": "└ Pending summary: *{pay}* payments · *{rub}* → *{tok}* ⚡",
            },
            "kb_program": "⚙️ Program details",
            "kb_access_terms": "⚙️ Access terms",
            "kb_bonus_to_aurum": "✨ Partner → AURUM",
            "kb_share": "⭐ Share",
        },
        "minute_abbr": "min",
        "duration": {
            "10": "10 minutes",
            "60": "1 hour",
            "120": "2 hours",
            "180": "3 hours",
            "240": "4 hours",
            "360": "6 hours",
            "480": "8 hours",
            "600": "10 hours",
            "720": "12 hours",
            "1440": "1 day",
        },
        "public_alerts_kb": {
            "enable": "✅ Enable",
            "disable": "❌ Disable",
            "every_5": "🔁 Every 5 deletions",
            "every_10": "🔁 Every 10 deletions",
            "int_2": "⏱ Interval 2 min",
            "int_5": "⏱ Interval 5 min",
            "int_10": "⏱ Interval 10 min",
            "back": "⬅️ Back",
        },
        "chats_ui": {
            "mode_one": "🎯 Manage one group",
            "mode_all": "🌐 Manage all groups",
            "sub_connected": "🛡 Connected chats",
            "sub_change_chat": "🔄 Switch chat",
            "sub_logs": "📍 Log chats",
        },
        "filters_kb": {
            "links": "🔗 Links",
            "media": "🖼 Media / stickers",
            "buttons": "🔘 Messages with buttons",
            "join": "👥 “Joined group” messages",
            "left": "🚪 “Left group” messages",
            "silence": "🔇 Silence mode",
            "spam": "🛡 Anti-spam shield",
            "allow": "✅ Allow",
            "forbid": "🚫 Block",
            "disable": "❌ Disable",
            "delete": "🗑 Delete",
            "keep": "📌 Keep",
            "enable": "✅ Enable",
            "row_links": "🔗 Links: {state}",
            "row_mentions": "🏷 @: {state}",
            "row_antiedit": "✏️ Anti-edit: {state}",
            "cut": "CUT",
            "nocut": "OFF",
        },
        "punish_kb": {"mode": "😈 Mode: {mode}", "mute": "🔇 Mute: {label}"},
        "newbie_kb": {"toggle": "👶 Newbie: {state}", "window": "⏱ Window: {minutes}m"},
        "reports_kb": {
            "connect": "➕ Connect reports chat",
            "toggle": "🧾 Reports: {state}",
            "change_chat": "🔄 Change reports chat",
            "no_reports": "🚫 Don’t send reports",
            "help": "🧾 How it works",
        },
        "antinakrutka_kb": {
            "enable": "✅ Enable",
            "disable": "❌ Disable",
            "threshold": "Threshold {n}",
            "window": "Window {m}m",
            "action_alert": "Alert only",
            "action_restrict": "Alert + mute",
            "mute_min": "Mute {r}m",
        },
        "nav_chats": {
            "one_pick_chat": "😈 *Manage one group*\n\nPick a chat:",
            "all_intro": (
                "🌐 *Manage all groups*\n\n"
                "Pick an action — you’ll get a list of chats to configure."
            ),
            "all_btn_protection": "🛡 Protection for all",
            "all_btn_reports": "🧾 Reports for all",
            "no_chats_protection": (
                "🛡 No connected chats yet. Add the bot to a group and connect it under *Connect group*."
            ),
            "no_chats_reports": (
                "🧾 No connected chats yet. Add the bot to a group and connect it under *Connect group*."
            ),
            "protection_all_pick": "🛡 *Protection for all*\n\nPick a chat to configure protection:",
            "reports_all_pick": "🧾 *Reports for all*\n\nPick a chat to configure reports:",
            "list_empty": "🛡 *Connected chats*\n\nNone yet. Tap *➕ Connect chat* in the main menu.",
            "list_title": "🛡 *Connected chats*",
            "list_more": "…and {n} more",
            "logs_empty": (
                "📍 *Log chats*\n\n"
                "None yet. To add one:\n"
                "1) Create a group for logs\n"
                "2) Add the bot and grant rights\n"
                "3) In that group run: /setlog"
            ),
            "logs_title": "📍 *Log chats*",
            "pick_change": "😈 *Switch chat*\nPick a chat:",
            "pick_default": "😈 *Pick a chat*\nWho are we protecting:",
        },
        "alerts": {
            "bad_payload": "Bad data 😈",
            "not_your_chat": "Not your chat. Hands off 😈",
        },
        "cleanup": {
            "title": "🧹 *Deleted-account cleanup*",
            "chat": "Chat",
            "checked": "Members checked",
            "kicked": "Deleted accounts removed",
            "error": "😈 Cleanup error: {error}",
        },
        "global_antispam": {
            "title": "📋 *Anti-spam database*",
            "body": (
                "Shared user database across all bot groups. When enabled, users are checked on *joining* this chat.\n\n"
                "• Use in this chat: *{on_off}*\n"
                "• Entries in DB: *{count}*\n\n"
                "_How to add without ID:_ in a group, reply to the user’s message and send /addantispam — the bot will add them."
            ),
            "toggle_enable": "✅ Enable in this chat",
            "toggle_disable": "❌ Disable in this chat",
            "add_by_id": "➕ Add by ID",
            "list_line": "  {i}. {label} — {reason}",
            "add_prompt": (
                "📋 Send the user’s *user_id* (number) to add to the anti-spam database.\n"
                "Example: `123456789`\n\n"
                "Or in a group: reply to the user’s message and send /addantispam — the bot will add the replied author.\n"
                "Cancel: /cancel"
            ),
            "premium_required": "Anti-spam database management is Premium-only.",
            "owner_premium_required": "This chat’s owner needs Premium for the anti-spam database.",
        },
        "profanity_dm": {
            "body": (
                "🚫 *Guard: Hard dictionary*\n\n"
                "Cuts roots and obfuscated forms. Punishment comes from *Punishments*.\n\n"
                "• Profanity: *{mat}*\n"
                "• Sketchy ‘side jobs’: *{jobs}*\n"
                "• Casino / betting: *{casino}*"
            ),
            "btn_mat": "🚫 Profanity: {on_off}",
            "btn_jobs": "🕵️ Side jobs: {on_off}",
            "btn_casino": "🎰 Casino/bets: {on_off}",
        },
        "stopwords_stub": (
            "🧠 *Stop words*\n\n"
            "We’ll turn this section on once the stopwords table exists in the DB.\n"
            "The panel is already wired for it.\n\n"
            "😈 Say the word — we’ll hook it up painlessly."
        ),
        "transfer_settings": {
            "done": "📤 *Settings copied*\n\nFrom *{src}* to *{dst}*.",
            "pick_other": "Pick another target chat.",
            "no_access_target": "No access to the target chat.",
        },
        "guard_tip": "🤝 You can support Guard under Plan & billing",
        "ref_access": {
            "body": (
                "⚙️ *Guard access terms*\n\n"
                "Access is extended via YooKassa payments\n"
                "Referral percentages accrue as partner tokens\n"
                "and can be moved to AURUM ✨ with the button in referrals\n\n"
                "To extend, open Plan & billing and complete payment\n\n"
                "If you don’t need auto-renewal, turn it off with the button below"
            ),
            "autorenew_off_btn": "⛔ Disable auto-renewal",
            "bonus_empty": "No partner tokens yet",
            "bonus_moved": "Converted to AURUM: {amount} ✨",
            "done_toast": "Done",
            "autorenew_off_body": (
                "⛔ *Auto-renewal disabled*\n\n"
                "To enable access again open Plan & billing\n"
                "and complete a new Guard payment"
            ),
        },
        "support": {
            "body": (
                "😈 *AntiSpam Guard* is listening.\n\n"
                "Support: @pastukh_viscera\n\n"
                "_Before you write:_\n"
                "• make sure it can’t be fixed from the panel\n"
                "• describe the issue in detail\n"
                "• attach a screenshot if possible\n\n"
                "Messages like “Hi” / “It doesn’t work” are ignored."
            ),
        },
        "guard_help": {
            "body": (
                "📋 Full guide — in the panel (*i* icon in the app).\n\n"
                "Open the panel with the *Menu* button under the input in this chat or the button below."
            ),
            "no_url_hint": "\n\n_(Button unavailable: MINI_APP_URL / WEBAPP_URL is not set on the server.)_",
            "open_panel_btn": "🛡 Open Guard panel",
        },
        "premium_cmd_disabled": {
            "7": (
                "Command disabled. Use a promo code in the panel → Account → Promo.\n"
                "Premium 7-day code: `{code}`"
            ),
            "14": (
                "Command disabled. Use a promo code in the panel → Account → Promo.\n"
                "Premium 14-day code: `{code}`"
            ),
            "aurum": "Command disabled. Use an advanced promo code in the panel → Account → Promo.",
        },
        "screens": {
            "captcha_first": "🧩 *Captcha on first message*\n\nCurrent state: *{on_off}*",
            "raid": "🚨 *Anti-raid*\n\n",
            "antinakrutka": (
                "📈 *Anti-boost*\n\n"
                "Alerts and reaction to mass joins in a group or a channel comments chat.\n\n"
                "State: *{on_off}*\n"
                "Threshold: *{th}* members in *{win}* min\n"
                "Action: *{action}*\n"
                "{mute_line}"
                "_Pick options below._"
            ),
            "antinakrutka_mute_line": "Mute on raid: *{mute}*",
            "antinakrutka_act_alert": "alert only",
            "antinakrutka_act_restrict": "alert + mute",
            "public_alerts": (
                "📢 *Guard messages*\n\n"
                "Now: *{on_off}*\n"
                "After every *{every}* deletions — a short line in the chat.\n"
                "Minimum interval: *{interval_min}* min\n"
                "Every 3 days — a message in the group (if active).\n\n"
                "_On by default. You can turn off._"
            ),
            "public_alerts_on_toast": (
                "📢 Guard messages: *ON*. Every N deletions — a line in chat; every 3 days — a group message."
            ),
            "public_alerts_off_toast": "📢 Guard messages: *OFF*. Group messages and post-deletion lines are disabled.",
            "public_alerts_every": "📢 Frequency: every *{n}* deletions. Guard messages: *{on_off}*.",
            "public_alerts_interval": "📢 Minimum interval between lines: *{min_val}* min.",
        },
        "captcha_first_kb": {"enable": "✅ Enable", "disable": "❌ Disable", "back": "⬅️ Back"},
        "filters_intro": {
            "main": (
                "⚙ *Filters for «{title}»*\n\n"
                "Configure the main limits:\n"
                "• links\n• media\n• buttons\n• captcha for all messages\n"
                "• system join messages\n• silence mode\n• anti-spam shield"
            ),
            "links": (
                "🔗 *Links*\n\nCurrent state: *{state}*\n\n"
                "Advanced modes (smart, Telegram-only, blacklist, etc.) — Mini App → Protection → Links."
            ),
            "media": "🖼 *Media / stickers*\n\nCurrent state: *{state}*",
            "buttons": "🔘 *Messages with buttons*\n\nCurrent state: *{state}*",
            "all_captcha": "🧩 *Captcha check for all messages*\n\nCurrent state: *{state}*",
            "all_captcha_on": "on for {mins} min",
            "join": "👥 *System “joined group” messages*\n\nCurrent state: *{state}*",
            "left": "🚪 *System “left group” messages*\n\nCurrent state: *{state}*",
            "del": "DELETE",
            "keep": "KEEP",
            "silence": (
                "🔇 *Silence mode*\n\n"
                "Current state: *{state}*\n\n"
                "While the window after *joining the chat* is active, any member message may end in a *mute* "
                "for the remaining minutes. Handy to stop spam right after they join."
            ),
            "silence_on": "on for {mins} min",
            "spam": "🛡 *Anti-spam shield*\n\nCurrent state: *{state}*",
        },
        "punish_intro": (
            "⚙️ *Punishments*\n\n"
            "Choose how we *reeducate* spammers:\n"
            "— delete message\n"
            "— mute\n"
            "— kick/ban\n\n"
            "_No tenderness. No swearing either._ 😈"
        ),
        "newbie_intro": (
            "👶 *Newbie mode*\n\n"
            "For the first *N minutes after join* the member is a newbie: same filters apply, "
            "but reports show *(newbie)* — easier to spot risk right after they enter.\n\n"
            "Enable and set the window length with the buttons below."
        ),
        "reports_intro": (
            "🧾 *Reports*\n\n"
            "Group: *{group_title}*\n"
            "Reports chat: *{reports_where}*\n"
            "Now: *{state}*\n\n"
            "_Connect or change the reports chat with the buttons below._"
        ),
        "reports_not_selected": "not set",
        "copy_settings_intro": "📤 *Copy settings*\n\nPick the chat *to copy settings into* from *{title}*:",
        "pending_prompt": {
            "mute": (
                "🔇 *Mute — duration*\n\n"
                "Minutes from *1* to *1440* (max *1 day*).\n"
                "_Example:_ `30` or `1440`\n\n"
                "😈 Just a number. No poetry."
            ),
            "newbie": (
                "👶 *Newbie window*\n\n"
                "Send one message with minutes *1..1440*.\n"
                "_Example:_ `10`"
            ),
        },
        "pending_input": {
            "need_number": "❌ Need a number.\n\n_Example:_ `30`",
            "mute_range": "❌ For mute: *1*…*1440* minutes (max *1 day*).\n\n_Example:_ `30`",
            "newbie_range": "❌ Enter *1..1440*.\n\n_Example:_ `10`",
        },
        "cancel_toast": "Cancelled 😈",
        "promo_input": {"cancelled": "Cancelled."},
        "antispam_private": {
            "user_id_expected": "Send user_id as digits (e.g. 123456789) or /cancel",
            "added": "✅ User `{uid}` added to the anti-spam database.",
            "already": "✅ User `{uid}` was already in the anti-spam database.",
        },
        "addantispam_group": {
            "no_bots": "Bots cannot be added to the anti-spam database.",
            "mem_fail": "Could not verify your rights in the group. Make sure the bot is an administrator.",
            "cmd_error": "Could not run the command: {error}",
            "restrict_required": (
                "Only admins with permission to *restrict members* can add users to the anti-spam database."
            ),
            "admin_only": "Only a group *administrator* can add a user to the anti-spam database.",
            "not_linked": "This group is not linked to your account. Manage the bot in a private chat.",
            "added_notice": (
                "✅ User {user_id} added to the anti-spam database.{extra}\n\n"
                "If the check is enabled, they will be removed when joining your groups.{tail}"
            ),
            "extra_kicked": " Removed from this group.",
            "tail_ban_fail": " Could not remove from chat — give the bot permission to *ban users*.",
            "already_kicked": "User {user_id} was already in the anti-spam database. Removed from this group.",
            "already": "User {user_id} was already in the anti-spam database.",
            "hint_no_reply": (
                "To add someone to the *anti-spam database*, *reply to their message* in the group "
                "and send /addantispam.\n\n"
                "Only a group *administrator* of a Guard-linked group can use this command."
            ),
        },
        "reports_flow": {
            "btn_pick": "📋 Choose reports chat",
            "btn_pick_new": "📋 Choose a new reports chat",
            "connect_hint": (
                "⬅️ *Use Guard via the «Menu» button above.*\n\n"
                "We’ve disabled the button under the input. "
                "Tap below to open picking the reports chat."
            ),
            "change_hint": (
                "⬅️ *Use Guard via the «Menu» button above.*\n\n"
                "We’ve disabled the button under the input. "
                "Tap below to pick a new reports chat."
            ),
            "pick_failed": (
                "Could not show the picker. Make sure the bot is added to the reports group, then try again from *Reports*."
            ),
            "help_body": (
                "🧾 *Reports = moderation log*\n\n"
                "I send there:\n"
                "• who got hit\n"
                "• why\n"
                "• what I did (delete/mute/ban)\n\n"
                "*How to set up:*\n"
                "Tap *➕ Connect reports chat* and pick a group — reports go there.\n\n"
                "😈 I don’t chat. I record actions."
            ),
            "session_expired": (
                "Session expired. Open *Reports* and tap «Connect reports chat» again."
            ),
            "connected_dm": "✅ Reports chat connected.",
            "chat_welcome": (
                "😈 *AntiSpam Guard* — reports chat for group "
                "*«{title}»*.\n\n"
                "Moderation reports (deletions, mutes, bans, etc.) land here. "
                "I don’t touch normal members here."
            ),
            "set_bad_payload": "Bad data 😈",
            "set_pick_from_list": "Pick a reports chat from the list 😈",
        },
        "connect_verify": {
            "bad_data": "Bad data 😈",
            "groups_only": "Groups only 😈",
            "admin_only": "Only a group admin can connect the chat 😈",
            "bot_need_admin": "First make the bot admin with permission to delete messages 😈",
            "bot_need_delete": "Give the bot “Delete messages” permission 😈",
            "verify_fail": "Could not verify the chat 😈",
            "groups_only_dm": "Only groups can be connected 😈",
        },
    },
}

from .http_api_errors import EN as _API_ERRORS_EN
from .http_api_ui import EN as _API_UI_EN

MESSAGES["api"] = {"errors": _API_ERRORS_EN, "ui": _API_UI_EN}
