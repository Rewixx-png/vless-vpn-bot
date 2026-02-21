from sqlalchemy import BigInteger, String, Boolean, Integer, DateTime, Text, ForeignKey, Float
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func
import datetime

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=True)
    
    country_filter: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    tags_filter: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    
    subscription_limit: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str] = mapped_column(String, default="ru")
    use_fragment: Mapped[bool] = mapped_column(Boolean, default=False)
    
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

class UserGroup(Base):
    __tablename__ = "user_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    country_filter: Mapped[str] = mapped_column(Text, nullable=True)
    tags_filter: Mapped[str] = mapped_column(Text, nullable=True, default=None)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    __mapper_args__ = {"confirm_deleted_rows": False}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vless_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    region: Mapped[str] = mapped_column(String, nullable=False, index=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=9999)
    speed_mbps: Mapped[float] = mapped_column(Float, default=0.0)
    ai_available: Mapped[bool] = mapped_column(Boolean, default=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    death_count: Mapped[int] = mapped_column(Integer, default=0)
    stability_streak: Mapped[int] = mapped_column(Integer, default=0)
    
    last_checked_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    added_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self):
        return f"<Subscription(id={self.id}, region='{self.region}')>"

class SubscriptionSource(Base):
    __tablename__ = "subscription_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    
    added_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

class BlacklistedItem(Base):
    __tablename__ = "blacklist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vless_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

class SystemConfig(Base):
    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=True)
