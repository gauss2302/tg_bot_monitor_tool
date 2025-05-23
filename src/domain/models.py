# src/domain/models.py
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional


@dataclass(frozen=True)
class BotConfig:
    """Configuration for a monitored bot."""
    bot_id: str
    name: str
    token: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    is_active: bool = True


@dataclass(frozen=True)
class UserInteraction:
    """Domain model for user interactions."""
    bot_id: str
    user_id: int  # Changed from str to int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    language_code: Optional[str]
    interaction_type: str
    timestamp: datetime
    message_text: Optional[str] = None


@dataclass(frozen=True)
class BotStats:
    """Statistics for a specific bot."""
    bot_id: str
    bot_name: str
    total_users: int
    daily_active_users: int
    weekly_active_users: int
    monthly_active_users: int
    new_users_today: int
    total_interactions: int
    last_interaction: Optional[datetime]


@dataclass(frozen=True)
class GlobalStats:
    """Global statistics across all bots."""
    total_bots: int
    active_bots: int
    total_users_across_bots: int
    total_interactions_today: int
    most_active_bot: Optional[str]
    least_active_bot: Optional[str]


@dataclass(frozen=True)
class ActivityTimeline:
    """Daily activity data point."""
    date: str # This is 'YYYY-MM-DD' string from SQLite DATE() function
    unique_users: int
    total_interactions: int