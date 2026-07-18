import os

# Database configurations (pointing to local TimescaleDB Docker container)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "your_secure_password")
DB_NAME = os.getenv("DB_NAME", "postgres")

# Target Scraper configurations
ZEPTO_API_URL = "https://api.zepto.com/lms/api/v2/get_page"
