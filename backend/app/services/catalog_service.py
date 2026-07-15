from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tenant import TenantContext, tenant_query
from app.models.product import ComboItem, PriceTier, Product
from app.schemas.product import (
    ComboItemIn,
    ComboItemOut,
    PriceTierIn,
    PriceTierOut,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)


class CatalogValidationError(Exception):
    """Raised for business-rule violations the router turns into a 400 with
    the project's standard {"detail", "code"} shape."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _to_product_out(
    product: Product, combo_items: list[ComboItem], price_tiers: list[PriceTier]
) -> ProductOut:
    return ProductOut(
        id=product.id,
        business_id=product.business_id,
        name=product.name,
        description=product.description,
        price=product.price,
        unit=product.unit,
        active=product.active,
        is_combo=product.is_combo,
        image_url=product.image_url,
        sort_order=product.sort_order,
        combo_items=[ComboItemOut.model_validate(ci) for ci in combo_items],
        price_tiers=[PriceTierOut.model_validate(pt) for pt in price_tiers],
    )


async def _combo_items_for(db: AsyncSession, ctx: TenantContext, product_id: int) -> list[ComboItem]:
    return list(
        (
            await db.scalars(
                tenant_query(ComboItem, ctx).where(ComboItem.combo_product_id == product_id)
            )
        ).all()
    )


async def _price_tiers_for(db: AsyncSession, ctx: TenantContext, product_id: int) -> list[PriceTier]:
    return list(
        (
            await db.scalars(
                tenant_query(PriceTier, ctx)
                .where(PriceTier.product_id == product_id)
                .order_by(PriceTier.min_quantity)
            )
        ).all()
    )


async def list_products(
    db: AsyncSession, ctx: TenantContext, *, limit: int, offset: int, active_only: bool = False
) -> tuple[list[ProductOut], int]:
    query = tenant_query(Product, ctx)
    if active_only:
        query = query.where(Product.active.is_(True))

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    products = list(
        (
            await db.scalars(query.order_by(Product.sort_order, Product.id).limit(limit).offset(offset))
        ).all()
    )

    product_ids = [p.id for p in products]
    combo_items_by_product: dict[int, list[ComboItem]] = defaultdict(list)
    price_tiers_by_product: dict[int, list[PriceTier]] = defaultdict(list)
    if product_ids:
        combo_rows = await db.scalars(
            tenant_query(ComboItem, ctx).where(ComboItem.combo_product_id.in_(product_ids))
        )
        for combo_item in combo_rows:
            combo_items_by_product[combo_item.combo_product_id].append(combo_item)

        tier_rows = await db.scalars(
            tenant_query(PriceTier, ctx)
            .where(PriceTier.product_id.in_(product_ids))
            .order_by(PriceTier.min_quantity)
        )
        for tier in tier_rows:
            price_tiers_by_product[tier.product_id].append(tier)

    items = [
        _to_product_out(p, combo_items_by_product[p.id], price_tiers_by_product[p.id]) for p in products
    ]
    return items, total


async def get_product(db: AsyncSession, ctx: TenantContext, product_id: int) -> ProductOut | None:
    product = await db.scalar(tenant_query(Product, ctx).where(Product.id == product_id))
    if product is None:
        return None
    combo_items = await _combo_items_for(db, ctx, product.id)
    price_tiers = await _price_tiers_for(db, ctx, product.id)
    return _to_product_out(product, combo_items, price_tiers)


async def _get_product_or_none(db: AsyncSession, ctx: TenantContext, product_id: int) -> Product | None:
    return await db.scalar(tenant_query(Product, ctx).where(Product.id == product_id))


async def create_product(db: AsyncSession, ctx: TenantContext, data: ProductCreate) -> ProductOut:
    product = Product(business_id=ctx.business_id, **data.model_dump())
    db.add(product)
    await db.flush()
    return _to_product_out(product, [], [])


async def update_product(
    db: AsyncSession, ctx: TenantContext, product_id: int, data: ProductUpdate
) -> ProductOut | None:
    product = await _get_product_or_none(db, ctx, product_id)
    if product is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    await db.flush()
    combo_items = await _combo_items_for(db, ctx, product.id)
    price_tiers = await _price_tiers_for(db, ctx, product.id)
    return _to_product_out(product, combo_items, price_tiers)


async def replace_combo_items(
    db: AsyncSession, ctx: TenantContext, product_id: int, items: list[ComboItemIn]
) -> list[ComboItemOut] | None:
    """Returns None if the product itself doesn't exist (router -> 404).
    Raises CatalogValidationError for business-rule violations (router -> 400).
    """
    product = await _get_product_or_none(db, ctx, product_id)
    if product is None:
        return None
    if not product.is_combo:
        raise CatalogValidationError("not_a_combo", "El producto no esta marcado como combo")

    component_ids = [item.component_product_id for item in items]
    if len(component_ids) != len(set(component_ids)):
        raise CatalogValidationError(
            "duplicate_component", "Un mismo producto componente aparece mas de una vez"
        )
    if product.id in component_ids:
        raise CatalogValidationError("self_reference", "Un combo no puede componerse de si mismo")

    if component_ids:
        components = list(
            (
                await db.scalars(tenant_query(Product, ctx).where(Product.id.in_(component_ids)))
            ).all()
        )
        found_ids = {c.id for c in components}
        missing = set(component_ids) - found_ids
        if missing:
            raise CatalogValidationError(
                "component_not_found", f"Producto(s) componente no encontrados: {sorted(missing)}"
            )
        nested_combos = [c.id for c in components if c.is_combo]
        if nested_combos:
            raise CatalogValidationError(
                "nested_combo", "Un combo no puede tener otro combo como componente"
            )

    existing = await _combo_items_for(db, ctx, product.id)
    for row in existing:
        await db.delete(row)
    await db.flush()

    new_rows = [
        ComboItem(
            business_id=ctx.business_id,
            combo_product_id=product.id,
            component_product_id=item.component_product_id,
            quantity=item.quantity,
        )
        for item in items
    ]
    db.add_all(new_rows)
    await db.flush()
    return [ComboItemOut.model_validate(row) for row in new_rows]


async def replace_price_tiers(
    db: AsyncSession, ctx: TenantContext, product_id: int, tiers: list[PriceTierIn]
) -> list[PriceTierOut] | None:
    product = await _get_product_or_none(db, ctx, product_id)
    if product is None:
        return None

    min_quantities = [tier.min_quantity for tier in tiers]
    if len(min_quantities) != len(set(min_quantities)):
        raise CatalogValidationError(
            "duplicate_min_quantity", "No puede haber dos tramos con el mismo min_quantity"
        )

    existing = await _price_tiers_for(db, ctx, product.id)
    for row in existing:
        await db.delete(row)
    await db.flush()

    new_rows = [
        PriceTier(
            business_id=ctx.business_id,
            product_id=product.id,
            min_quantity=tier.min_quantity,
            unit_price=tier.unit_price,
        )
        for tier in tiers
    ]
    db.add_all(new_rows)
    await db.flush()
    return [PriceTierOut.model_validate(row) for row in new_rows]
