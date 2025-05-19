# MBTI 벡터 예측 모델 정의
import torch
import torch.nn as nn

class MBTIProjector(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(768, 512),
            nn.ReLU(),
            nn.Linear(512, 768)
        )

    def forward(self, x):
        return self.net(x)