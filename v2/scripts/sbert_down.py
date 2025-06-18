from sentence_transformers import SentenceTransformer
model = SentenceTransformer("snunlp/KR-SBERT-V40K-klueNLI-augSTS")
model.save("./kr-sbert")