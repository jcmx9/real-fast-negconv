"""Thin wrapper around the external exiftool binary (optional at runtime)."""

import logging
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from real_fast_negconv import paths

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 300
# DNG-specific tags (colour, rendering, raw layout, embedded data): ours
# describe our data; a DNG used as input must never add its own (another
# camera matrix, profile, calibration, black/white levels or crop). The JXL*
# tags describe JPEG XL compression of the source's image data and do not
# apply to ours either. Names as exiftool lists them (`exiftool -list`).
DNG_TAGS = (
    "DNGVersion",
    "DNGBackwardVersion",
    "DNGPrivateData",
    "DNGAdobeData",
    "UniqueCameraModel",
    "LocalizedCameraModel",
    "ColorMatrix1",
    "ColorMatrix2",
    "ColorMatrix3",
    "CameraCalibration1",
    "CameraCalibration2",
    "CameraCalibration3",
    "CameraCalibrationSig",
    "ReductionMatrix1",
    "ReductionMatrix2",
    "ReductionMatrix3",
    "ForwardMatrix1",
    "ForwardMatrix2",
    "ForwardMatrix3",
    "CalibrationIlluminant1",
    "CalibrationIlluminant2",
    "CalibrationIlluminant3",
    "IlluminantData1",
    "IlluminantData2",
    "IlluminantData3",
    "AnalogBalance",
    "AsShotNeutral",
    "AsShotWhiteXY",
    "AsShotICCProfile",
    "AsShotPreProfileMatrix",
    "AsShotProfileName",
    "BaselineExposure",
    "BaselineExposureOffset",
    "BaselineNoise",
    "BaselineSharpness",
    "LinearResponseLimit",
    "DefaultBlackRender",
    "NoiseProfile",
    "ProfileName",
    "ProfileCopyright",
    "ProfileEmbedPolicy",
    "ProfileCalibrationSig",
    "ProfileDynamicRange",
    "ProfileGroupName",
    "ProfileType",
    "ProfileGainTableMap",
    "ProfileGainTableMap2",
    "ProfileHueSatMapDims",
    "ProfileHueSatMapData1",
    "ProfileHueSatMapData2",
    "ProfileHueSatMapData3",
    "ProfileHueSatMapEncoding",
    "ProfileLookTableDims",
    "ProfileLookTableData",
    "ProfileLookTableEncoding",
    "ProfileToneCurve",
    "RawToPreviewGain",
    "MakerNoteSafety",
    "OpcodeList1",
    "OpcodeList2",
    "OpcodeList3",
    "ActiveArea",
    "MaskedAreas",
    "BlackLevel",
    "BlackLevelRepeatDim",
    "BlackLevelDeltaH",
    "BlackLevelDeltaV",
    "WhiteLevel",
    "LinearizationTable",
    "ShadowScale",
    "BayerGreenSplit",
    "AntiAliasStrength",
    "ChromaBlurRadius",
    "BestQualityScale",
    "DefaultScale",
    "DefaultCropOrigin",
    "DefaultCropSize",
    "DefaultUserCrop",
    "ColumnInterleaveFactor",
    "RowInterleaveFactor",
    "RawImageDigest",
    "NewRawImageDigest",
    "OriginalRawFileData",
    "OriginalRawFileDigest",
    "RawImageSegmentation",
    "ColorimetricReference",
    "CacheVersion",
    "EnhanceParams",
    "DepthFormat",
    "DepthNear",
    "DepthFar",
    "DepthUnits",
    "DepthMeasureType",
    "SemanticName",
    "SemanticInstanceID",
    "JXLDistance",
    "JXLEffort",
    "JXLDecodeSpeed",
)


def copy_command(executable: Path, source: Path, target: Path) -> list[str]:
    """exiftool arguments copying all metadata except tags we set ourselves."""
    return [
        str(executable),
        "-q",
        "-q",
        "-overwrite_original",
        "-TagsFromFile",
        str(source),
        "-all:all",
        "--MakerNotes",
        "--Orientation",
        "--ImageDescription",
        "--Software",
        "--ImageWidth",
        "--ImageHeight",
        "--XMP-crs:all",
        *(f"--{tag}" for tag in DNG_TAGS),
        "-ThumbnailImage=",
        "-PreviewImage=",
        "-Orientation#=1",
        str(target),
    ]


def private_exiftool_path(platform: str = sys.platform) -> Path:
    """Where the installer puts its own exiftool (app data dir)."""
    data_dir = paths.data_dir()
    name = "exiftool.exe" if platform == "win32" else "exiftool"
    return data_dir / "exiftool" / name


class ExifTool:
    """Read camera names and copy EXIF; silently degrades when not installed."""

    def __init__(self, executable: Path | None) -> None:
        self.executable = executable

    @classmethod
    def locate(cls, configured: Path | None = None) -> "ExifTool":
        """Use the configured binary, else PATH, else the installer's copy."""
        if configured is not None:
            return cls(configured if configured.is_file() else None)
        found = shutil.which("exiftool")
        if found:
            return cls(Path(found))
        private = private_exiftool_path()
        return cls(private if private.is_file() else None)

    @property
    def available(self) -> bool:
        return self.executable is not None

    def camera_name(self, source: Path) -> str | None:
        """'<Make> <Model>' of a file, or None."""
        if self.executable is None:
            return None
        try:
            done = subprocess.run(
                [str(self.executable), "-s3", "-Make", "-Model", str(source)],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=TIMEOUT_SECONDS,
            )
        except Exception as exc:  # best effort: metadata must never fail a file
            log.warning("exiftool could not read %s: %s", source.name, exc)
            return None
        name = " ".join(
            line.strip() for line in done.stdout.splitlines() if line.strip()
        )
        return name or None

    def copy_metadata(self, source: Path, targets: Sequence[Path]) -> bool:
        """Copy metadata from `source` into every target; False if any failed."""
        if self.executable is None:
            return False
        ok = True
        for target in targets:
            try:
                subprocess.run(
                    copy_command(self.executable, source, target),
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=TIMEOUT_SECONDS,
                )
            except Exception as exc:  # best effort: metadata must never fail a file
                log.warning("exiftool failed for %s: %s", target.name, exc)
                ok = False
        return ok
