"""EC2 inference adapter for the VISA Lab course recognition model.

Adapted from https://github.com/nehavadnere/CSE546-FALL-2025/blob/model/face_recognition.py
"""
__copyright__ = "Copyright 2025, VISA Lab"
__license__ = "MIT"

from functools import lru_cache
from pathlib import Path
import argparse

import torch
from PIL import Image
from facenet_pytorch import MTCNN, InceptionResnetV1

DEFAULT_DATA_PATH = Path(__file__).with_name('data.pt')


@lru_cache(maxsize=1)
def _models():
    return (MTCNN(image_size=240, margin=0, min_face_size=20),
            InceptionResnetV1(pretrained='vggface2').eval())


@lru_cache(maxsize=4)
def _references(path):
    embeddings, names = torch.load(path, map_location='cpu', weights_only=True)
    if not len(names) or len(embeddings) != len(names):
        raise ValueError('Reference embeddings and names must be nonempty and aligned')
    embeddings = [torch.as_tensor(e, dtype=torch.float32).reshape(-1) for e in embeddings]
    if any(e.numel() != 512 or not torch.isfinite(e).all() for e in embeddings):
        raise ValueError('Reference embeddings must contain 512 finite values')
    return embeddings, names


def face_match(img_path, data_path=None):
    """Return (nearest identity, distance), or ('No-Face', infinity)."""
    path = str(Path(data_path).resolve() if data_path is not None else DEFAULT_DATA_PATH)
    embeddings, names = _references(path)
    detector, recognizer = _models()
    with Image.open(img_path) as image:
        image = image.convert('RGB')
        with torch.inference_mode():
            face, _ = detector(image, return_prob=True)
            if face is None:
                return 'No-Face', float('inf')
            embedding = recognizer(face.unsqueeze(0)).reshape(-1)
            distances = [torch.dist(embedding, reference).item() for reference in embeddings]
    index = min(range(len(distances)), key=distances.__getitem__)
    return names[index], distances[index]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run local course face recognition')
    parser.add_argument('image')
    parser.add_argument('--data', default=str(DEFAULT_DATA_PATH))
    args = parser.parse_args()
    print(face_match(args.image, args.data)[0])
