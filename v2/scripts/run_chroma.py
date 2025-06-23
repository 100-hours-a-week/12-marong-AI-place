from dotenv import load_dotenv
from pathlib import Path
import subprocess, os, time

def run_chroma():
    try:
        dotenv_path = Path(__file__).resolve().parent.parent / ".env"
        load_dotenv(dotenv_path=dotenv_path)

        # 환경 변수 로드
        CHROMA_PORT = os.getenv("CHROMA_PORT")
        CHROMA_PATH = os.getenv("CHROMA_PATH")

        if not CHROMA_PORT or not CHROMA_PATH:
            raise ValueError(" .env 파일에 CHROMA_PORT 또는 CHROMA_PATH가 정의되지 않았습니다.")

        if not os.path.exists(CHROMA_PATH):
            raise FileNotFoundError(f" CHROMA_PATH 경로가 존재하지 않습니다: {CHROMA_PATH}")

        command = f"nohup chroma run --host 0.0.0.0 --port {CHROMA_PORT} --path {CHROMA_PATH} > chroma.log 2>&1 &"
        subprocess.Popen(command, shell=True)

        print(f" ChromaDB가 백그라운드에서 실행되었습니다. (PORT: {CHROMA_PORT})")
        time.sleep(2)

        # 실행 확인 (lsof로 포트 점유 확인)
        print(" 실행된 포트 확인 중...")
        check_command = f"lsof -i :{CHROMA_PORT}"
        os.system(check_command)

    except FileNotFoundError as fe:
        print(fe)
    except Exception as e:
        print(" 예기치 못한 오류 발생:", e)

if __name__ == "__main__":
    run_chroma()