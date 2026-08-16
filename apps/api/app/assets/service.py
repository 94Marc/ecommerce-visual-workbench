import hashlib
import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.assets.models import Asset, AssetStatus, AssetType, AssetVersion, ContentKind
from app.assets.storage import ObjectStorage
from app.catalog.models import SKU, Product
from app.core.models import utc_now


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
        status: AssetStatus = AssetStatus.REVIEW,
        label: str | None = None,
        asset_slot_id: uuid.UUID | None = None,
        content_kind: ContentKind | None = None,
        contains_demo_data: bool = False,
        demo_data_fields: list[str] | None = None,
    ) -> Asset:
        if asset_type is AssetType.ORIGINAL:
            raise AssetInvariantError("derived assets cannot use ORIGINAL type")
        self._validate_content_kind(asset_type, content_kind)
        source = self.session.get(AssetVersion, source_version_id)
        if source is None:
            raise AssetNotFoundError(f"asset version {source_version_id} not found")
        asset = Asset(
            product_id=source.asset.product_id,
            sku_id=source.asset.sku_id,
            asset_type=asset_type,
            content_kind=content_kind,
            label=label,
            asset_slot_id=asset_slot_id,
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
            status=status,
            contains_demo_data=contains_demo_data,
            demo_data_fields=demo_data_fields,
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
        status: AssetStatus = AssetStatus.DRAFT,
        width: int | None = None,
        height: int | None = None,
        contains_demo_data: bool = False,
        demo_data_fields: list[str] | None = None,
    ) -> AssetVersion:
        asset = self.get_asset(asset_id)
        if asset.asset_type is AssetType.ORIGINAL:
            raise AssetInvariantError(
                "ORIGINAL assets are immutable and cannot receive processed versions"
            )
        source = self.session.get(AssetVersion, source_version_id)
        if source is None:
            raise AssetNotFoundError(f"asset version {source_version_id} not found")
        if source.asset.product_id != asset.product_id:
            raise AssetInvariantError("source version must belong to the same product")
        version = self._store_version(
            asset,
            content,
            filename,
            mime_type,
            source_version_id=source_version_id,
            status=status,
            width=width,
            height=height,
            contains_demo_data=contains_demo_data,
            demo_data_fields=demo_data_fields,
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
            .where(Asset.product_id == product_id, Asset.is_archived.is_(False))
            .options(selectinload(Asset.versions))
            .order_by(Asset.created_at)
        )
        return list(self.session.scalars(statement).unique())

    def update_asset(
        self,
        asset_id: uuid.UUID,
        *,
        label: str | None,
        asset_slot_id: uuid.UUID | None = None,
        content_kind: ContentKind | None = None,
    ) -> Asset:
        asset = self.get_asset(asset_id)
        if asset.asset_type is AssetType.ORIGINAL:
            raise AssetInvariantError("ORIGINAL assets are immutable")
        self._validate_content_kind(asset.asset_type, content_kind)
        if asset_slot_id is not None:
            from app.plans.models import AssetSlot

            slot = self.session.get(AssetSlot, asset_slot_id)
            if slot is None:
                raise AssetNotFoundError(f"asset slot {asset_slot_id} not found")
            if slot.image_type != asset.asset_type.value:
                raise AssetInvariantError("asset type must match the selected asset slot")
            if slot.plan.product_id != asset.product_id:
                raise AssetInvariantError("asset slot belongs to a different product")
        asset.label = label
        asset.asset_slot_id = asset_slot_id
        asset.content_kind = content_kind
        self.session.commit()
        return self.get_asset(asset_id)

    def archive_asset(self, asset_id: uuid.UUID) -> None:
        asset = self.get_asset(asset_id)
        if asset.asset_type is AssetType.ORIGINAL:
            raise AssetInvariantError("ORIGINAL assets cannot be deleted")
        asset.is_archived = True
        asset.archived_at = utc_now()
        self.session.commit()

    def list_versions(self, asset_id: uuid.UUID) -> list[AssetVersion]:
        self.get_asset(asset_id)
        return list(
            self.session.scalars(
                select(AssetVersion)
                .where(AssetVersion.asset_id == asset_id, AssetVersion.is_deleted.is_(False))
                .order_by(AssetVersion.version_number.desc())
            )
        )

    def get_version(self, version_id: uuid.UUID) -> AssetVersion:
        version = self.session.get(AssetVersion, version_id)
        if version is None or version.is_deleted:
            raise AssetNotFoundError(f"asset version {version_id} not found")
        return version

    def update_version_status(self, version_id: uuid.UUID, status: AssetStatus) -> AssetVersion:
        version = self.get_version(version_id)
        if version.asset.asset_type is AssetType.ORIGINAL:
            raise AssetInvariantError("ORIGINAL versions are immutable")
        if status is AssetStatus.APPROVED and version.contains_demo_data:
            raise AssetInvariantError(
                "assets containing demo or placeholder data cannot be production approved"
            )
        allowed = {
            AssetStatus.DRAFT: {AssetStatus.PROCESSING, AssetStatus.REVIEW},
            AssetStatus.PROCESSING: {AssetStatus.REVIEW, AssetStatus.REJECTED},
            AssetStatus.REVIEW: {
                AssetStatus.PROCESSING,
                AssetStatus.APPROVED_FOR_SMOKE_TEST,
                AssetStatus.APPROVED,
                AssetStatus.REJECTED,
            },
            AssetStatus.REJECTED: {AssetStatus.PROCESSING},
            AssetStatus.APPROVED_FOR_SMOKE_TEST: {
                AssetStatus.PROCESSING,
                AssetStatus.APPROVED,
                AssetStatus.REJECTED,
            },
            AssetStatus.APPROVED: set(),
        }
        if status is not version.status and status not in allowed[version.status]:
            raise AssetInvariantError(
                f"cannot transition asset version from {version.status} to {status}"
            )
        version.status = status
        self.session.commit()
        self.session.refresh(version)
        return version

    def delete_version(self, version_id: uuid.UUID) -> None:
        version = self.get_version(version_id)
        if version.asset.asset_type is AssetType.ORIGINAL:
            raise AssetInvariantError("ORIGINAL versions cannot be deleted")
        version.is_deleted = True
        version.deleted_at = utc_now()
        self.session.commit()

    def download_version(self, version_id: uuid.UUID) -> tuple[AssetVersion, bytes]:
        version = self.get_version(version_id)
        return version, self.storage.get(version.object_key)

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
        status: AssetStatus = AssetStatus.DRAFT,
        contains_demo_data: bool = False,
        demo_data_fields: list[str] | None = None,
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
        raw_extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        extension = re.sub(r"[^a-z0-9]", "", raw_extension)[:10] or "bin"
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
            status=status,
            contains_demo_data=contains_demo_data,
            demo_data_fields=sorted(set(demo_data_fields or [])),
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

    @staticmethod
    def _validate_content_kind(
        asset_type: AssetType, content_kind: ContentKind | None
    ) -> None:
        if content_kind is not None and asset_type is not AssetType.DETAIL:
            raise AssetInvariantError("content_kind is only valid for DETAIL assets")
