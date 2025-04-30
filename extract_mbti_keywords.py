class ExtractMBTIKeywords:
    def __init__(self):
        self.labels = [
            ['외향적이고 활발한', '내성적이고 조용한'],  # E / I
            ['감각적이고 경험을 중시하는', '직관적이고 상상력이 풍부한'],  # S / N
            ['논리적이고 사고를 중시하는', '감성적이고 공감력이 좋은'],  # T / F
            ['계획적이고 절차를 중시하는', '즉흥적이고 유연한']  # J / P
        ]

    def extract(self, vec):
        keywords = []
        for i, value in enumerate(vec):
            dominant, opposite = self.labels[i]

            if value < 0.2:
                keywords.append(f"매우 {opposite}")
            elif value < 0.4:
                keywords.append(f"다소 {opposite}")
            elif value < 0.6:
                keywords.append(f"{dominant}/{opposite} 균형")
            elif value < 0.8:
                keywords.append(f"다소 {dominant}")
            else:
                keywords.append(f"매우 {dominant}")

        return keywords