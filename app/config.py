"""應用設定管理"""

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    # LINE
    line_channel_secret: str = field(
        default_factory=lambda: os.getenv("LINE_CHANNEL_SECRET", "")
    )
    line_channel_access_token: str = field(
        default_factory=lambda: os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    )

    # MySQL
    mysql_host: str = field(
        default_factory=lambda: os.getenv("MYSQL_HOST", "host.docker.internal")
    )
    mysql_port: int = field(
        default_factory=lambda: int(os.getenv("MYSQL_PORT", "3306"))
    )
    mysql_user: str = field(
        default_factory=lambda: os.getenv("MYSQL_USER", "medqueue")
    )
    mysql_password: str = field(
        default_factory=lambda: os.getenv("MYSQL_PASSWORD", "")
    )
    mysql_database: str = field(
        default_factory=lambda: os.getenv("MYSQL_DATABASE", "medical_queue")
    )

    # Redis
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://redis:6379/0")
    )

    # 應用
    app_env: str = field(
        default_factory=lambda: os.getenv("APP_ENV", "production")
    )
    app_debug: bool = field(
        default_factory=lambda: os.getenv("APP_DEBUG", "false").lower() == "true"
    )
    scrape_interval: int = field(
        default_factory=lambda: int(os.getenv("SCRAPE_INTERVAL_SECONDS", "60"))
    )
    notify_threshold: int = field(
        default_factory=lambda: int(os.getenv("NOTIFY_THRESHOLD", "5"))
    )

    # 管理後台
    admin_username: str = field(
        default_factory=lambda: os.getenv("ADMIN_USERNAME", "admin")
    )
    admin_password: str = field(
        default_factory=lambda: os.getenv("ADMIN_PASSWORD", "changeme")
    )

    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    @property
    def sync_database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )


settings = Settings()
