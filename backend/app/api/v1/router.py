from fastapi import APIRouter

from app.api.v1 import auth, payment_methods, products, users

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(products.router)
router.include_router(payment_methods.router)
