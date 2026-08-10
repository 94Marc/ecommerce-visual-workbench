import hashlib
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.assets.models import Asset, AssetType, AssetVersion
from app.assets.storage import ObjectStorage
from app.catalog.models import SKU, Product


class AssetNotFoundError(LookupError):
    pass


class AssetInvariantError(ValueError):
    pass


class AssetService:
    def __init__(self, session: Session, storage: ObjectStorage):
        self.session = session
        self.storage = storage

    def create_original(
        self,
        product_id: uuid.UUID,
        content: bytes,
        filename: str,
        mime_type: str,
        *,
        sku_id: uuid.UUID | None = None,
        label: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> Asset:
        self._validate_owner(product_id, sku_id)
        asset = Asset(
            product_id=product_id,
            sku_id=sku_id,
            asset_type=AssetType.ORIGINAL,
            label=label,
        )
        self.session.add(asset)
        self.session.flush()
        self._store_version(asset, content, filename, mime_type, width=width, height=height)
        self.session.commit()
        return self.get_asset(asset.id)

    def create_derived(
        self,
        source_version_id: uuid.UUID,
        asset_type: AssetType,
        content: bytes,
        filename: str,
        mime_type: str,
        *,
        width: int | None = None,
        height: int | None = None,
        label: str | None = None,
    ) -> Asset:
        if asset_type is AssetType.ORIGINAL:
            raise AssetInvariantError("derived assets cannot use ORIGINAL type")
        source = self.session.get(AssetVersion, source_version_id)
        if source is None:
            raise AssetNotFoundError(f"asset version {source_version_id} not found")
        asset = Asset(
            product_id=source.asset.product_id,
            sku_id=source.asset.sku_id,
            asset_type=asset_type,
            label=label,
        )
        self.session.add(asset)
        self.session.flush()
        self._store_version(
            asset,
            content,
            filename,
            mime_type,
            source_version_id=source.id,
            width=width,
            height=height,
        )
        self.session.commit()
        return self.get_asset(asset.id)

    def append_processed_version(
        self,
        asset_id: uuid.UUID,
        source_version_id: uuid.UUID,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> AssetVersion:
        asset = self.get_asset(asset_id)
        if asset.asset_type is AssetType.ORIGINAL:
            raise AssetInvariantError(
                "ORIGINAL assets are immutable and cannot receive processed versions"
            )
        source = self.session.get(AssetVersion, source_version_id)
        if source is None:
            raise AssetNotFoundError(f"asset version {source_version_id} not found")
        version = self._store_version(
            asset, content, filename, mime_type, source_version_id=source_version_id
        )
        self.session.commit()
        self.session.refresh(version)
        return version

    def get_asset(self, asset_id: uuid.UUID) -> Asset:
        statement = select(Asset).where(Asset.id == asset_id).options(selectinload(Asset.versions))
        asset = self.session.scalar(statement)
        if asset is None:
            raise AssetNotFoundError(f"asset {asset_id} not found")
        return asset

    def list_product_assets(self, product_id: uuid.UUID) -> list[Asset]:
        statement = (
            select(Asset)
            .where(Asset.product_id == product_id)
            .options(selectinload(Asset.versions))
            .order_by(Asset.created_at)
        )
        return list(self.session.scalars(statement).unique())

    def _store_version(
        self,
        asset: Asset,
        content: bytes,
        filename: str,
        mime_type: str,
        *,
        source_version_id: uuid.UUID | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> AssetVersion:
        next_version = (
            self.session.scalar(
                select(func.coalesce(func.max(AssetVersion.version_number), 0)).where(
                    AssetVersion.asset_id == asset.id
                )
            )
            + 1
        )
        version_id = uuid.uuid4()
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        key = f"products/{asset.product_id}/assets/{asset.id}/versions/{version_id}.{extension}"
        checksum = hashlib.sha256(content).hexdigest()
        self.storage.put(key, content, mime_type)
        version = AssetVersion(
            id=version_id,
            asset_id=asset.id,
            version_number=next_version,
            object_key=key,
            original_filename=filename,
            mime_type=mime_type,
            byte_size=len(content),
            width=width,
            height=height,
            checksum_sha256=checksum,
            source_version_id=source_version_id,
        )
        self.session.add(version)
        self.session.flush()
        return version

    def _validate_owner(self, product_id: uuid.UUID, sku_id: uuid.UUID | None) -> None:
        if self.session.get(Product, product_id) is None:
            raise AssetNotFoundError(f"product {product_id} not found")
        if sku_id is not None:
            sku = self.session.get(SKU, sku_id)
            if sku is None or sku.product_id != product_id:
                raise AssetInvariantError("SKU must belong to the product")
