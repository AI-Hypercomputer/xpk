"""
Copyright 2025 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

     https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import time
import random
import sys
import math

EPOCHS = 10
STEPS_PER_EPOCH = 40
initial_loss = 2.3
min_loss = 0.15


def get_progress_bar(current: int, total: int, width: int = 30):
  """Creates the Keras-style [==========>.....] bar"""
  progress = current / total
  arrow_len = int(width * progress)
  return "=" * arrow_len + ">" + "." * (width - arrow_len - 1)


print("Train on 60000 samples, validate on 10000 samples")

current_loss = initial_loss
current_acc = 0.10

for epoch in range(1, EPOCHS + 1):
  print(f"Epoch {epoch}/{EPOCHS}")

  epoch_start_time = time.time()

  for step in range(1, STEPS_PER_EPOCH + 1):
    time.sleep(random.uniform(0.02, 0.05))
    decay = math.exp(-0.05 * ((epoch - 1) * STEPS_PER_EPOCH + step))
    target_loss = (initial_loss - min_loss) * decay + min_loss
    noise = random.uniform(-0.1, 0.1) * target_loss
    step_loss = max(0, target_loss + noise)
    step_acc = 1.0 - (step_loss / (initial_loss + 0.5))
    step_acc = max(0, min(0.99, step_acc + random.uniform(-0.02, 0.02)))
    step_duration = (time.time() - epoch_start_time) / step
    if step_duration < 1:
      time_str = f"{int(step_duration * 1000)}ms/step"
    else:
      time_str = f"{step_duration:.1f}s/step"
    bar = get_progress_bar(step, STEPS_PER_EPOCH)

    output = (
        f"\r{step}/{STEPS_PER_EPOCH} "
        f"[{bar}] - "
        f"{time_str} - "
        f"loss: {step_loss:.4f} - "
        f"accuracy: {step_acc:.4f}"
    )

    sys.stdout.write(output)
    sys.stdout.flush()

  val_loss = step_loss * random.uniform(1.0, 1.2)
  val_acc = step_acc * random.uniform(0.9, 0.98)

  print(f" - val_loss: {val_loss:.4f} - val_accuracy: {val_acc:.4f}")
