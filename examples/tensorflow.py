import time
import random
import sys
import math

# --- Hyperparameters ---
EPOCHS = 10
STEPS_PER_EPOCH = 40  # How many "batches" per epoch
initial_loss = 2.3    # Typical starting loss for classification
min_loss = 0.15       # The floor (irreducible error)

def get_progress_bar(current, total, width=30):
    """Creates the Keras-style [==========>.....] bar"""
    progress = current / total
    arrow_len = int(width * progress)
    # The arrow is '=' characters with a '>' at the tip, padded by dots or spaces
    bar = '=' * arrow_len + '>' + '.' * (width - arrow_len - 1)
    return bar

print("Train on 60000 samples, validate on 10000 samples")

# Global tracking for realistic curves
current_loss = initial_loss
current_acc = 0.10 # Start with random guess accuracy (10%)

for epoch in range(1, EPOCHS + 1):
    print(f"Epoch {epoch}/{EPOCHS}")
    
    # Reset batch metrics for the new epoch
    epoch_start_time = time.time()
    
    for step in range(1, STEPS_PER_EPOCH + 1):
        # 1. Simulate Calculation Time (simulating a GPU crunching numbers)
        time.sleep(random.uniform(0.02, 0.05))
        
        # 2. Update Metrics (Realistic Drift)
        # Loss decays exponentially over time
        decay = math.exp(-0.05 * ((epoch-1) * STEPS_PER_EPOCH + step))
        target_loss = (initial_loss - min_loss) * decay + min_loss
        
        # Add noise (jitter) that gets smaller as loss gets smaller
        noise = random.uniform(-0.1, 0.1) * target_loss
        step_loss = max(0, target_loss + noise)
        
        # Accuracy is roughly inversely proportional to loss
        # As loss drops to 0, accuracy climbs to 1.0 (100%)
        step_acc = 1.0 - (step_loss / (initial_loss + 0.5))
        step_acc = max(0, min(0.99, step_acc + random.uniform(-0.02, 0.02)))

        # 3. Calculate Step Timing
        step_duration = (time.time() - epoch_start_time) / step
        if step_duration < 1:
            time_str = f"{int(step_duration * 1000)}ms/step"
        else:
            time_str = f"{step_duration:.1f}s/step"

        # 4. Construct the Output String
        # \r returns the cursor to the start of the line (magic for overwriting)
        bar = get_progress_bar(step, STEPS_PER_EPOCH)
        
        output = (
            f"\r{step}/{STEPS_PER_EPOCH} "           # Step Counter
            f"[{bar}] - "                            # Progress Bar
            f"{time_str} - "                         # Timing
            f"loss: {step_loss:.4f} - "              # Loss
            f"accuracy: {step_acc:.4f}"              # Accuracy
        )
        
        # Write to stdout and flush buffer immediately to show update
        sys.stdout.write(output)
        sys.stdout.flush()

    # 5. End of Epoch: Add Validation Metrics
    # Validation is usually slightly worse than training (higher loss, lower acc)
    val_loss = step_loss * random.uniform(1.0, 1.2)
    val_acc = step_acc * random.uniform(0.9, 0.98)
    
    print(f" - val_loss: {val_loss:.4f} - val_accuracy: {val_acc:.4f}")
