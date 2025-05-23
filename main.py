# main.py - Updated with HTTP server
import asyncio
import logging
import uvicorn
from contextlib import asynccontextmanager

from src.config.settings import settings
from src.domain.interfaces import (
    IBotConfigRepository, IUserInteractionRepository,
    IAnalyticsService, IBotMonitoringService
)
from src.infrastructure.database.sqlite_repositories import (
    SQLiteBotConfigRepository, SQLiteUserInteractionRepository
)
from src.application.services.analytics_service import AnalyticsService
from src.application.services.monitoring_service import BotMonitoringService
from src.application.use_cases.bot_management import BotManagementUseCase
from src.infrastructure.telegram.bot_handlers import TelegramBotHandlers
from src.presentation.telegram_bot import TelegramBotApplication
from src.infrastructure.http.analytics_server import AnalyticsHttpServer

# Global variables to store app components
telegram_bot_app = None
analytics_http_server = None


@asynccontextmanager
async def lifespan(app):
    """Lifespan context manager for FastAPI app."""
    global telegram_bot_app

    # Startup: Start Telegram bot
    if telegram_bot_app:
        asyncio.create_task(telegram_bot_app.run())

    yield

    # Shutdown: Stop services
    if telegram_bot_app and telegram_bot_app.monitoring_service:
        await telegram_bot_app.monitoring_service.stop_monitoring()


def configure_logging():
    """Configures application-wide logging."""
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=settings.LOG_LEVEL
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.INFO)
    logging.getLogger("uvicorn").setLevel(logging.INFO)


async def initialize_components():
    """Initialize all application components."""
    global telegram_bot_app, analytics_http_server

    logger = logging.getLogger(__name__)
    logger.info("Initializing application components...")

    # 1. Initialize Repositories
    bot_config_repo: IBotConfigRepository = SQLiteBotConfigRepository(db_path=settings.DATABASE_PATH)
    interaction_repo: IUserInteractionRepository = SQLiteUserInteractionRepository(db_path=settings.DATABASE_PATH)
    logger.info("Repositories initialized.")

    # 2. Initialize Services
    analytics_service_instance: AnalyticsService = AnalyticsService(
        bot_config_repo=bot_config_repo,
        interaction_repo=interaction_repo
    )
    analytics_service: IAnalyticsService = analytics_service_instance

    monitoring_service_instance: BotMonitoringService = BotMonitoringService(analytics_service=analytics_service)
    monitoring_service: IBotMonitoringService = monitoring_service_instance
    logger.info("Services initialized.")

    # 3. Initialize Use Cases
    bot_management_use_case = BotManagementUseCase(
        bot_config_repo=bot_config_repo,
        interaction_repo=interaction_repo
    )
    logger.info("Use Cases initialized.")

    # 4. Initialize Telegram Bot
    telegram_handlers = TelegramBotHandlers(
        analytics_service=analytics_service,
        bot_management=bot_management_use_case,
        admin_user_ids=settings.ADMIN_USER_IDS,
    )

    telegram_bot_app = TelegramBotApplication(
        token=settings.ANALYTICS_BOT_TOKEN,
        handlers_class=telegram_handlers,
        monitoring_service=monitoring_service
    )
    logger.info("Telegram Bot Application initialized.")

    # 5. Initialize HTTP Server
    api_key = settings.API_KEY if hasattr(settings, 'API_KEY') else "your-secret-api-key"
    analytics_http_server = AnalyticsHttpServer(
        analytics_service=analytics_service,
        api_key=api_key
    )
    logger.info("HTTP Analytics Server initialized.")

    return analytics_http_server.app


async def run_telegram_bot():
    """Run the Telegram bot in a separate task."""
    global telegram_bot_app

    if telegram_bot_app:
        try:
            await telegram_bot_app.run()
        except Exception as e:
            logging.error(f"Error running Telegram bot: {e}")


async def main_async():
    """Main async function."""
    configure_logging()
    logger = logging.getLogger(__name__)

    try:
        # Initialize components
        app = await initialize_components()

        # Start Telegram bot as background task
        telegram_task = asyncio.create_task(run_telegram_bot())

        # Configure and run HTTP server
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=8000,
            log_level="info"
        )
        server = uvicorn.Server(config)

        logger.info("Starting HTTP server on http://0.0.0.0:8000")
        logger.info("Starting Telegram bot...")

        # Run HTTP server
        await server.serve()

    except KeyboardInterrupt:
        logger.info("Application shutting down due to KeyboardInterrupt...")
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
    finally:
        logger.info("Application shutdown sequence initiated.")
        if telegram_bot_app and telegram_bot_app.monitoring_service:
            await telegram_bot_app.monitoring_service.stop_monitoring()
        logger.info("Application finished.")


if __name__ == "__main__":
    asyncio.run(main_async())