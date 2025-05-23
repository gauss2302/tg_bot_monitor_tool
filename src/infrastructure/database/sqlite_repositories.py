# src/infrastructure/database/sqlite_repositories.py
import sqlite3
import logging
from datetime import datetime, date, timedelta
from typing import List, Optional

from ...domain.interfaces import IBotConfigRepository, IUserInteractionRepository
from ...domain.models import BotConfig, UserInteraction, BotStats, GlobalStats, ActivityTimeline

logger = logging.getLogger(__name__)


class SQLiteBotConfigRepository(IBotConfigRepository):
    """SQLite implementation of bot configuration repository."""

    def __init__(self, db_path: str = "analytics_monitor.db"):
        self.db_path = db_path
        self._init_database()

    def _init_database(self) -> None:
        """Initialize database tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_configs (
                    bot_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    token TEXT NOT NULL UNIQUE,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)
            conn.commit()

    async def create(self, bot_config: BotConfig) -> BotConfig:
        """Create a new bot configuration."""
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute("""
                    INSERT INTO bot_configs (bot_id, name, token, description, created_at, is_active)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    bot_config.bot_id,
                    bot_config.name,
                    bot_config.token,
                    bot_config.description,
                    bot_config.created_at or datetime.now(),  # Ensure created_at is set
                    bot_config.is_active
                ))
                conn.commit()
            except sqlite3.IntegrityError as e:
                logger.error(
                    f"SQLite integrity error creating bot: {e} for bot_id={bot_config.bot_id}, token={bot_config.token}")
                # This might indicate a duplicate bot_id or token if constraints are violated.
                # The service layer should ideally check for existence before calling create.
                raise ValueError(f"Could not create bot. ID or Token might already exist: {e}")
        return bot_config

    async def get_by_id(self, bot_id: str) -> Optional[BotConfig]:
        """Retrieve bot configuration by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM bot_configs WHERE bot_id = ?", (bot_id,))
            row = cursor.fetchone()

            if row:
                return BotConfig(
                    bot_id=row['bot_id'],
                    name=row['name'],
                    token=row['token'],
                    description=row['description'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                    is_active=bool(row['is_active'])
                )
        return None

    async def get_by_token(self, token: str) -> Optional[BotConfig]:
        """Retrieve bot configuration by token."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM bot_configs WHERE token = ?", (token,))
            row = cursor.fetchone()

            if row:
                return BotConfig(
                    bot_id=row['bot_id'],
                    name=row['name'],
                    token=row['token'],
                    description=row['description'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                    is_active=bool(row['is_active'])
                )
        return None

    async def get_all(self) -> List[BotConfig]:
        """Retrieve all bot configurations."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM bot_configs ORDER BY created_at DESC")
            rows = cursor.fetchall()

            return [
                BotConfig(
                    bot_id=row['bot_id'],
                    name=row['name'],
                    token=row['token'],
                    description=row['description'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                    is_active=bool(row['is_active'])
                )
                for row in rows
            ]

    async def update(self, bot_config: BotConfig) -> BotConfig:
        """Update bot configuration."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE bot_configs
                SET name = ?, description = ?, is_active = ?
                WHERE bot_id = ?
            """, (
                bot_config.name,
                bot_config.description,
                bot_config.is_active,
                bot_config.bot_id
            ))
            conn.commit()
            # Fetch the updated record to ensure consistency or return the input if confident
            updated_config = await self.get_by_id(bot_config.bot_id)
            return updated_config if updated_config else bot_config  # Fallback, though should exist

    async def delete(self, bot_id: str) -> bool:
        """Delete bot configuration."""
        with sqlite3.connect(self.db_path) as conn:
            # Before deleting from bot_configs, delete related interactions
            # This is manual cascade because SQLite FKs might not be enforced by default
            # or ON DELETE CASCADE might not be set.
            conn.execute("DELETE FROM user_interactions WHERE bot_id = ?", (bot_id,))
            cursor = conn.execute("DELETE FROM bot_configs WHERE bot_id = ?", (bot_id,))
            conn.commit()
            return cursor.rowcount > 0


class SQLiteUserInteractionRepository(IUserInteractionRepository):
    """SQLite implementation of user interaction repository."""

    def __init__(self, db_path: str = "analytics_monitor.db"):
        self.db_path = db_path
        self._init_database()

    def _init_database(self) -> None:
        """Initialize database tables."""
        with sqlite3.connect(self.db_path) as conn:
            # Ensure foreign key support is enabled for the connection if using PRAGMA
            # conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language_code TEXT,
                    interaction_type TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_text TEXT,
                    FOREIGN KEY (bot_id) REFERENCES bot_configs (bot_id) ON DELETE CASCADE
                )
            """)
            # Added ON DELETE CASCADE to FOREIGN KEY for automatic cleanup.
            # The manual delete in SQLiteBotConfigRepository.delete() for user_interactions
            # can be a fallback or removed if ON DELETE CASCADE works reliably.

            # Create indexes for performance
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interaction_bot_timestamp ON user_interactions(bot_id, timestamp)")  # Renamed for clarity
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interaction_user_bot ON user_interactions(user_id, bot_id)")  # Renamed
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interaction_timestamp ON user_interactions(timestamp)")  # Renamed
            conn.commit()

    async def record_interaction(self, interaction: UserInteraction) -> None:
        """Record a user interaction."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO user_interactions (
                    bot_id, user_id, username, first_name, last_name,
                    language_code, interaction_type, timestamp, message_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                interaction.bot_id,
                interaction.user_id,
                interaction.username,
                interaction.first_name,
                interaction.last_name,
                interaction.language_code,
                interaction.interaction_type,
                interaction.timestamp,
                interaction.message_text
            ))
            conn.commit()

    async def get_bot_stats(self, bot_id: str, target_date: date) -> BotStats:
        """Get statistics for a specific bot."""
        today_dt = datetime.combine(target_date, datetime.min.time())
        week_ago_dt = today_dt - timedelta(days=6)  # Start of the 7-day window including today
        month_ago_dt = today_dt - timedelta(days=29)  # Start of the 30-day window including today

        # Convert dates to strings for SQL anISON (YYYY-MM-DD)
        today_str = target_date.isoformat()
        week_ago_str = week_ago_dt.date().isoformat()
        month_ago_str = month_ago_dt.date().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Get bot name
            bot_cursor = conn.execute("SELECT name FROM bot_configs WHERE bot_id = ?", (bot_id,))
            bot_row = bot_cursor.fetchone()
            bot_name = bot_row['name'] if bot_row else "Unknown Bot"
            if not bot_row:
                logger.warning(f"Bot name not found for bot_id: {bot_id} during stats calculation.")
                # Handle this case: maybe raise error or return stats with "Unknown Bot"

            # Total unique users
            total_users_cursor = conn.execute("""
                SELECT COUNT(DISTINCT user_id) as count FROM user_interactions WHERE bot_id = ?
            """, (bot_id,))
            total_users = total_users_cursor.fetchone()['count'] or 0

            # Daily active users
            dau_cursor = conn.execute("""
                SELECT COUNT(DISTINCT user_id) as count FROM user_interactions
                WHERE bot_id = ? AND DATE(timestamp, 'localtime') = ?
            """, (bot_id, today_str))  # Using 'localtime' to match local date context
            daily_active_users = dau_cursor.fetchone()['count'] or 0

            # Weekly active users (last 7 days including today)
            wau_cursor = conn.execute("""
                SELECT COUNT(DISTINCT user_id) as count FROM user_interactions
                WHERE bot_id = ? AND DATE(timestamp, 'localtime') >= ? AND DATE(timestamp, 'localtime') <= ?
            """, (bot_id, week_ago_str, today_str))
            weekly_active_users = wau_cursor.fetchone()['count'] or 0

            # Monthly active users (last 30 days including today)
            mau_cursor = conn.execute("""
                SELECT COUNT(DISTINCT user_id) as count FROM user_interactions
                WHERE bot_id = ? AND DATE(timestamp, 'localtime') >= ? AND DATE(timestamp, 'localtime') <= ?
            """, (bot_id, month_ago_str, today_str))
            monthly_active_users = mau_cursor.fetchone()['count'] or 0

            # New users today
            # A user is new today if their first interaction timestamp for this bot falls on today.
            new_users_cursor = conn.execute("""
                SELECT COUNT(DISTINCT T1.user_id) as count
                FROM user_interactions T1
                INNER JOIN (
                    SELECT user_id, MIN(DATE(timestamp, 'localtime')) as first_interaction_date
                    FROM user_interactions
                    WHERE bot_id = ?
                    GROUP BY user_id
                ) T2 ON T1.user_id = T2.user_id
                WHERE T1.bot_id = ? AND T2.first_interaction_date = ?;
            """, (bot_id, bot_id, today_str))
            new_users_today = new_users_cursor.fetchone()['count'] or 0

            # Total interactions
            total_interactions_cursor = conn.execute("""
                SELECT COUNT(*) as count FROM user_interactions WHERE bot_id = ?
            """, (bot_id,))
            total_interactions = total_interactions_cursor.fetchone()['count'] or 0

            # Last interaction
            last_interaction_cursor = conn.execute("""
                SELECT MAX(timestamp) as max_ts FROM user_interactions WHERE bot_id = ?
            """, (bot_id,))
            last_interaction_result = last_interaction_cursor.fetchone()['max_ts']
            last_interaction = datetime.fromisoformat(last_interaction_result) if last_interaction_result else None

            return BotStats(
                bot_id=bot_id,
                bot_name=bot_name,
                total_users=total_users,
                daily_active_users=daily_active_users,
                weekly_active_users=weekly_active_users,
                monthly_active_users=monthly_active_users,
                new_users_today=new_users_today,
                total_interactions=total_interactions,
                last_interaction=last_interaction
            )

    async def get_global_stats(self, target_date: date) -> GlobalStats:
        """Get global statistics across all bots."""
        today_str = target_date.isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Total bots
            total_bots_cursor = conn.execute("SELECT COUNT(*) as count FROM bot_configs")
            total_bots = total_bots_cursor.fetchone()['count'] or 0

            # Active bots (with interactions today)
            active_bots_cursor = conn.execute("""
                SELECT COUNT(DISTINCT bot_id) as count FROM user_interactions
                WHERE DATE(timestamp, 'localtime') = ?
            """, (today_str,))
            active_bots = active_bots_cursor.fetchone()['count'] or 0

            # Total unique users across all bots
            total_users_cursor = conn.execute("""
                SELECT COUNT(DISTINCT user_id) as count FROM user_interactions
            """)
            total_users_across_bots = total_users_cursor.fetchone()['count'] or 0

            # Total interactions today
            interactions_today_cursor = conn.execute("""
                SELECT COUNT(*) as count FROM user_interactions WHERE DATE(timestamp, 'localtime') = ?
            """, (today_str,))
            total_interactions_today = interactions_today_cursor.fetchone()['count'] or 0

            # Most active bot today
            most_active_cursor = conn.execute("""
                SELECT bot_id, COUNT(*) as interaction_count
                FROM user_interactions
                WHERE DATE(timestamp, 'localtime') = ?
                GROUP BY bot_id
                ORDER BY interaction_count DESC
                LIMIT 1
            """, (today_str,))
            most_active_row = most_active_cursor.fetchone()
            most_active_bot_id = most_active_row['bot_id'] if most_active_row else None

            # Least active bot today (that has any interactions today)
            least_active_cursor = conn.execute("""
                SELECT bot_id, COUNT(*) as interaction_count
                FROM user_interactions
                WHERE DATE(timestamp, 'localtime') = ?
                GROUP BY bot_id
                ORDER BY interaction_count ASC
                LIMIT 1
            """, (today_str,))
            least_active_row = least_active_cursor.fetchone()
            least_active_bot_id = least_active_row['bot_id'] if least_active_row else None

            return GlobalStats(
                total_bots=total_bots,
                active_bots=active_bots,
                total_users_across_bots=total_users_across_bots,
                total_interactions_today=total_interactions_today,
                most_active_bot=most_active_bot_id,
                least_active_bot=least_active_bot_id
            )

    async def get_activity_timeline(self, bot_id: str, days: int = 7) -> List[ActivityTimeline]:
        """Get user activity timeline for a bot."""
        # Calculate the start date for the timeline (days ago from today)
        start_date_dt = date.today() - timedelta(days=days - 1)
        start_date_str = start_date_dt.isoformat()
        end_date_str = date.today().isoformat()  # Ensure timeline includes today

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT
                    DATE(timestamp, 'localtime') as activity_date,
                    COUNT(DISTINCT user_id) as unique_users,
                    COUNT(*) as total_interactions
                FROM user_interactions
                WHERE bot_id = ? AND DATE(timestamp, 'localtime') >= ? AND DATE(timestamp, 'localtime') <= ?
                GROUP BY DATE(timestamp, 'localtime')
                ORDER BY activity_date ASC
            """, (bot_id, start_date_str, end_date_str))
            # Generate a list of all dates in the range to ensure days with no activity are included
            all_dates_in_range = [start_date_dt + timedelta(days=i) for i in range(days)]

            activity_map = {row['activity_date']: ActivityTimeline(
                date=row['activity_date'],
                unique_users=row['unique_users'],
                total_interactions=row['total_interactions']
            ) for row in cursor.fetchall()}

            # Fill in missing dates with zero activity
            result_timeline: List[ActivityTimeline] = []
            for d_obj in all_dates_in_range:
                d_str = d_obj.isoformat()
                if d_str in activity_map:
                    result_timeline.append(activity_map[d_str])
                else:
                    result_timeline.append(ActivityTimeline(date=d_str, unique_users=0, total_interactions=0))

            return result_timeline
