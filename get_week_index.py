from datetime import datetime, timedelta

class GetWeekIndex:
    def __init__(self, target_date, base_date):
        self.target_date = target_date
        self.base_date = base_date

    def get(self):
        delta_days = (self.target_date - self.base_date).days
        return (delta_days // 7) + 1 if delta_days >= 0 else 0