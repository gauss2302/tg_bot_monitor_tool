# src/application/services/analytics_service.py
import logging
from datetime import datetime, date  # Ensure datetime is imported
from typing import Optional

from telegram import Bot  # For token validation in add_bot

from ...domain.interfaces import IAnalyticsService, IBotConfigRepository, IUserInteractionRepository
from ...domain.models import BotConfig, UserInteraction, BotStats, GlobalStats

logger = logging.getLogger(__name__)


class AnalyticsService(IAnalyticsService):
    """Service for analytics operations."""

    def __init__(
            self,
            bot_config_repo: IBotConfigRepository,
            interaction_repo: IUserInteractionRepository
    ):
        self._bot_config_repo = bot_config_repo
        self._interaction_repo = interaction_repo

    async def add_bot(self, name: str, token: str, description: Optional[str] = None) -> BotConfig:
        try:
            tg_bot_validator = Bot(token)
            bot_info = await tg_bot_validator.get_me()
            bot_id = str(bot_info.id)

            existing_by_id = await self._bot_config_repo.get_by_id(bot_id)
            if existing_by_id:
                raise ValueError(f"Bot with ID {bot_id} ({existing_by_id.name}) already exists.")
            existing_by_token = await self._bot_config_repo.get_by_token(token)
            if existing_by_token:
                raise ValueError(
                    f"Bot token is already registered for {existing_by_token.name} (ID: {existing_by_token.bot_id}).")

            bot_config_data = BotConfig(  # Renamed variable to avoid confusion with model name
                bot_id=bot_id, name=name, token=token, description=description,
                created_at=datetime.now(), is_active=True
            )
            return await self._bot_config_repo.create(bot_config_data)
        except ValueError as ve:
            raise ve
        except Exception as e:
            logger.error(f"Failed to validate or add bot token: {e}", exc_info=True)
            raise ValueError(f"Failed to add bot. Could not validate token or unexpected error: {e}")

    async def remove_bot(self, bot_id: str) -> bool:
        return await self._bot_config_repo.delete(bot_id)

    async def get_bot_statistics(self, bot_id: str) -> BotStats:
        bot_config = await self._bot_config_repo.get_by_id(bot_id)
        if not bot_config:
            raise ValueError(f"Bot with ID {bot_id} not found. Cannot retrieve stats.")
        return await self._interaction_repo.get_bot_stats(bot_id, date.today())

    async def get_global_statistics(self) -> GlobalStats:
        return await self._interaction_repo.get_global_stats(date.today())

    async def track_interaction(
            self,
            bot_id_or_token: str,
            user_id: int,
            interaction_type: str,
            timestamp: datetime,
            username: Optional[str] = None,
            first_name: Optional[str] = None,
            last_name: Optional[str] = None,
            language_code: Optional[str] = None,
            message_text: Optional[str] = None,
            is_token: bool = False
    ) -> None:
        """Tracks a user interaction."""
        target_bot_id: Optional[str] = None

        if is_token:
            bot_config = await self._bot_config_repo.get_by_token(bot_id_or_token)
            if not bot_config:
                logger.warning(f"track_interaction: Unknown bot token provided: {bot_id_or_token[:10]}...")
                return
            target_bot_id = bot_config.bot_id
        else:
            bot_exists_config = await self._bot_config_repo.get_by_id(bot_id_or_token)
            if not bot_exists_config:  # Check if bot_id exists
                logger.warning(f"track_interaction: Bot ID {bot_id_or_token} not found in configurations.")
                return
            target_bot_id = bot_id_or_token

        if not target_bot_id:
            logger.error("track_interaction: Could not determine target_bot_id.")
            return

        interaction = UserInteraction(
            bot_id=target_bot_id,
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            interaction_type=interaction_type,
            timestamp=timestamp,
            message_text=message_text
        )
        await self._interaction_repo.record_interaction(interaction)
        logger.debug(f"Interaction tracked for bot {target_bot_id}, user {user_id}, type {interaction_type}")