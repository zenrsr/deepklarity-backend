import os
import logging
from typing import Optional
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool
import asyncpg
from databases import Database
from models import Base

logger = logging.getLogger(__name__)

class DatabaseService:
    """Database service with connection pooling and async support"""
    
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/quizdb")
        self.async_database_url = os.getenv("ASYNC_DATABASE_URL", self.database_url.replace("postgresql://", "postgresql+asyncpg://"))
        
        self.pool_size = int(os.getenv("DB_POOL_SIZE", "20"))
        self.max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "30"))
        self.pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
        self.pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "3600"))
        
        self.engine = None
        self.async_database = None
        self._setup_engine()
        self._setup_async_database()
    
    def _setup_engine(self):
        """Setup SQLAlchemy engine with connection pooling"""
        try:
            self.engine = create_engine(
                self.database_url,
                poolclass=QueuePool,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_timeout=self.pool_timeout,
                pool_recycle=self.pool_recycle,
                pool_pre_ping=True, 
                echo=False 
            )
            
            if self.engine.dialect.name == "sqlite":
                event.listen(self.engine, "connect", self._set_sqlite_pragma)
                event.listen(self.engine, "checkout", self._test_connection)
            
            logger.info(f"Database engine created with pool_size={self.pool_size}, max_overflow={self.max_overflow}")

            try:
                Base.metadata.create_all(self.engine)
                logger.info("Database tables ensured via SQLAlchemy metadata")
            except Exception as table_error:
                logger.error(f"Failed to create database tables: {table_error}")
                raise
            
        except Exception as e:
            logger.error(f"Failed to create database engine: {e}")
            raise
    
    def _setup_async_database(self):
        """Setup async database connection"""
        try:
            self.async_database = Database(self.async_database_url)
            logger.info("Async database connection initialized")
        except Exception as e:
            logger.error(f"Failed to create async database connection: {e}")
            raise
    
    @staticmethod
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        """Set SQLite pragmas for better performance (if using SQLite)"""
        if hasattr(dbapi_connection, 'cursor'):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()
    
    @staticmethod
    def _test_connection(dbapi_connection, connection_record, connection_proxy):
        """Test database connection before using it"""
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
        except Exception as e:
            logger.warning(f"Database connection test failed: {e}")
            raise
    
    async def connect_async(self):
        """Connect to async database"""
        if self.async_database and not self.async_database.is_connected:
            await self.async_database.connect()
            logger.info("Async database connected")
    
    async def disconnect_async(self):
        """Disconnect from async database"""
        if self.async_database and self.async_database.is_connected:
            await self.async_database.disconnect()
            logger.info("Async database disconnected")
    
    def get_engine(self) -> Engine:
        """Get the SQLAlchemy engine"""
        return self.engine
    
    def get_async_database(self) -> Database:
        """Get the async database connection"""
        return self.async_database
    
    def get_connection_info(self) -> dict:
        """Get database connection pool information"""
        if not self.engine:
            return {"status": "disconnected"}
        
        try:
            pool = self.engine.pool
            return {
                "status": "connected",
                "pool_size": pool.size(),
                "checked_in_connections": pool.checkedin(),
                "checked_out_connections": pool.checkedout(),
                "overflow_connections": pool.overflow(),
                "total_connections": pool.total(),
                "pool_timeout": self.pool_timeout,
                "pool_recycle": self.pool_recycle
            }
        except Exception as e:
            logger.error(f"Failed to get connection info: {e}")
            return {"status": "error", "error": str(e)}
    
    def test_connection(self) -> bool:
        """Test database connectivity"""
        try:
            with self.engine.connect() as connection:
                result = connection.execute("SELECT 1")
                result.fetchone()
                logger.info("Database connection test successful")
                return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    async def test_async_connection(self) -> bool:
        """Test async database connectivity"""
        try:
            if not self.async_database.is_connected:
                await self.connect_async()
            
            result = await self.async_database.fetch_one("SELECT 1")
            logger.info("Async database connection test successful")
            return True
        except Exception as e:
            logger.error(f"Async database connection test failed: {e}")
            return False

db_service = None

def get_database_service() -> DatabaseService:
    """Get or create the global database service instance"""
    global db_service
    if db_service is None:
        db_service = DatabaseService()
    return db_service
