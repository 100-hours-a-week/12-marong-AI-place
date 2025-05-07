import subprocess

def run_chroma():
    try:
        subprocess.run([
            "chroma",
            "run",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--path", "/Users/kimss/Documents/marong/chroma_db"
        ], check=True)
    except subprocess.CalledProcessError as e:
        print("Chroma 실행 중 오류 발생:", e)
    except FileNotFoundError:
        print("❌ 'chroma' 명령어를 찾을 수 없습니다. PATH에 등록되어 있는지 확인하세요.")

if __name__ == "__main__":
    run_chroma()