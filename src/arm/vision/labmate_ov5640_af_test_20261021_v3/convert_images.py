#!/usr/bin/env python3
import json
import os
import sys
import cv2

run = sys.argv[1]
metrics = {}
for name in ('before', 'after'):
    source = os.path.join(run, name + '.ppm')
    if not os.path.exists(source):
        continue
    image = cv2.imread(source)
    if image is None:
        raise RuntimeError('Cannot decode ' + source)
    target = os.path.join(run, name + '.png')
    if not cv2.imwrite(target, image):
        raise RuntimeError('Cannot write ' + target)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    center = gray[h // 4:3 * h // 4, w // 4:3 * w // 4]
    metrics[name] = {'laplacian_variance': float(cv2.Laplacian(gray, cv2.CV_64F).var()),
                     'center_laplacian_variance': float(cv2.Laplacian(center, cv2.CV_64F).var())}
    print('PNG=' + target)
    if name == 'after':
        photo = os.path.join(run, 'photo.jpg')
        if not cv2.imwrite(photo, image, [cv2.IMWRITE_JPEG_QUALITY, 95]):
            raise RuntimeError('Cannot write ' + photo)
        print('PHOTO_SAVED=' + photo)
with open(os.path.join(run, 'sharpness.json'), 'w') as output:
    json.dump(metrics, output, indent=2)
print('SHARPNESS=' + json.dumps(metrics))
