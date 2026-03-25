from .health import router as health_router
from .start import router as start_router
from .onboarding import router as onboarding_router
from .panel_dm import router as panel_dm_router
from .whitelist import router as whitelist_router
from .stopwords import router as stopwords_router
from .log_actions import router as log_actions_router
from .log_setup import router as log_setup_router
from .moderation import router as moderation_router

routers = [
    health_router,
    start_router,
    onboarding_router,
    panel_dm_router,
    whitelist_router,
    stopwords_router,
    log_actions_router,
    log_setup_router,
    moderation_router,
]
