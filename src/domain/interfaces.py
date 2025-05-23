# src/domain/interfaces.py
from abc import ABC, abstractmethod
from datetime import date, datetime # Added datetime
from typing import List, Optional, Dict

from .models import BotConfig, UserInteraction, BotStats, GlobalStats, ActivityTimeline


class IBotConfigRepository(ABC):
    """Repository interface for bot configuration management."""

    @abstractmethod
    async def create(self, bot_config: BotConfig) -> BotConfig:
        """Create a new bot configuration."""
        pass

    @abstractmethod
    async def get_by_id(self, bot_id: str) -> Optional[BotConfig]:
        """Retrieve bot configuration by ID."""
        pass

    @abstractmethod
    async def get_all(self) -> List[BotConfig]:
        """Retrieve all bot configurations."""
        pass

    @abstractmethod
    async def update(self, bot_config: BotConfig) -> BotConfig:
        """Update bot configuration."""
        pass

    @abstractmethod
    async def delete(self, bot_id: str) -> bool:
        """Delete bot configuration."""
        pass

    @abstractmethod
    async def get_by_token(self, token: str) -> Optional[BotConfig]:
        """Retrieve bot configuration by token."""
        pass


class IUserInteractionRepository(ABC):
    """Repository interface for user interaction management."""

    @abstractmethod
    async def record_interaction(self, interaction: UserInteraction) -> None:
        """Record a user interaction."""
        pass

    @abstractmethod
    async def get_bot_stats(self, bot_id: str, target_date: date) -> BotStats:
        """Get statistics for a specific bot."""
        pass

    @abstractmethod
    async def get_global_stats(self, target_date: date) -> GlobalStats:
        """Get global statistics across all bots."""
        pass

    @abstractmethod
    async def get_activity_timeline(self, bot_id: str, days: int = 7) -> List[ActivityTimeline]:
        """Get user activity timeline for a bot."""
        pass


class IAnalyticsService(ABC):
    """Service interface for analytics operations."""

    @abstractmethod
    async def add_bot(self, name: str, token: str, description: Optional[str] = None) -> BotConfig:
        """Add a new bot to monitoring."""
        pass

    @abstractmethod
    async def remove_bot(self, bot_id: str) -> bool:
        """Remove a bot from monitoring."""
        pass

    @abstractmethod
    async def get_bot_statistics(self, bot_id: str) -> BotStats:
        """Get statistics for a specific bot."""
        pass

    @abstractmethod
    async def get_global_statistics(self) -> GlobalStats:
        """Get global statistics."""
        pass

    @abstractmethod
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
        """
        Tracks a user interaction.
        If is_token is True, bot_id_or_token is treated as a bot token to find the bot_id.
        Otherwise, it's treated as a direct bot_id.
        """
        pass


class IBotMonitoringService(ABC):
    """Service interface for bot monitoring operations."""

    @abstractmethod
    async def start_monitoring(self) -> None:
        """Start monitoring service."""
        pass

    @abstractmethod
    async def stop_monitoring(self) -> None:
        """Stop monitoring service."""
        pass

    @abstractmethod
    async def validate_bot_token(self, token: str) -> Dict:
        """Validate and get bot information."""
        pass