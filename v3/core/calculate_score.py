class CalculateScore:
    def __init__(self, rating, distance, similarity, max_distance, weights):
        self.rating = rating
        self.distance = distance
        self.similarity = similarity
        self.max_distance = max_distance
        self.weights = weights

    def calculate(self):
        rating_score = max(0, (self.rating - 2.5))  # normalize rating
        distance_score = max(0, (self.max_distance - self.distance) / self.max_distance)

        final_score = (
            rating_score * self.weights["rating"] +
            distance_score * self.weights["distance"] +
            self.similarity * self.weights["similarity"]
        )
        return final_score