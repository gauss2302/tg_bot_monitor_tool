# src/config/settings.py
import os
import logging
from dotenv import load_dotenv
from typing import List, Optional

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

class Settings:
    """Application settings loaded from environment variables."""

    # Telegram Bot Token for the Analytics Monitor Bot
    ANALYTICS_BOT_TOKEN: Optional[str] = os.getenv("ANALYTICS_BOT_TOKEN")
    API_KEY: str = os.getenv("ANALYTICS_API_KEY", "your-secret-api-key-change-this")
    HTTP_HOST: str = os.getenv("HTTP_HOST", "0.0.0.0")
    HTTP_PORT: int = int(os.getenv("HTTP_PORT", "8000"))

    # List of admin user IDs for the Analytics Monitor Bot
    _admin_user_ids_str: Optional[str] = os.getenv("ADMIN_USER_IDS")
    ADMIN_USER_IDS: List[int] = []
    if _admin_user_ids_str:
        try:
            ADMIN_USER_IDS = [int(id_str.strip()) for id_str in _admin_user_ids_str.split(',') if id_str.strip()]
        except ValueError:
            logger.error("Invalid ADMIN_USER_IDS format. Should be comma-separated integers.")

    # Database path
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "analytics_monitor.db")

    # Logging level
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()


    def __init__(self):
        if not self.ANALYTICS_BOT_TOKEN:
            logger.critical("ANALYTICS_BOT_TOKEN environment variable is not set.")
            raise ValueError("ANALYTICS_BOT_TOKEN environment variable is not set.")
        if not self.ADMIN_USER_IDS:
            logger.warning("ADMIN_USER_IDS environment variable is not set or is invalid. Admin commands may not work.")
            # Depending on strictness, you might want to raise an error here too.
            # For now, it allows running but admin commands will fail for non-admins.

        logger.info("Settings loaded.")
        logger.info(f"Admin User IDs: {self.ADMIN_USER_IDS}")
        logger.info(f"Database Path: {self.DATABASE_PATH}")
        logger.info(f"Log Level: {self.LOG_LEVEL}")


# Single instance of settings to be imported by other modules
settings = Settings()