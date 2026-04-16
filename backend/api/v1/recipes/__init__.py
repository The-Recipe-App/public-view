from fastapi import APIRouter

router = APIRouter(prefix="/recipes", tags=["recipes"])

from .create import router as create_router
from .comments import router as comments_router
from .reactions import router as reactions_router
from .feed import router as feeds_router
from .admin import router as admin_router

from .publish import router as publish_router
from .edit import router as edit_router
from .report import router as report_router
from .get import router as get_router
from .seed_dummy_recipes import router as seed_router
from .licenses.licenses import router as licenses_router

router.include_router(create_router)
router.include_router(comments_router)
router.include_router(reactions_router)
router.include_router(feeds_router)
router.include_router(admin_router)

router.include_router(publish_router)
router.include_router(edit_router)
router.include_router(report_router)
router.include_router(get_router)

router.include_router(seed_router)
router.include_router(licenses_router)