"""Random Forest species distribution model — prediction pipeline."""

import logging
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd

from src.models.sdm_result import SDMModelMeta
from src.services.sdm_features import build_feature_matrix
from src.services.sdm_train import FEATURE_COLS, slugify

logger = logging.getLogger(__name__)

_MODELS_DIR = Path("data/models")


# ── public API ────────────────────────────────────────────────────────────────


def predict_species(
    species: str,
    features_df: pd.DataFrame | None = None,
    models_dir: Path | None = None,
) -> pd.DataFrame | None:
    """Load trained model and predict presence probability for every stream segment.

    Returns a DataFrame with columns:
        ogf_id, species, presence_probability, confidence_tier,
        model_version, predicted_at

    Returns None if no trained model exists for this species.
    """
    bundle = _load_bundle(species, models_dir)
    if bundle is None:
        return None
    preprocessor, clf, meta = bundle

    if features_df is None:
        features_df = build_feature_matrix()

    X_tr = preprocessor.transform(features_df[FEATURE_COLS])
    proba = clf.predict_proba(X_tr)[:, 1]

    return pd.DataFrame({
        "ogf_id": features_df["ogf_id"].values,
        "species": species,
        "presence_probability": proba,
        "confidence_tier": meta.confidence_tier,
        "model_version": f"rf-{meta.training_date.strftime('%Y%m%d')}",
        "predicted_at": datetime.now(),
    })


def load_model_metadata(
    species: str, models_dir: Path | None = None
) -> SDMModelMeta | None:
    """Return metadata for a trained model without loading the model itself."""
    mdir = models_dir or _MODELS_DIR
    meta_path = mdir / f"{slugify(species)}_meta.json"
    if not meta_path.exists():
        return None
    return SDMModelMeta.model_validate_json(meta_path.read_text())


def list_trained_species(models_dir: Path | None = None) -> list[str]:
    """Return sorted species names for all models in the models directory."""
    mdir = models_dir or _MODELS_DIR
    if not mdir.exists():
        return []
    result = []
    for meta_path in sorted(mdir.glob("*_meta.json")):
        try:
            meta = SDMModelMeta.model_validate_json(meta_path.read_text())
            result.append(meta.species)
        except Exception:
            logger.warning("Failed to load metadata from %s", meta_path)
    return result


# ── internal ──────────────────────────────────────────────────────────────────


def _load_bundle(
    species: str, models_dir: Path | None = None
) -> tuple | None:
    """Return (preprocessor, clf, meta) or None if no model exists."""
    mdir = models_dir or _MODELS_DIR
    slug = slugify(species)
    model_path = mdir / f"{slug}.joblib"
    meta_path = mdir / f"{slug}_meta.json"

    if not model_path.exists() or not meta_path.exists():
        return None

    bundle = joblib.load(model_path)
    meta = SDMModelMeta.model_validate_json(meta_path.read_text())
    return bundle["preprocessor"], bundle["clf"], meta
