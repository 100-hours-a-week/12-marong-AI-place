from dotenv import load_dotenv
import subprocess, os

def run_chroma():
    try:
        load_dotenv()
        
        # 환경 변수 로드
        CHROMA_PORT = os.getenv("CHROMA_PORT")
        CHROMA_PATH = os.getenv("CHROMA_PATH")

        command = f"nohup chroma run --host 0.0.0.0 --port {CHROMA_PORT} --path {CHROMA_PATH} > chroma.log 2>&1 &"
        subprocess.Popen(command, shell=True)
        print("ChromaDB가 백그라운드에서 실행되었습니다.")

    except FileNotFoundError:
        print("❌ 'chroma' 명령어를 찾을 수 없습니다. PATH에 등록되어 있는지 확인하세요.")
    except Exception as e:
        print("⚠️ 예기치 못한 오류 발생:", e)

if __name__ == "__main__":
    run_chroma()