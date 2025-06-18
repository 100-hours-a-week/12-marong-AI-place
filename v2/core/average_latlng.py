import math

class AverageLatLng:
    # 위도/경도를 라디안으로 변환    
    def __init__(self, lat1, lon1, lat2, lon2):
      self.lat1, self.lon1, self.lat2, self.lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    def loc_to_vec(self):
      # 위도/경도를 3D 좌표로 변환
      x1, y1, z1 = math.cos(self.lat1)*math.cos(self.lon1), math.cos(self.lat1)*math.sin(self.lon1), math.sin(self.lat1)
      x2, y2, z2 = math.cos(self.lat2)*math.cos(self.lon2), math.cos(self.lat2)*math.sin(self.lon2), math.sin(self.lat2)

      # 평균 벡터
      self.x, self.y, self.z = (x1 + x2) / 2, (y1 + y2) / 2, (z1 + z2) / 2

    def get(self):
      # 다시 위도/경도로 변환
      lon = math.atan2(self.y, self.x)
      hyp = math.sqrt(self.x * self.x + self.y * self.y)
      lat = math.atan2(self.z, hyp)

      # 라디안 → 도(degree)
      return math.degrees(lat), math.degrees(lon)