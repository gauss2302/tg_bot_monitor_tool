# src/presentation/telegram_bot.py
import asyncio
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from ..infrastructure.telegram.bot_handlers import TelegramBotHandlers
from ..application.services.monitoring_service import BotMonitoringService # For starting/stopping monitoring

logger = logging.getLogger(__name__)

class TelegramBotApplication:
    """Manages the Telegram bot application setup and execution."""

    def __init__(
        self,
        token: str,
        handlers_class: TelegramBotHandlers,
        monitoring_service: BotMonitoringService
    ):
        if not token:
            raise ValueError("Telegram bot token is required.")
        self.token = token
        self.handlers = handlers_class
        self.monitoring_service = monitoring_service
        self.application = Application.builder().token(self.token).build()
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Setup command and callback handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.handlers.start_handler))
        self.application.add_handler(CommandHandler("add_bot", self.handlers.add_bot_handler))
        self.application.add_handler(CommandHandler("list_bots", self.handlers.list_bots_handler))
        self.application.add_handler(CommandHandler("stats", self.handlers.stats_handler))
        self.application.add_handler(CommandHandler("global_stats", self.handlers.global_stats_handler))
        self.application.add_handler(CommandHandler("remove_bot", self.handlers.remove_bot_handler))

        # Callback query handler
        self.application.add_handler(CallbackQueryHandler(self.handlers.callback_handler))

        # Optional: Add a message handler for unknown commands or general messages if needed
        # self.application.add_handler(MessageHandler(filters.COMMAND, self.unknown_command_handler))
        # self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.echo_handler))

        logger.info("Telegram bot handlers configured.")


    # Example for unknown command handler
    # async def unknown_command_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    #     if self.handlers._is_admin(update.effective_user.id): # Accessing protected member, consider better way
    #         await update.message.reply_text("❓ Sorry, I didn't understand that command. Type /start for help.")


    async def run(self) -> None:
        """Start the Telegram bot polling."""
        await self.monitoring_service.start_monitoring() # Start monitoring service alongside bot
        logger.info("Starting Analytics Monitor Telegram Bot...")
        try:
            await self.application.initialize() # Initialize before running
            await self.application.start()
            await self.application.updater.start_polling()
            logger.info("Analytics Monitor Telegram Bot started successfully.")
            # Keep the application running until interrupted
            # In a real scenario, you might have a more graceful shutdown mechanism
            # For asyncio.run, this will run until KeyboardInterrupt or similar
            while True:
                await asyncio.sleep(3600) # Or some other mechanism to keep alive
        except Exception as e:
            logger.error(f"Error running Telegram bot: {e}", exc_info=True)
        finally:
            logger.info("Stopping Analytics Monitor Telegram Bot...")
            if self.application.updater and self.application.updater.is_running:
                await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            await self.monitoring_service.stop_monitoring()
            logger.info("Analytics Monitor Telegram Bot stopped.")