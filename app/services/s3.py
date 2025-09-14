"""AWS S3 service for downloading documents."""

import tempfile
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from app.core.config import settings
from app.core.exceptions import VectorStoreError
from app.core.logging import setup_logger

logger = setup_logger(__name__)


class S3Service:
    """Service for interacting with AWS S3."""

    def __init__(self):
        """Initialize S3 service."""
        self.region_name = settings.S3_REGION
        self._client = None

    @property
    def client(self):
        """Get or create S3 client."""
        if self._client is None:
            try:
                self._client = boto3.client("s3", region_name=self.region_name)
            except NoCredentialsError:
                raise VectorStoreError(
                    "AWS credentials not found. Please configure AWS credentials."
                )
        return self._client

    def parse_s3_url(self, s3_url: str) -> Tuple[str, str]:
        """
        Parse S3 URL to extract bucket and key.

        Args:
            s3_url: S3 URL in format s3://bucket/key or s3://bucket/path/to/key

        Returns:
            Tuple of (bucket_name, object_key)

        Raises:
            VectorStoreError: If URL format is invalid
        """
        try:
            parsed = urlparse(s3_url)
            if parsed.scheme != "s3":
                raise VectorStoreError(
                    f"Invalid S3 URL format: {s3_url}. Must start with 's3://'"
                )

            bucket = parsed.netloc
            key = parsed.path.lstrip("/")

            if not bucket:
                raise VectorStoreError(f"No bucket specified in S3 URL: {s3_url}")
            if not key:
                raise VectorStoreError(f"No object key specified in S3 URL: {s3_url}")

            return bucket, key

        except Exception as e:
            raise VectorStoreError(f"Failed to parse S3 URL '{s3_url}': {str(e)}")

    def construct_s3_url(self, knowledge_id: str, filename: str) -> str:
        """
        Construct S3 URL from knowledge ID and filename.

        Args:
            knowledge_id: Knowledge base identifier (UUID)
            filename: Name of the file

        Returns:
            S3 URL in format s3://bucket/knowledge/knowledge_id/filename
        """
        return f"s3://{settings.S3_BUCKET_NAME}/knowledge/{knowledge_id}/{filename}"

    def extract_filename_from_s3_path(self, s3_url: str) -> str:
        """
        Extract filename from S3 path.

        Args:
            s3_url: S3 URL

        Returns:
            Filename
        """
        try:
            _, key = self.parse_s3_url(s3_url)
            return Path(key).name
        except Exception as e:
            raise VectorStoreError(
                f"Failed to extract filename from S3 path '{s3_url}': {str(e)}"
            )

    async def download_file(
        self, s3_url: str, local_path: Optional[Path] = None
    ) -> Path:
        """
        Download a file from S3 to local storage.

        Args:
            s3_url: S3 URL of the file to download
            local_path: Optional local path to save the file. If not provided, uses temp directory

        Returns:
            Path to the downloaded file

        Raises:
            VectorStoreError: If download fails
        """
        bucket, key = self.parse_s3_url(s3_url)

        # Determine local file path
        if local_path is None:
            # Create temp file with same extension as S3 object
            filename = Path(key).name
            suffix = Path(filename).suffix
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            local_path = Path(temp_file.name)
            temp_file.close()
        else:
            local_path = Path(local_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            logger.info(f"Downloading file from S3: {s3_url} -> {local_path}")

            # Download file from S3
            response = self.client.get_object(Bucket=bucket, Key=key)

            # Write to local file
            with open(local_path, "wb") as f:
                for chunk in response["Body"].iter_chunks(chunk_size=8192):
                    f.write(chunk)

            # Verify file was downloaded
            if not local_path.exists():
                raise VectorStoreError(f"File was not created at {local_path}")

            file_size = local_path.stat().st_size
            logger.info(
                f"Successfully downloaded file: {local_path} ({file_size} bytes)"
            )

            return local_path

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "NoSuchBucket":
                raise VectorStoreError(f"S3 bucket does not exist: {bucket}")
            elif error_code == "NoSuchKey":
                raise VectorStoreError(f"S3 object does not exist: {s3_url}")
            elif error_code == "AccessDenied":
                raise VectorStoreError(f"Access denied to S3 object: {s3_url}")
            else:
                raise VectorStoreError(f"S3 client error: {str(e)}")
        except Exception as e:
            # Clean up temp file if download failed
            if local_path and local_path.exists():
                try:
                    local_path.unlink()
                except:
                    pass
            raise VectorStoreError(f"Failed to download file from S3: {str(e)}")

    def is_s3_url(self, url: str) -> bool:
        """
        Check if a URL is an S3 URL.

        Args:
            url: URL to check

        Returns:
            True if URL is an S3 URL, False otherwise
        """
        try:
            parsed = urlparse(url)
            return parsed.scheme == "s3"
        except:
            return False

    async def file_exists(self, s3_url: str) -> bool:
        """
        Check if a file exists in S3.

        Args:
            s3_url: S3 URL of the file to check

        Returns:
            True if file exists, False otherwise
        """
        try:
            bucket, key = self.parse_s3_url(s3_url)
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise VectorStoreError(f"Error checking if S3 file exists: {str(e)}")
        except Exception as e:
            raise VectorStoreError(f"Error checking if S3 file exists: {str(e)}")

    def cleanup_temp_file(self, file_path: Path) -> None:
        """
        Clean up temporary file.

        Args:
            file_path: Path to the temporary file to clean up
        """
        try:
            if file_path and file_path.exists():
                file_path.unlink()
                logger.debug(f"Cleaned up temporary file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temporary file {file_path}: {str(e)}")


# Global instance
s3_service = S3Service()
