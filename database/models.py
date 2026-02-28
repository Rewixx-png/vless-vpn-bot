from sqlalchemy import Column, BigInteger, String, Boolean, Integer, DateTime, Text, ForeignKey, Float
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)
    
    country_filter = Column(Text, nullable=True, default=None)
    tags_filter = Column(Text, nullable=True, default=None)
    
    subscription_limit = Column(Integer, default=0)
    language = Column(String, default="ru")
    use_fragment = Column(Boolean, default=False)
    
    created_at = Column(
        DateTime(timezone=True), server_default=func.now()
    )

class UserGroup(Base):
    __tablename__ = "user_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), index=True)
    name = Column(String, nullable=False)
    country_filter = Column(Text, nullable=True)
    tags_filter = Column(Text, nullable=True, default=None)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now()
    )

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    __mapper_args__ = {"confirm_deleted_rows": False}

    id = Column(Integer, primary_key=True, autoincrement=True)
    vless_key = Column(Text, unique=True, nullable=False)
    region = Column(String, nullable=False, index=True)
    latency_ms = Column(Integer, default=9999)
    speed_mbps = Column(Float, default=0.0)
    ai_available = Column(Boolean, default=False)
    
    is_active = Column(Boolean, default=True)
    death_count = Column(Integer, default=0)
    stability_streak = Column(Integer, default=0)
    
    last_checked_at = Column(
        DateTime(timezone=True), server_default=func.now()
    )
    added_at = Column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self):
        return f"<Subscription(id={self.id}, region='{self.region}')>"

class SubscriptionSource(Base):
    __tablename__ = "subscription_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(Text, unique=True, nullable=False)
    title = Column(String, nullable=True)
    is_enabled = Column(Boolean, default=True)
    
    added_at = Column(
        DateTime(timezone=True), server_default=func.now()
    )

class BlacklistedItem(Base):
    __tablename__ = "blacklist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vless_key = Column(Text, unique=True, nullable=False)
    reason = Column(String, nullable=True)
    added_at = Column(
        DateTime(timezone=True), server_default=func.now()
    )

class SystemConfig(Base):
    __tablename__ = "system_config"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)
