from dotenv import load_dotenv
import subprocess, os

def run_chroma():
    try:
        load_dotenv()
        
        # ChromaDB 환경 변수 로드
        CHROMA_PORT = os.getenv("CHROMA_PORT")
        CHROMA_PATH = os.getenv("CHROMA_PATH")
        
        subprocess.run([
            "chroma",
            "run",
            "--host", "0.0.0.0",
            "--port", f"{CHROMA_PORT}",
            "--path", f"{CHROMA_PATH}"
        ], check=True)
    except subprocess.CalledProcessError as e:
        print("Chroma 실행 중 오류 발생:", e)
    except FileNotFoundError:
        print("❌ 'chroma' 명령어를 찾을 수 없습니다. PATH에 등록되어 있는지 확인하세요.")

if __name__ == "__main__":
    run_chroma()