"""
Configuration management for the stream processing platform
"""
import os
from typing import Dict, Any


class Config:
    """Central configuration class"""

    # JobManager Configuration
    JOBMANAGER_HOST = os.getenv("JOBMANAGER_HOST", "localhost")
    JOBMANAGER_REST_PORT = int(os.getenv("JOBMANAGER_REST_PORT", "8081"))
    JOBMANAGER_RPC_PORT = int(os.getenv("JOBMANAGER_RPC_PORT", "6123"))

    # TaskManager Configuration
    TASKMANAGER_HOST = os.getenv("TASKMANAGER_HOST", "localhost")
    TASKMANAGER_RPC_PORT = int(os.getenv("TASKMANAGER_RPC_PORT", "6124"))
    TASK_SLOTS = int(os.getenv("TASK_SLOTS", "4"))
    MEMORY_SIZE = int(os.getenv("MEMORY_SIZE", "2048"))  # MB

    # Checkpoint Configuration
    CHECKPOINT_INTERVAL = int(os.getenv("CHECKPOINT_INTERVAL", "10000"))  # ms
    CHECKPOINT_TIMEOUT = int(os.getenv("CHECKPOINT_TIMEOUT", "60000"))  # ms
    STATE_BACKEND = os.getenv("STATE_BACKEND", "rocksdb")
    STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "s3")  # Options: "s3", "gcs", "local"
    S3_CHECKPOINT_PATH = os.getenv("S3_CHECKPOINT_PATH", "s3://stream-processing/checkpoints")
    GCS_CHECKPOINT_PATH = os.getenv("GCS_CHECKPOINT_PATH", "gs://stream-processing/checkpoints")

    # AWS Configuration
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

    # GCP Configuration
    GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")

    # PostgreSQL Configuration
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB = os.getenv("POSTGRES_DB", "stream_processing")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_GROUP_ID_PREFIX = os.getenv("KAFKA_GROUP_ID_PREFIX", "stream-processing")

    # Heartbeat Configuration
    HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "5000"))  # ms
    HEARTBEAT_TIMEOUT = int(os.getenv("HEARTBEAT_TIMEOUT", "15000"))  # ms

    # Watermark Configuration
    WATERMARK_INTERVAL = int(os.getenv("WATERMARK_INTERVAL", "200"))  # ms
    WATERMARK_OUT_OF_ORDERNESS = int(os.getenv("WATERMARK_OUT_OF_ORDERNESS", "5000"))  # ms

    # Network Configuration
    BUFFER_SIZE = int(os.getenv("BUFFER_SIZE", "32768"))  # bytes
    BUFFER_POOL_SIZE = int(os.getenv("BUFFER_POOL_SIZE", "2048"))  # number of buffers
    CREDIT_INITIAL = int(os.getenv("CREDIT_INITIAL", "1024"))
    CREDIT_MIN = int(os.getenv("CREDIT_MIN", "256"))

    # RocksDB Configuration
    ROCKSDB_WRITE_BUFFER_SIZE = int(os.getenv("ROCKSDB_WRITE_BUFFER_SIZE", str(64 * 1024 * 1024)))  # 64MB
    ROCKSDB_MAX_WRITE_BUFFERS = int(os.getenv("ROCKSDB_MAX_WRITE_BUFFERS", "3"))
    ROCKSDB_BLOCK_CACHE_SIZE = int(os.getenv("ROCKSDB_BLOCK_CACHE_SIZE", str(256 * 1024 * 1024)))  # 256MB

    # Metrics Configuration
    METRICS_PORT = int(os.getenv("METRICS_PORT", "9090"))

    @classmethod
    def get_postgres_connection_string(cls) -> str:
        """Get PostgreSQL connection string"""
        return (
            f"postgresql://{cls.POSTGRES_USER}:{cls.POSTGRES_PASSWORD}"
            f"@{cls.POSTGRES_HOST}:{cls.POSTGRES_PORT}/{cls.POSTGRES_DB}"
        )

    @classmethod
    def get_config_dict(cls) -> Dict[str, Any]:
        """Get all configuration as dictionary"""
        return {
            key: value
            for key, value in cls.__dict__.items()
            if not key.startswith("_") and key.isupper()
        }

    @classmethod
    def update_from_dict(cls, config_dict: Dict[str, Any]):
        """Update configuration from dictionary"""
        for key, value in config_dict.items():
            if hasattr(cls, key):
                setattr(cls, key, value)

    @classmethod
    def get_s3_bucket(cls) -> str:
        """Extract S3 bucket name from S3_CHECKPOINT_PATH"""
        s3_path = cls.S3_CHECKPOINT_PATH
        if s3_path.startswith('s3://'):
            s3_path = s3_path[5:]
        bucket = s3_path.split('/', 1)[0]
        return bucket

    @classmethod
    def get_gcs_bucket(cls) -> str:
        """Extract GCS bucket name from GCS_CHECKPOINT_PATH"""
        gcs_path = cls.GCS_CHECKPOINT_PATH
        if gcs_path.startswith('gs://'):
            gcs_path = gcs_path[5:]
        bucket = gcs_path.split('/', 1)[0]
        return bucket
