import os
import logging
from dotenv import load_dotenv
from main_tool import run_batch_recommendation

# 로그 설정
logger = logging.getLogger("uvicorn.error")
load_dotenv()

if __name__ == "__main__":
    run_batch_recommendation()