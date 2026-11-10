"""Ghi log ứng dụng + log lỗi, xoay vòng mỗi ngày và giữ tối thiểu 30 ngày (yêu cầu phi chức năng)."""
import logging
import os
from logging.handlers import TimedRotatingFileHandler


def configure_logging(app):
    if app.testing:
        return
    log_dir = app.config["LOG_DIR"]
    os.makedirs(log_dir, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    days = app.config["LOG_RETENTION_DAYS"]

    app_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "app.log"), when="midnight", backupCount=days, encoding="utf-8")
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(fmt)

    error_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "error.log"), when="midnight", backupCount=days, encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)

    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(app_handler)
    app.logger.addHandler(error_handler)
