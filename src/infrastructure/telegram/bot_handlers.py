# src/infrastructure/telegram/bot_handlers.py
import logging
from datetime import datetime, timezone  # Added timezone
from typing import List, Set, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from ...application.services.analytics_service import \
    AnalyticsService  # Should be IAnalyticsService for type hint if following DI
from ...domain.interfaces import IAnalyticsService  # For type hinting
from ...application.use_cases.bot_management import BotManagementUseCase
from ...config import settings  # Import the settings instance
# IUserInteractionRepository is not directly used here anymore if all goes via AnalyticsService
from ...domain.models import UserInteraction  # Not directly created here anymore

logger = logging.getLogger(__name__)


class TelegramBotHandlers:
    """Telegram bot command and callback handlers."""

    def __init__(
            self,
            analytics_service: IAnalyticsService,  # Changed to interface
            bot_management: BotManagementUseCase,
            admin_user_ids: List[int]
            # interaction_repo: IUserInteractionRepository # Removed, using analytics_service now
    ):
        self._analytics_service = analytics_service  # This is now IAnalyticsService
        self._bot_management = bot_management
        self._admin_user_ids: Set[int] = set(admin_user_ids)
        self._self_bot_id: Optional[str] = None

    async def _get_self_bot_id(self) -> Optional[str]:
        """Retrieves and caches this bot's own bot_id from BotConfig table."""
        if self._self_bot_id:
            return self._self_bot_id

        if not settings.ANALYTICS_BOT_TOKEN:  # Access from the imported settings instance
            logger.warning("ANALYTICS_BOT_TOKEN not configured in settings.")
            return None

        try:
            # Use the method added to BotManagementUseCase
            bot_config = await self._bot_management.get_bot_config_by_token(settings.ANALYTICS_BOT_TOKEN)
            if bot_config:
                self._self_bot_id = bot_config.bot_id
                logger.info(f"Identified self (admin bot) with bot_id: {self._self_bot_id}")
                return self._self_bot_id
            else:
                logger.warning(
                    "Admin bot's token not found in bot_configs. "
                    "Ensure it's added via /add_bot for self-tracking to work."
                )
        except Exception as e:
            logger.error(f"Error getting self bot_id: {e}", exc_info=True)
        return None

    async def _record_admin_interaction(self, update: Update, interaction_type_suffix: str):
        """Records an interaction performed by an admin on this bot via AnalyticsService."""
        self_bot_id = await self._get_self_bot_id()
        if not self_bot_id:
            logger.debug("Cannot record admin interaction: self_bot_id not identified.")
            return

        user = update.effective_user
        if not user:
            logger.debug("Cannot record admin interaction: no effective_user.")
            return

        message_text: Optional[str] = None
        interaction_main_type: str = "unknown"

        if update.message:
            message_text = update.message.text
            interaction_main_type = "command" if message_text and message_text.startswith('/') else "message"
        elif update.callback_query:
            message_text = update.callback_query.data
            interaction_main_type = "callback_query"

        full_interaction_type = f"{interaction_main_type}_{interaction_type_suffix}"

        try:
            await self._analytics_service.track_interaction(
                bot_id_or_token=self_bot_id,
                user_id=user.id,
                interaction_type=full_interaction_type,
                timestamp=datetime.now(timezone.utc),  # Use UTC for consistency
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                language_code=user.language_code,
                message_text=message_text,
                is_token=False  # self_bot_id is an ID
            )
            logger.debug(
                f"Admin interaction sent to service: {full_interaction_type} by user {user.id} for self_bot_id {self_bot_id}")
        except Exception as e:
            logger.error(f"Failed to send admin interaction to service: {e}", exc_info=True)

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin."""
        return user_id in self._admin_user_ids

    async def start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # Defensive check for update.effective_user
        if not update.effective_user or not self._is_admin(update.effective_user.id):
            if update.message: await update.message.reply_text("❌ Access denied. Admin only bot.")
            return
        await self._record_admin_interaction(update, "start")

        keyboard = [
            [InlineKeyboardButton("📊 Global Stats", callback_data="global_stats")],
            [InlineKeyboardButton("🤖 List Bots", callback_data="list_bots")],
            [InlineKeyboardButton("➕ Add Bot", callback_data="add_bot_help")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🔍 **Analytics Monitor Bot**\n\nWelcome to your multi-bot analytics dashboard!\n\n"
            "**Available Commands:**\n"
            "• `/add_bot <name> <token> [description]` - Add a bot to monitor\n"
            "• `/list_bots` - Show all monitored bots\n"
            "• `/stats <bot_id>` - Get specific bot statistics\n"
            "• `/global_stats` - Get global statistics\n"
            "• `/remove_bot <bot_id>` - Remove a bot from monitoring\n\n"
            "Choose an option below:",
            parse_mode='Markdown', reply_markup=reply_markup
        )

    async def add_bot_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not self._is_admin(update.effective_user.id):
            if update.message: await update.message.reply_text("❌ Access denied.")
            return

        # Record before argument parsing in case of error
        await self._record_admin_interaction(update, "add_bot_command_attempt")

        args = context.args
        if not args or len(args) < 2:  # Check if args exist before trying to access
            if update.message:
                await update.message.reply_text(
                    "❌ **Usage:** `/add_bot <name> <token> [description]`\n\n"
                    "**Example:**\n"
                    "`/add_bot \"My Taxi Bot\" 123456:ABC-DEF... \"Taxi booking bot\"`",
                    parse_mode='Markdown'
                )
            return

        name = args[0]
        token = args[1]
        description = " ".join(args[2:]) if len(args) > 2 else None

        try:
            bot_config = await self._analytics_service.add_bot(name, token, description)
            if token == settings.ANALYTICS_BOT_TOKEN:
                self._self_bot_id = bot_config.bot_id
                logger.info(f"Admin bot successfully added itself. Self_bot_id is now {self._self_bot_id}")

            # Record success after the operation
            # await self._record_admin_interaction(update, f"add_bot_success_{bot_config.bot_id}") # Already recorded attempt

            if update.message:
                await update.message.reply_text(
                    f"✅ **Bot added successfully!**\n\n"
                    f"**Bot ID:** `{bot_config.bot_id}`\n"
                    f"**Name:** {bot_config.name}\n"
                    f"**Description:** {bot_config.description or 'None'}\n"
                    f"**Added:** {bot_config.created_at.strftime('%Y-%m-%d %H:%M') if bot_config.created_at else 'N/A'}",
                    parse_mode='Markdown'
                )
        except ValueError as ve:
            # await self._record_admin_interaction(update, "add_bot_value_error") # Already recorded attempt
            if update.message: await update.message.reply_text(f"❌ **Error adding bot:** {str(ve)}",
                                                               parse_mode='Markdown')
        except Exception as e:
            # await self._record_admin_interaction(update, "add_bot_exception") # Already recorded attempt
            logger.error(f"Error adding bot in handler: {e}", exc_info=True)
            if update.message: await update.message.reply_text("❌ **Unexpected error adding bot:** Please check logs.",
                                                               parse_mode='Markdown')

    async def list_bots_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not self._is_admin(update.effective_user.id):
            if update.message: await update.message.reply_text("❌ Access denied.")
            return
        await self._record_admin_interaction(update, "list_bots_command")

        bots = await self._bot_management.get_all_monitored_bots()
        if not bots:
            if update.message: await update.message.reply_text("📋 No bots are currently being monitored.")
            return

        message = "🤖 **Monitored Bots:**\n\n"
        for bot_item in bots:
            status = "🟢 Active" if bot_item.is_active else "🔴 Inactive"
            message += (
                f"**{bot_item.name}**\n"
                f"ID: `{bot_item.bot_id}`\n"
                f"Status: {status}\n"
                f"Added: {bot_item.created_at.strftime('%Y-%m-%d') if bot_item.created_at else 'N/A'}\n\n"
            )
        keyboard = []
        for bot_button_item in bots[:5]:
            keyboard.append([
                InlineKeyboardButton(f"📊 {bot_button_item.name} Stats", callback_data=f"stats_{bot_button_item.bot_id}")
            ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.message: await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def stats_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not self._is_admin(update.effective_user.id):
            if update.message: await update.message.reply_text("❌ Access denied.")
            return

        bot_id_arg = "self"  # Default or placeholder
        if not context.args:
            await self._record_admin_interaction(update, "stats_command_no_arg")
            if update.message:
                await update.message.reply_text(
                    "❌ **Usage:** `/stats <bot_id>`\n\n"
                    "Use `/list_bots` to see available bot IDs.",
                    parse_mode='Markdown'
                )
            return

        bot_id_arg = context.args[0]
        await self._record_admin_interaction(update, f"stats_command_for_{bot_id_arg}")

        try:
            stats_data = await self._analytics_service.get_bot_statistics(bot_id_arg)
            last_interaction_str = "Never"
            if stats_data.last_interaction:
                # Ensure last_interaction is timezone-aware if stored as UTC, or convert for display
                # For now, assuming it's compatible with strftime directly
                last_interaction_str = stats_data.last_interaction.strftime('%Y-%m-%d %H:%M')

            message = (
                f"📊 **Statistics for {stats_data.bot_name}**\n\n"
                f"👥 **Total Users:** {stats_data.total_users:,}\n"
                f"🟢 **Daily Active:** {stats_data.daily_active_users:,}\n"
                f"📅 **Weekly Active:** {stats_data.weekly_active_users:,}\n"
                f"📆 **Monthly Active:** {stats_data.monthly_active_users:,}\n"
                f"🆕 **New Users Today:** {stats_data.new_users_today:,}\n"
                f"💬 **Total Interactions:** {stats_data.total_interactions:,}\n"
                f"🕐 **Last Interaction:** {last_interaction_str}\n\n"
                f"**Bot ID:** `{stats_data.bot_id}`"
            )
            keyboard = [
                [InlineKeyboardButton("📈 Weekly Timeline", callback_data=f"timeline_{bot_id_arg}")],
                [InlineKeyboardButton("🔄 Refresh", callback_data=f"stats_{bot_id_arg}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            if update.message: await update.message.reply_text(message, parse_mode='Markdown',
                                                               reply_markup=reply_markup)
        except ValueError as ve:
            if update.message: await update.message.reply_text(f"❌ **Error fetching stats:** {str(ve)}",
                                                               parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error fetching stats in handler for bot_id {bot_id_arg}: {e}", exc_info=True)
            if update.message: await update.message.reply_text(
                "❌ **Unexpected error fetching stats:** Please check logs.",
                parse_mode='Markdown')

    async def global_stats_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not self._is_admin(update.effective_user.id):
            if update.message: await update.message.reply_text("❌ Access denied.")
            return
        await self._record_admin_interaction(update, "global_stats_command")

        try:
            global_stats_data = await self._analytics_service.get_global_statistics()
            message = (
                f"🌍 **Global Analytics Dashboard**\n\n"
                f"🤖 **Total Bots:** {global_stats_data.total_bots}\n"
                f"🟢 **Active Today:** {global_stats_data.active_bots}\n"
                f"👥 **Total Users:** {global_stats_data.total_users_across_bots:,}\n"
                f"💬 **Interactions Today:** {global_stats_data.total_interactions_today:,}\n\n"
            )
            if global_stats_data.most_active_bot:
                bot_conf = await self._bot_management.get_monitored_bot_details(global_stats_data.most_active_bot)
                if bot_conf:
                    message += f"🏆 **Most Active Bot:** {bot_conf.name} (`{global_stats_data.most_active_bot}`)\n"
                else:
                    message += f"🏆 **Most Active Bot:** ID `{global_stats_data.most_active_bot}` (Details not found)\n"
            if global_stats_data.least_active_bot:
                bot_conf = await self._bot_management.get_monitored_bot_details(global_stats_data.least_active_bot)
                if bot_conf:
                    message += f"😴 **Least Active Bot:** {bot_conf.name} (`{global_stats_data.least_active_bot}`)\n"
                else:
                    message += f"😴 **Least Active Bot:** ID `{global_stats_data.least_active_bot}` (Details not found)\n"

            keyboard = [
                [InlineKeyboardButton("🤖 List All Bots", callback_data="list_bots")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="global_stats")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            if update.message: await update.message.reply_text(message, parse_mode='Markdown',
                                                               reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error fetching global stats in handler: {e}", exc_info=True)
            if update.message: await update.message.reply_text(f"❌ **Error fetching global stats:** {str(e)}",
                                                               parse_mode='Markdown')

    async def remove_bot_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not self._is_admin(update.effective_user.id):
            if update.message: await update.message.reply_text("❌ Access denied.")
            return

        bot_id_arg = "none"  # Default if no args
        if context.args:
            bot_id_arg = context.args[0]

        await self._record_admin_interaction(update, f"remove_bot_command_for_{bot_id_arg}")

        if not context.args:
            if update.message:
                await update.message.reply_text(
                    "❌ **Usage:** `/remove_bot <bot_id>`\n\n"
                    "Use `/list_bots` to see available bot IDs.",
                    parse_mode='Markdown'
                )
            return

        # bot_id_arg is already set from context.args[0]

        try:
            bot_config_obj = await self._bot_management.get_monitored_bot_details(bot_id_arg)  # Renamed
            if not bot_config_obj:
                if update.message: await update.message.reply_text(f"❌ Bot with ID `{bot_id_arg}` not found.",
                                                                   parse_mode='Markdown')
                return

            keyboard = [
                [InlineKeyboardButton("✅ Yes, Remove", callback_data=f"confirm_remove_{bot_id_arg}")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_remove")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            if update.message:
                await update.message.reply_text(
                    f"⚠️ **Confirm Bot Removal**\n\n"
                    f"Are you sure you want to remove:\n"
                    f"**Name:** {bot_config_obj.name}\n"
                    f"**ID:** `{bot_id_arg}`\n\n"
                    f"⚠️ **Warning:** This will delete this bot's configuration and ALL its analytics data!",
                    parse_mode='Markdown', reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Error in remove_bot_handler for bot_id {bot_id_arg}: {e}", exc_info=True)
            if update.message: await update.message.reply_text(f"❌ **Error preparing bot removal:** {str(e)}",
                                                               parse_mode='Markdown')

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.from_user or not self._is_admin(query.from_user.id):  # Defensive checks
            if query: await query.answer("❌ Access denied.", show_alert=True)
            return

        await self._record_admin_interaction(update, query.data)

        data = query.data
        message_edited_flag = False

        try:
            if data == "global_stats":
                await self._handle_global_stats_callback(query)
                message_edited_flag = True
            elif data == "list_bots":
                await self._handle_list_bots_callback(query)
                message_edited_flag = True
            elif data == "add_bot_help":
                await self._handle_add_bot_help_callback(query)
                message_edited_flag = True
            elif data.startswith("stats_"):
                bot_id = data.replace("stats_", "")
                await self._handle_bot_stats_callback(query, bot_id)
                message_edited_flag = True
            elif data.startswith("timeline_"):
                bot_id = data.replace("timeline_", "")
                await self._handle_timeline_callback(query, bot_id)
                message_edited_flag = True
            elif data.startswith("confirm_remove_"):
                bot_id = data.replace("confirm_remove_", "")
                await self._handle_confirm_remove_callback(query, bot_id)
                message_edited_flag = True
            elif data == "cancel_remove":
                await query.edit_message_text("❌ Bot removal cancelled.")
                message_edited_flag = True
            else:
                logger.warning(f"Unhandled callback data structure: {data}")
                await query.edit_message_text("❓ Unknown or unhandled action.")
                message_edited_flag = True

            if message_edited_flag:
                await query.answer()

        except BadRequest as e:
            if "Message is not modified" in str(e):
                logger.debug(f"Callback {data}: Message not modified. Silently answering.")
                await query.answer()
            else:
                logger.error(f"BadRequest during callback {data}: {e}", exc_info=True)
                await query.answer("⚠️ Telegram API Error.", show_alert=True)
                if query.message:
                    try:
                        await query.edit_message_text(f"❌ Telegram API error: {str(e)[:100]}", parse_mode='Markdown')
                    except Exception:
                        pass  # Ignore if edit fails
        except ValueError as ve:
            logger.warning(f"ValueError during callback {data}: {ve}")
            await query.answer(f"⚠️ {str(ve)[:150]}", show_alert=True)
            if query.message:
                try:
                    await query.edit_message_text(f"❌ {str(ve)}", parse_mode='Markdown')
                except BadRequest as e_br:
                    if "Message is not modified" in str(e_br):
                        await query.answer()
                    else:
                        logger.error(f"Nested BadRequest: {e_br}")
                except Exception:
                    pass  # Ignore if edit fails
        except Exception as e:
            logger.error(f"Unexpected error processing callback {data}: {e}", exc_info=True)
            await query.answer("❌ Internal error.", show_alert=True)
            if query.message:
                try:
                    await query.edit_message_text("❌ An unexpected internal error occurred.", parse_mode='Markdown')
                except BadRequest as e_br:
                    if "Message is not modified" in str(e_br):
                        await query.answer()
                    else:
                        logger.error(f"Nested BadRequest: {e_br}")
                except Exception:
                    pass  # Ignore if edit fails

    async def _handle_global_stats_callback(self, query: Update.callback_query) -> None:
        global_stats_data = await self._analytics_service.get_global_statistics()
        message = (
            f"🌍 **Global Analytics Dashboard**\n\n"
            f"🤖 **Total Bots:** {global_stats_data.total_bots}\n"
            f"🟢 **Active Today:** {global_stats_data.active_bots}\n"
            f"👥 **Total Users:** {global_stats_data.total_users_across_bots:,}\n"
            f"💬 **Interactions Today:** {global_stats_data.total_interactions_today:,}\n\n"
        )
        if global_stats_data.most_active_bot:
            try:
                bot_conf = await self._bot_management.get_monitored_bot_details(global_stats_data.most_active_bot)
                message += f"🏆 **Most Active Bot:** {bot_conf.name if bot_conf else 'ID'} (`{global_stats_data.most_active_bot}`)\n"
            except Exception:
                message += f"🏆 **Most Active Bot:** ID `{global_stats_data.most_active_bot}` (Error fetching details)\n"

        if global_stats_data.least_active_bot:
            try:
                bot_conf = await self._bot_management.get_monitored_bot_details(global_stats_data.least_active_bot)
                message += f"😴 **Least Active Bot:** {bot_conf.name if bot_conf else 'ID'} (`{global_stats_data.least_active_bot}`)\n"
            except Exception:
                message += f"😴 **Least Active Bot:** ID `{global_stats_data.least_active_bot}` (Error fetching details)\n"

        keyboard = [[InlineKeyboardButton("🤖 List All Bots", callback_data="list_bots")],
                    [InlineKeyboardButton("🔄 Refresh", callback_data="global_stats")]]
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    async def _handle_list_bots_callback(self, query: Update.callback_query) -> None:
        bots = await self._bot_management.get_all_monitored_bots()
        if not bots:
            await query.edit_message_text("📋 No bots are currently being monitored.")
            return

        message = "🤖 **Monitored Bots:**\n\n"
        for bot_item in bots:
            status = "🟢 Active" if bot_item.is_active else "🔴 Inactive"
            message += (f"**{bot_item.name}**\nID: `{bot_item.bot_id}`\nStatus: {status}\n"
                        f"Added: {bot_item.created_at.strftime('%Y-%m-%d') if bot_item.created_at else 'N/A'}\n\n")
        keyboard = [[InlineKeyboardButton(f"📊 {b.name} Stats", callback_data=f"stats_{b.bot_id}")] for b in bots[:5]]
        keyboard.extend([[InlineKeyboardButton("🔄 Refresh", callback_data="list_bots")],
                         [InlineKeyboardButton("🔙 Back to Menu", callback_data="global_stats")]])
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    async def _handle_add_bot_help_callback(self, query: Update.callback_query) -> None:
        message = (
            "➕ **Add Bot to Monitoring**\n\n"
            "**Command:** `/add_bot <name> <token> [description]`\n\n"
            "**Parameters:**\n"
            "• `<name>` - Bot name (use quotes if it contains spaces)\n"
            "• `<token>` - Bot token from @BotFather\n"
            "• `[description]` - Optional description\n\n"
            "**Examples:**\n"
            "`/add_bot MyBot 123456:ABC-DEF...`\n"
            "`/add_bot \"Taxi Bot\" 123456:ABC-DEF... \"For taxi bookings\"`\n\n"
            "ℹ️ The bot token will be validated before adding."
        )
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="global_stats")]]
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    async def _handle_bot_stats_callback(self, query: Update.callback_query, bot_id: str) -> None:
        stats_data = await self._analytics_service.get_bot_statistics(bot_id)
        last_interaction_str = stats_data.last_interaction.strftime(
            '%Y-%m-%d %H:%M') if stats_data.last_interaction else "Never"
        message = (
            f"📊 **Statistics for {stats_data.bot_name}**\n\n"
            f"👥 **Total Users:** {stats_data.total_users:,}\n"
            f"🟢 **Daily Active:** {stats_data.daily_active_users:,}\n"
            f"📅 **Weekly Active:** {stats_data.weekly_active_users:,}\n"
            f"📆 **Monthly Active:** {stats_data.monthly_active_users:,}\n"
            f"🆕 **New Users Today:** {stats_data.new_users_today:,}\n"
            f"💬 **Total Interactions:** {stats_data.total_interactions:,}\n"
            f"🕐 **Last Interaction:** {last_interaction_str}\n\n"
            f"**Bot ID:** `{stats_data.bot_id}`"
        )
        keyboard = [[InlineKeyboardButton("📈 Weekly Timeline", callback_data=f"timeline_{bot_id}")],
                    [InlineKeyboardButton("🔄 Refresh", callback_data=f"stats_{bot_id}")],
                    [InlineKeyboardButton("🔙 Back to List", callback_data="list_bots")]]
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    async def _handle_timeline_callback(self, query: Update.callback_query, bot_id: str) -> None:
        bot_config = await self._bot_management.get_monitored_bot_details(bot_id)
        if not bot_config:  # Bot not found by ID
            await query.edit_message_text(f"📈 **Timeline for Bot ID {bot_id}**\n\n❌ Bot details not found.",
                                          parse_mode='Markdown')
            return
        bot_name = bot_config.name

        timeline_data = await self._bot_management.get_bot_activity_timeline(bot_id, 7)
        message = f"📈 **7-Day Timeline for {bot_name}**\n\n"

        if not timeline_data:  # Should be a list of 7 items, even if all zeros
            message += "▫️ No activity data available (or bot just added)."
        else:
            has_any_activity = any(entry.unique_users > 0 or entry.total_interactions > 0 for entry in timeline_data)
            if not has_any_activity:
                message += "▫️ No activity recorded in the last 7 days."
            else:
                for entry in timeline_data:
                    user_bar_fill = min(entry.unique_users // 2 if entry.unique_users > 0 else 0, 10)
                    user_bar = "👤" * user_bar_fill + "▫️" * (10 - user_bar_fill)
                    message += f"`{entry.date}` {user_bar} {entry.unique_users:2d}👥 {entry.total_interactions:3d}💬\n"
        message += f"\n📊 Legend: 👥 Unique Users | 💬 Interactions"

        keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data=f"timeline_{bot_id}")],
                    [InlineKeyboardButton("🔙 Back to Stats", callback_data=f"stats_{bot_id}")]]
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    async def _handle_confirm_remove_callback(self, query: Update.callback_query, bot_id: str) -> None:
        bot_config = await self._bot_management.get_monitored_bot_details(bot_id)
        if not bot_config:
            await query.edit_message_text(f"❌ Bot with ID `{bot_id}` not found or already removed.",
                                          parse_mode='Markdown')
            return

        bot_name_for_message = bot_config.name
        success = await self._analytics_service.remove_bot(bot_id)
        if success:
            await query.edit_message_text(
                f"✅ **Bot Removed Successfully**\n\n"
                f"**{bot_name_for_message}** (`{bot_id}`) has been removed from monitoring.\n"
                f"⚠️ All analytics data for this bot has been deleted.", parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                f"❌ Failed to remove bot `{bot_id}`. (Error or already removed).", parse_mode='Markdown'
            )