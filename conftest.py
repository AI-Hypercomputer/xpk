import os
import pytest


@pytest.fixture(autouse=True, scope="session")
def setup_feature_flags():
  os.environ["OPTIONAL_NUM_SLICES"] = "true"
  os.environ["RESERVATIONS_VALIDATION_ENABLED"] = "true"
