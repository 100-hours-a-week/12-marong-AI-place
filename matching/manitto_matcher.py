import random
from typing import List, Dict, Tuple, Optional, FrozenSet


class ManittoMatcher:
    def __init__(self, user_ids: List[int], previous_matches: Dict[FrozenSet[int], int], current_week: int):
        self.user_ids = user_ids
        self.previous_matches = previous_matches
        self.current_week = current_week

    def assign_weighted_pairs(self) -> Tuple[List[Tuple[int, int]], Optional[int]]:
        users = self.user_ids[:]

        excluded = None
        if len(users) % 2 == 1:
            excluded = users.pop()
            
        random.shuffle(users)

        pairs = []
        available = set(users)

        while len(available) >= 2:
            u1 = available.pop()
            candidates = list(available)

            weights = []
            for u2 in candidates:
                pair = frozenset([u1, u2])
                if pair in self.previous_matches:
                    week_matched = self.previous_matches[pair]
                    weeks_ago = self.current_week - week_matched
                    # 최근일수록 낮은 확률, 오래전일수록 높은 확률
                    weight = min(1.0, 0.1 + (weeks_ago * 0.05))  # 최소 0.1 ~ 최대 1.0
                else:
                    weight = 1.0  # 이전에 한 번도 안 만난 조합은 최대 확률

                weights.append(weight)

            if sum(weights) == 0:
                u2 = random.choice(candidates)
            else:
                u2 = random.choices(candidates, weights=weights, k=1)[0]

            available.remove(u2)
            pairs.append((u1, u2))

        return pairs, excluded