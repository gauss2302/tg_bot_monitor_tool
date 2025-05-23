# analytics_sdk.py - SDK for monitored bots
import aiohttp
import asyncio
import logging
import hmac
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from telegram import Update, User
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from dataclasses import dataclass, asdict
from collections import deque
import time

logger = logging.getLogger(__name__)


@dataclass
class InteractionData:
    """Data structure for interaction tracking."""
    user_id: int
    interaction_type: str
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language_code: Optional[str] = None
    message_text: Optional[str] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class AnalyticsSDK:
    """SDK for monitored bots to send analytics data."""

    def __init__(
            self,
            webhook_url: str,
            bot_token: str,
            webhook_secret: Optional[str] = None,
            batch_size: int = 10,
            batch_timeout: int = 30,
            max_retries: int = 3
    ):
        self.webhook_url = webhook_url.rstrip('/')
        self.bot_token = bot_token
        self.webhook_secret = webhook_secret
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.max_retries = max_retries

        # Batching
        self.interaction_queue: deque = deque()
        self.last_batch_time = time.time()
        self.batch_task: Optional[asyncio.Task] = None

        # HTTP session
        self.session: Optional[aiohttp.ClientSession] = None

        # Statistics
        self.sent_count = 0
        self.failed_count = 0
        self.last_error: Optional[str] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    def _create_signature(self, payload: str) -> str:
        """Create HMAC signature for webhook payload."""
        if not self.webhook_secret:
            return ""

        signature = hmac.new(
            self.webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

        return f"sha256={signature}"

    async def track_interaction(
            self,
            user_id: int,
            interaction_type: str,
            username: Optional[str] = None,
            first_name: Optional[str] = None,
            last_name: Optional[str] = None,
            language_code: Optional[str] = None,
            message_text: Optional[str] = None,
            timestamp: Optional[datetime] = None,
            send_immediately: bool = False
    ) -> bool:
        """Track a single interaction."""
        interaction = InteractionData(
            user_id=user_id,
            interaction_type=interaction_type,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            message_text=message_text,
            timestamp=timestamp or datetime.now()
        )

        if send_immediately:
            return await self._send_single_interaction(interaction)
        else:
            return await self._add_to_batch(interaction)

    async def track_from_update(
            self,
            update: Update,
            interaction_type: Optional[str] = None,
            send_immediately: bool = False
    ) -> bool:
        """Track interaction from Telegram Update object."""
        if not update.effective_user:
            return False

        user = update.effective_user
        message_text = None

        # Determine interaction type if not provided
        if interaction_type is None:
            if update.message:
                if update.message.text and update.message.text.startswith('/'):
                    interaction_type = "command"
                else:
                    interaction_type = "message"
            elif update.callback_query:
                interaction_type = "callback_query"
                message_text = f"callback: {update.callback_query.data}"
            else:
                interaction_type = "unknown"

        # Get message text if not already set
        if message_text is None and update.message and update.message.text:
            message_text = update.message.text[:500]  # Limit length

        return await self.track_interaction(
            user_id=user.id,
            interaction_type=interaction_type,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
            message_text=message_text,
            send_immediately=send_immediately
        )

    async def _add_to_batch(self, interaction: InteractionData) -> bool:
        """Add interaction to batch queue."""
        self.interaction_queue.append(interaction)

        # Start batch processing task if not running
        if self.batch_task is None or self.batch_task.done():
            self.batch_task = asyncio.create_task(self._batch_processor())

        # Send immediately if batch is full
        if len(self.interaction_queue) >= self.batch_size:
            await self._send_batch()

        return True

    async def _batch_processor(self):
        """Background task to process batches."""
        while True:
            try:
                # Wait for batch timeout
                await asyncio.sleep(self.batch_timeout)

                # Send batch if there are interactions
                if self.interaction_queue:
                    await self._send_batch()

            except asyncio.CancelledError:
                # Send remaining interactions before cancelling
                if self.interaction_queue:
                    await self._send_batch()
                break
            except Exception as e:
                logger.error(f"Error in batch processor: {e}")
                await asyncio.sleep(5)  # Wait before retrying

    async def _send_single_interaction(self, interaction: InteractionData) -> bool:
        """Send single interaction immediately."""
        payload = {
            "bot_token": self.bot_token,
            **asdict(interaction)
        }

        # Convert datetime to ISO string
        payload["timestamp"] = interaction.timestamp.isoformat()

        return await self._send_webhook(
            f"{self.webhook_url}/webhook/interaction",
            payload
        )

    async def _send_batch(self) -> bool:
        """Send batch of interactions."""
        if not self.interaction_queue:
            return True

        # Get interactions from queue
        interactions = []
        while self.interaction_queue and len(interactions) < self.batch_size:
            interaction = self.interaction_queue.popleft()
            interaction_dict = asdict(interaction)
            interaction_dict["timestamp"] = interaction.timestamp.isoformat()
            interactions.append(interaction_dict)

        payload = {
            "bot_token": self.bot_token,
            "interactions": interactions
        }

        success = await self._send_webhook(
            f"{self.webhook_url}/webhook/batch",
            payload
        )

        if not success:
            # Put interactions back in queue on failure
            for interaction_dict in interactions:
                interaction_dict["timestamp"] = datetime.fromisoformat(interaction_dict["timestamp"])
                interaction = InteractionData(**interaction_dict)
                self.interaction_queue.appendleft(interaction)

        return success

    async def _send_webhook(self, url: str, payload: Dict[str, Any]) -> bool:
        """Send webhook with retries."""
        for attempt in range(self.max_retries):
            try:
                session = await self._get_session()
                payload_json = json.dumps(payload, default=str)

                headers = {"Content-Type": "application/json"}
                if self.webhook_secret:
                    headers["X-Hub-Signature-256"] = self._create_signature(payload_json)

                async with session.post(url, data=payload_json, headers=headers) as response:
                    if response.status == 200:
                        self.sent_count += 1
                        logger.debug(f"Analytics data sent successfully")
                        return True
                    else:
                        error_text = await response.text()
                        self.last_error = f"HTTP {response.status}: {error_text}"
                        logger.warning(f"Failed to send analytics data: {self.last_error}")

            except Exception as e:
                self.last_error = str(e)
                logger.error(f"Error sending analytics data (attempt {attempt + 1}): {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

        self.failed_count += 1
        return False

    async def flush(self) -> bool:
        """Send all queued interactions immediately."""
        if not self.interaction_queue:
            return True

        return await self._send_batch()

    def get_stats(self) -> Dict[str, Any]:
        """Get SDK statistics."""
        return {
            "sent_count": self.sent_count,
            "failed_count": self.failed_count,
            "queued_count": len(self.interaction_queue),
            "last_error": self.last_error,
            "success_rate": (
                self.sent_count / (self.sent_count + self.failed_count)
                if (self.sent_count + self.failed_count) > 0 else 1.0
            )
        }

    async def close(self):
        """Close SDK and send remaining data."""
        # Cancel batch processor
        if self.batch_task and not self.batch_task.done():
            self.batch_task.cancel()
            try:
                await self.batch_task
            except asyncio.CancelledError:
                pass

        # Send remaining interactions
        await self.flush()

        # Close HTTP session
        if self.session and not self.session.closed:
            await self.session.close()


class TelegramAnalyticsMiddleware:
    """Middleware to automatically track Telegram bot interactions."""

    def __init__(self, analytics_sdk: AnalyticsSDK):
        self.sdk = analytics_sdk

    async def track_message(self, update: Update, context) -> None:
        """Handler to track message interactions."""
        await self.sdk.track_from_update(update)

    async def track_command(self, update: Update, context) -> None:
        """Handler to track command interactions."""
        await self.sdk.track_from_update(update, "command")

    async def track_callback(self, update: Update, context) -> None:
        """Handler to track callback query interactions."""
        await self.sdk.track_from_update(update, "callback_query")

    def setup_auto_tracking(self, application: Application) -> None:
        """Setup automatic tracking for all interactions."""
        # Track all messages (run first, before other handlers)
        application.add_handler(
            MessageHandler(filters.ALL, self.track_message),
            group=-2
        )

