import logging
from typing import List, Optional

from ...domain.interfaces import IBotConfigRepository, IUserInteractionRepository # IAnalyticsService removed if unused here
from ...domain.models import BotConfig, ActivityTimeline

logger = logging.getLogger(__name__)


class BotManagementUseCase:
    """Use case for bot management and combined data retrieval operations."""

    def __init__(
            self,
            # analytics_service: IAnalyticsService, # Removed as it's unused in this class's methods
            bot_config_repo: IBotConfigRepository,
            interaction_repo: IUserInteractionRepository
    ):
        # self._analytics_service = analytics_service # Removed
        self._bot_config_repo = bot_config_repo
        self._interaction_repo = interaction_repo

    async def get_all_monitored_bots(self) -> List[BotConfig]:
        """
        Retrieves all bot configurations currently being monitored.
        """
        logger.debug("Fetching all monitored bots via use case.")
        return await self._bot_config_repo.get_all()

    async def get_bot_config_by_token(self, token: str) -> Optional[BotConfig]: # Added this method
        """Get bot configuration by token."""
        logger.debug(f"Fetching bot config by token '{token[:10]}...' via use case.")
        return await self._bot_config_repo.get_by_token(token)

    async def get_monitored_bot_details(self, bot_id: str) -> Optional[BotConfig]:
        """
        Retrieves detailed information for a specific monitored bot by its ID.
        Returns None if the bot is not found.
        """
        logger.debug(f"Fetching details for bot ID: {bot_id} via use case.")
        bot = await self._bot_config_repo.get_by_id(bot_id)
        # Removed warning here, caller can handle None
        return bot

    async def get_bot_activity_timeline(self, bot_id: str, days: int = 7) -> List[ActivityTimeline]:
        """
        Retrieves the activity timeline (daily unique users and interactions)
        for a specific bot over a given number of days.
        """
        logger.debug(f"Fetching activity timeline for bot ID: {bot_id} for {days} days via use case.")
        bot_config = await self._bot_config_repo.get_by_id(bot_id)
        if not bot_config:
            raise ValueError(f"Bot with ID {bot_id} not found. Cannot retrieve activity timeline.")
        return await self._interaction_repo.get_activity_timeline(bot_id, days)