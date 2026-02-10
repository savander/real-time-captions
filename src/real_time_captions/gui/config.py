from pathlib import Path
from typing import Final, TypedDict

from platformdirs import user_config_dir

APP_NAME = "AutoCaptions"
APP_AUTHOR = "Codrig"

# Window Settings
DEFAULT_SIZE: Final = (800, 200)
DEFAULT_FONT_SIZE: Final = 30
DEFAULT_MAX_BATCHES: Final = 4
DEFAULT_BG_OPACITY: Final = 180
FONT_FAMILY: Final = "Arial"

# Logic Settings
MODULE_NAME: Final = "real_time_captions"
CONFIG_DIR: Final = Path(user_config_dir(APP_NAME, APP_AUTHOR))
CONFIG_FILE: Final = CONFIG_DIR / "window_config.json"

# UI Component General Settings
BUTTON_SIZE: Final = 30
CLOSE_BUTTON_HOVER_COLOR: Final = "#FF5F57"
CLEAR_BUTTON_HOVER_COLOR: Final = "#FFAB40"

# Colors
TEXT_GRADIENT: Final = ["#FFFFFF", "#F0F0F0", "#D9D9D9", "#B3B3B3", "#999999"]


class WordSegment(TypedDict):
    text: str
    batch_id: int
