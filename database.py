from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Float, DateTime, Integer, Text, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from config import DB_PATH
from security import redact_secrets

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False, "timeout": 30},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class MarketQuote(Base):
    __tablename__ = "market_quotes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(40), index=True)
    date: Mapped[str] = mapped_column(String(10), index=True)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(80), default="Yahoo Finance")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_quote_symbol_date"),)

class MacroIndicator(Base):
    __tablename__ = "macro_indicators"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[str] = mapped_column(String(40), index=True)
    date: Mapped[str] = mapped_column(String(10), index=True)
    value: Mapped[float] = mapped_column(Float)
    units: Mapped[str] = mapped_column(String(40), default="")
    source: Mapped[str] = mapped_column(String(80), default="FRED")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("series_id", "date", name="uq_macro_series_date"),)

class ImportedDatum(Base):
    __tablename__ = "imported_data"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset: Mapped[str] = mapped_column(String(40), index=True)
    date: Mapped[str] = mapped_column(String(10), index=True)
    key: Mapped[str] = mapped_column(String(100), default="")
    value1: Mapped[float | None] = mapped_column(Float, nullable=True)
    value2: Mapped[float | None] = mapped_column(Float, nullable=True)
    value3: Mapped[float | None] = mapped_column(Float, nullable=True)
    value4: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(100), default="CSV import")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("dataset", "date", "key", name="uq_import_dataset_date_key"),)

class ScoreRecord(Base):
    __tablename__ = "market_scores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    macro_score: Mapped[float] = mapped_column(Float)
    flows_score: Mapped[float] = mapped_column(Float)
    technical_score: Mapped[float] = mapped_column(Float)
    domestic_score: Mapped[float] = mapped_column(Float)
    total_score: Mapped[float] = mapped_column(Float)
    note: Mapped[str] = mapped_column(Text, default="")

class CollectionLog(Base):
    __tablename__ = "collection_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(engine)
    # SQLite WAL improves dashboard reads while the collector writes.
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        conn.exec_driver_sql("PRAGMA busy_timeout=5000")
    _sanitize_collection_logs()


def _sanitize_collection_logs():
    with SessionLocal() as session:
        changed = False
        for log in session.query(CollectionLog).all():
            safe_message = redact_secrets(log.message)
            if safe_message != log.message:
                log.message = safe_message
                changed = True
        if changed:
            session.commit()
