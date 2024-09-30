#!/usr/bin/python3
import os


class Config(object):
    upload_dir = os.getenv("UPLOAD_DIR", "upload")
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    rkey_pref = os.getenv("RKEY_PREF", "user")
    pdf_name = os.getenv("PDF_NAME", "sar_chart.pdf")
    admin_email = os.getenv("ADMIN_EMAIL", "admin@example-org.com")
    max_metric_header = int(os.getenv("MAX_METRIC_HEADER", 8))
    cols_per_line = int(os.getenv("COLS_PER_LINE", 4))
    max_header_count = int(os.getenv("MAX_HEADER_COUNT", 6))
    file_type = os.getenv("FILE_TYPE", "parquet")