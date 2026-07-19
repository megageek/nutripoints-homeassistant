from __future__ import annotations

DOMAIN = "nutri_points"
PLATFORMS = ["sensor", "binary_sensor"]

CONF_API_KEY = "api_key"
CONF_BASE_URL = "base_url"
CONF_POLL_INTERVAL_SECONDS = "poll_interval_seconds"
CONF_VERIFY_SSL = "verify_ssl"
CONF_LOW_POINTS_THRESHOLD = "low_points_threshold"
CONF_ENTRY_ID = "entry_id"

DEFAULT_POLL_INTERVAL_SECONDS = 60
DEFAULT_VERIFY_SSL = True
DEFAULT_LOW_POINTS_THRESHOLD = 5

MIN_POLL_INTERVAL_SECONDS = 15
MAX_POLL_INTERVAL_SECONDS = 3600
MIN_LOW_POINTS_THRESHOLD = 0
MAX_LOW_POINTS_THRESHOLD = 50

RUNTIME_ENDPOINT = "/api/v1/system/runtime"
TODAY_ENDPOINT = "/api/v1/days/today"
READINESS_ENDPOINT = "/api/v1/days/today/readiness"
WEIGHT_OVERVIEW_ENDPOINT = "/api/v1/weight/overview"
HA_EVENTS_ENDPOINT = "/api/v1/integrations/ha/events"
FOOD_LOG_ENDPOINT = "/api/v1/logs/food"
ACTIVITY_LOG_ENDPOINT = "/api/v1/logs/activity"
DRINK_LOG_ENDPOINT = "/api/v1/logs/drinks"
DRINK_SETTINGS_ENDPOINT = "/api/v1/settings/drinks"
WEIGHT_LOG_ENDPOINT = "/api/v1/logs/weight"
STEPS_LOG_ENDPOINT = "/api/v1/logs/steps"

# Keep Home Assistant compatible with adjacent stable server generations so it can
# talk to production while development moves forward.
SUPPORTED_API_CONTRACT_TAGS = ("stable-rw-v1", "stable-rw-v2", "stable-rw-v3", "stable-rw-v4")

AUTOMATION_EVENTS_CAPABILITY = "ha_automation_events_v1"
AUTOMATION_EVENT_NAMES = (
    "meal_food_logged",
    "weigh_in_summary_generated",
    "recipe_batch_label_requested",
)


def automation_event_signal(entry_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_automation_event"


SERVICE_LOG_FOOD = "log_food"
SERVICE_LOG_ACTIVITY = "log_activity"
SERVICE_LOG_DRINK = "log_drink"
SERVICE_LOG_WEIGHT = "log_weight"
SERVICE_SET_STEPS = "set_steps"

ATTR_LAST_ERROR = "last_error"
ATTR_RUNTIME_FAILURE_CLASS = "runtime_failure_class"
ATTR_RUNTIME_FAILURE_COUNT = "runtime_failure_count"
ATTR_RUNTIME_ISSUE_ACTIVE = "runtime_issue_active"

RUNTIME_FAILURE_INVALID_AUTH = "invalid_auth"
RUNTIME_FAILURE_INVALID_HOST = "invalid_host"
RUNTIME_FAILURE_HTTP_API_KEY_FORBIDDEN = "http_api_key_forbidden"
RUNTIME_FAILURE_INCOMPATIBLE_CONTRACT = "incompatible_contract"
RUNTIME_FAILURE_TRANSIENT_TRANSPORT = "transient_transport"

TRANSIENT_RUNTIME_ISSUE_THRESHOLD = 3

SERVICE_ATTR_NAME = "name"
SERVICE_ATTR_DRINK_TYPE_ID = "drink_type_id"
SERVICE_ATTR_DRINK_TYPE_NAME = "drink_type_name"
SERVICE_ATTR_VOLUME_ML = "volume_ml"
SERVICE_ATTR_PRESET_ID = "preset_id"
SERVICE_ATTR_PROTEIN_G = "protein_g"
SERVICE_ATTR_CARBS_G = "carbs_g"
SERVICE_ATTR_FAT_G = "fat_g"
SERVICE_ATTR_FIBER_G = "fiber_g"
SERVICE_ATTR_NUTRITION_ENTRY_MODE = "nutrition_entry_mode"
SERVICE_ATTR_CALORIES_KCAL = "calories_kcal"
SERVICE_ATTR_POINTS = "points"
SERVICE_ATTR_MEAL_TYPE = "meal_type"
SERVICE_ATTR_APPLIES_TO_DATE = "applies_to_date"
SERVICE_ATTR_LOGGED_AT = "logged_at"
SERVICE_ATTR_KCAL = "kcal"
SERVICE_ATTR_WEIGHT_KG = "weight_kg"
SERVICE_ATTR_STEPS = "steps"
SERVICE_ATTR_MODE = "mode"

MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"]
FOOD_NUTRITION_ENTRY_MODES = ["macros", "calories", "points"]
STEP_UPDATE_MODES = ["replace_total", "add_delta"]

SSE_RECONNECT_MIN_SECONDS = 1.0
SSE_RECONNECT_MAX_SECONDS = 10.0
SSE_RECONNECT_JITTER_SECONDS = 0.5
