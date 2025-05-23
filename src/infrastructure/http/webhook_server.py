# src/infrastructure/http/webhook_server.py
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
import asyncio
import logging
import hmac
import hashlib

from ...domain.interfaces import IAnalyticsService

logger = logging.getLogger(__name__)


class InteractionPayload(BaseModel):
    """Payload for interaction data from monitored bots."""
    bot_token: str
    user_id: int
    interaction_type: str
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language_code: Optional[str] = None
    message_text: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class BatchInteractionPayload(BaseModel):
    """Batch payload for multiple interactions."""
    bot_token: str
    interactions: List[InteractionPayload]


class WebhookServer:
    """HTTP webhook server for receiving analytics data from monitored bots."""

    def __init__(self, analytics_service: IAnalyticsService, webhook_secret: str):
        self.analytics_service = analytics_service
        self.webhook_secret = webhook_secret
        self.app = FastAPI(
            title="Bot Analytics Webhook Server",
            description="Receives interaction data from monitored bots",
            version="1.0.0"
        )
        self._setup_routes()

    def _verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify webhook signature for security."""
        if not signature.startswith('sha256='):
            return False

        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(f"sha256={expected_signature}", signature)

    def _setup_routes(self) -> None:
        """Setup webhook routes."""

        @self.app.post("/webhook/interaction")
        async def receive_interaction(
                payload: InteractionPayload,
                background_tasks: BackgroundTasks,
                request: Request
        ):
            """Receive single interaction from monitored bot."""
            try:
                # Verify signature if provided
                signature = request.headers.get('X-Hub-Signature-256')
                if signature:
                    body = await request.body()
                    if not self._verify_signature(body, signature):
                        raise HTTPException(status_code=401, detail="Invalid signature")

                # Process interaction in background
                background_tasks.add_task(
                    self._process_interaction,
                    payload
                )

                return {"status": "accepted", "message": "Interaction queued for processing"}

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error receiving interaction: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        @self.app.post("/webhook/batch")
        async def receive_batch_interactions(
                payload: BatchInteractionPayload,
                background_tasks: BackgroundTasks,
                request: Request
        ):
            """Receive batch of interactions from monitored bot."""
            try:
                # Verify signature if provided
                signature = request.headers.get('X-Hub-Signature-256')
                if signature:
                    body = await request.body()
                    if not self._verify_signature(body, signature):
                        raise HTTPException(status_code=401, detail="Invalid signature")

                # Process batch in background
                background_tasks.add_task(
                    self._process_batch_interactions,
                    payload
                )

                return {
                    "status": "accepted",
                    "message": f"Batch of {len(payload.interactions)} interactions queued"
                }

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error receiving batch: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        @self.app.get("/webhook/health")
        async def health_check():
            """Health check endpoint."""
            return {
                "status": "healthy",
                "timestamp": datetime.now(),
                "service": "analytics-webhook"
            }

        @self.app.get("/webhook/stats")
        async def webhook_stats():
            """Get webhook processing statistics."""
            # You could add metrics here
            return {
                "status": "operational",
                "uptime": datetime.now(),
                "version": "1.0.0"
            }

    async def _process_interaction(self, payload: InteractionPayload) -> None:
        """Process single interaction in background."""
        try:
            await self.analytics_service.track_interaction(
                bot_id_or_token=payload.bot_token,
                user_id=payload.user_id,
                interaction_type=payload.interaction_type,
                timestamp=payload.timestamp,
                username=payload.username,
                first_name=payload.first_name,
                last_name=payload.last_name,
                language_code=payload.language_code,
                message_text=payload.message_text,
                is_token=True
            )
            logger.debug(f"Processed interaction: {payload.interaction_type} for user {payload.user_id}")
        except Exception as e:
            logger.error(f"Error processing interaction: {e}")

    async def _process_batch_interactions(self, payload: BatchInteractionPayload) -> None:
        """Process batch of interactions in background."""
        processed = 0
        failed = 0

        for interaction in payload.interactions:
            try:
                await self.analytics_service.track_interaction(
                    bot_id_or_token=payload.bot_token,
                    user_id=interaction.user_id,
                    interaction_type=interaction.interaction_type,
                    timestamp=interaction.timestamp,
                    username=interaction.username,
                    first_name=interaction.first_name,
                    last_name=interaction.last_name,
                    language_code=interaction.language_code,
                    message_text=interaction.message_text,
                    is_token=True
                )
                processed += 1
            except Exception as e:
                logger.error(f"Error processing batch interaction: {e}")
                failed += 1

        logger.info(f"Batch processing complete: {processed} processed, {failed} failed")