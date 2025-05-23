import logging
from typing import Dict
from telegram import Bot

from src.domain.interfaces import IBotMonitoringService, IAnalyticsService

logger = logging.getLogger(__name__)


class BotMonitoringService(IBotMonitoringService):
    """Service for bot monitoring operations."""

    def __init__(self, analytics_service: IAnalyticsService):
        self._analytics_service = analytics_service
        self._monitoring_active = False

    async def start_monitoring(self) -> None:
        """Start monitoring service."""
        self._monitoring_active = True
        logger.info("Bot monitoring service started")

    async def stop_monitoring(self) -> None:
        """Stop monitoring service."""
        self._monitoring_active = False
        logger.info("Bot monitoring service stopped")

    async def validate_bot_token(self, token: str) -> Dict:
        """Validate and get bot information."""
        try:
            bot = Bot(token)
            bot_info = await bot.get_me()
            return {
                "id": bot_info.id,
                "username": bot_info.username,
                "first_name": bot_info.first_name,
                "is_bot": bot_info.is_bot
            }
        except Exception as e:
            logger.error(f"Error validating bot token: {e}")
            return {}

    @property
    def is_monitoring_active(self) -> bool:
        """Check if monitoring is active."""
        return self._monitoring_active