import asyncio
import concurrent.futures
from core.recommend_place import RecommendPlace

class RecommendPlaceAsync:
    """
    RecommendPlace의 recommend() 메서드를 비동기 환경에서 멀티스레딩으로 호출할 수 있는 래퍼 클래스.
    클래스명과 메서드명은 변경하지 않고 감싸기만 한다.
    """

    def __init__(self, **kwargs):
        # 기존 RecommendPlace 인스턴스를 생성해 내부에 보관
        self._sync_instance = RecommendPlace(**kwargs)
        # 실행용 쓰레드풀 생성 (필요 시 외부 주입 가능)
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

    async def recommend(self, *args, **kwargs):
        """
        RecommendPlace.recommend()를 asyncio 환경에서 비동기로 실행.
        내부적으로 run_in_executor를 사용하여 멀티스레딩 병렬 처리.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: self._sync_instance.recommend(*args, **kwargs)
        )