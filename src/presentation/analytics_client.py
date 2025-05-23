# analytics_client.py - Library for monitored bots to use
import aiohttp
import asyncio
import logging
from datetime import datetime
from typing import Optional
from telegram import Update
from telegram.ext import Application, MessageHandler, filters

logger = logging.getLogger(__name__)


class AnalyticsClient:
    """Client for sending analytics data to the analytics server."""

    def __init__(self, analytics_url: str, api_key: str, bot_token: str):
        self.analytics_url = analytics_url.rstrip('/')
        self.api_key = api_key
        self.bot_token = bot_token
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={"X-API-Key": self.api_key}
            )
        return self.session

    async def track_interaction(
            self,
            user_id: int,
            interaction_type: str,
            username: Optional[str] = None,
            first_name: Optional[str] = None,
            last_name: Optional[str] = None,
            language_code: Optional[str] = None,
            message_text: Optional[str] = None,
            timestamp: Optional[datetime] = None
    ) -> bool:
        """Send interaction data to analytics server."""
        try:
            session = await self._get_session()

            data = {
                "bot_token": self.bot_token,
                "user_id": user_id,
                "interaction_type": interaction_type,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "language_code": language_code,
                "message_text": message_text,
                "timestamp": (timestamp or datetime.now()).isoformat()
            }

            async with session.post(
                    f"{self.analytics_url}/track-interaction",
                    json=data
            ) as response:
                if response.status == 200:
                    logger.debug(f"Interaction tracked: {interaction_type} for user {user_id}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to track interaction: {response.status} - {error_text}")
                    return False

        except Exception as e:
            logger.error(f"Error sending analytics data: {e}")
            return False

    async def track_from_update(self, update: Update, interaction_type: str) -> bool:
        """Helper to track interaction from Telegram Update object."""
        if not update.effective_user:
            return False

        user = update.effective_user
        message_text = None

        if update.message and update.message.text:
            message_text = update.message.text
        elif update.callback_query and update.callback_query.data:
            message_text = f"callback: {update.callback_query.data}"

        return await self.track_interaction(
            user_id=user.id,
            interaction_type=interaction_type,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
            message_text=message_text
        )

    async def get_bot_stats(self) -> Optional[dict]:
        """Get this bot's statistics from the analytics server."""
        try:
            session = await self._get_session()
            async with session.get(
                    f"{self.analytics_url}/bots/{self.bot_token}/stats"
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Failed to get bot stats: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error getting bot stats: {e}")
            return None

    async def close(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()


# Example integration for monitored bots
class AnalyticsMiddleware:
    """Middleware to automatically track interactions in monitored bots."""

    def __init__(self, analytics_client: AnalyticsClient):
        self.client = analytics_client

    async def track_message(self, update: Update, context) -> None:
        """Track message interactions."""
        if update.message:
            interaction_type = "command" if update.message.text and update.message.text.startswith('/') else "message"
            await self.client.track_from_update(update, interaction_type)

    async def track_callback(self, update: Update, context) -> None:
        """Track callback query interactions."""
        if update.callback_query:
            await self.client.track_from_update(update, "callback_query")

    def setup_tracking(self, application: Application) -> None:
        """Setup automatic tracking for an Application."""
        # Track all messages
        application.add_handler(
            MessageHandler(filters.ALL, self.track_message),
            group=-1  # Run before other handlers
        )
