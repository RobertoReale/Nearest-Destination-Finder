import logging
import os
import sys

def setup_logger():
    # Create logger
    logger = logging.getLogger("app_logger")
    logger.setLevel(logging.DEBUG)

    # Prevent adding handlers multiple times
    if logger.handlers:
        return logger

    # Create formatters
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create file handler
    file_handler = logging.FileHandler("app.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

def get_logger(name="app_logger"):
    return logging.getLogger("app_logger").getChild(name)
