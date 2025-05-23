# src/infrastructure/http/analytics_server.py
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import logging

from ...domain.interfaces import IAnalyticsService

logger = logging.getLogger(__name__)


class InteractionData(BaseModel):
    """Request model for interaction tracking."""
    bot_token: str
    user_id: int
    interaction_type: str
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language_code: Optional[str] = None
    message_text: Optional[str] = None
    timestamp: Optional[datetime] = None


class AnalyticsHttpServer:
    """HTTP server for receiving analytics data from monitored bots."""

    def __init__(self, analytics_service: IAnalyticsService, api_key: str):
        self.analytics_service = analytics_service
        self.api_key = api_key
        self.app = FastAPI(title="Bot Analytics API", version="1.0.0")
        self._setup_routes()

    def _verify_api_key(self, x_api_key: str = Header(...)) -> bool:
        """Verify API key for authentication."""
        if x_api_key != self.api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return True

    def _setup_routes(self) -> None:
        """Setup HTTP routes."""

        @self.app.post("/track-interaction")
        async def track_interaction(
                data: InteractionData,
                _: bool = Depends(self._verify_api_key)
        ):
            """Endpoint for bots to report interactions."""
            try:
                await self.analytics_service.track_interaction(
                    bot_id_or_token=data.bot_token,
                    user_id=data.user_id,
                    interaction_type=data.interaction_type,
                    timestamp=data.timestamp or datetime.now(),
                    username=data.username,
                    first_name=data.first_name,
                    last_name=data.last_name,
                    language_code=data.language_code,
                    message_text=data.message_text,
                    is_token=True
                )
                return {"status": "success", "message": "Interaction recorded"}
            except Exception as e:
                logger.error(f"Error tracking interaction: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "healthy", "timestamp": datetime.now()}

        @self.app.get("/bots/{bot_token}/stats")
        async def get_bot_stats_by_token(
                bot_token: str,
                _: bool = Depends(self._verify_api_key)
        ):
            """Get bot statistics by token."""
            try:
                # First get bot config to find bot_id
                bot_config = await self.analytics_service._bot_config_repo.get_by_token(bot_token)
                if not bot_config:
                    raise HTTPException(status_code=404, detail="Bot not found")

                stats = await self.analytics_service.get_bot_statistics(bot_config.bot_id)
                return {
                    "bot_id": stats.bot_id,
                    "bot_name": stats.bot_name,
                    "total_users": stats.total_users,
                    "daily_active_users": stats.daily_active_users,
                    "weekly_active_users": stats.weekly_active_users,
                    "monthly_active_users": stats.monthly_active_users,
                    "new_users_today": stats.new_users_today,
                    "total_interactions": stats.total_interactions,
                    "last_interaction": stats.last_interaction
                }
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except Exception as e:
                logger.error(f"Error fetching bot stats: {e}")
                raise HTTPException(status_code=500, detail=str(e))