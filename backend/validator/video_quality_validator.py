"""
Video Quality Validator (pipeline-friendly)

Directly validates visual quality (brightness, clarity, contrast) from MP4 video files.
Works with raw video only (no MCAP required).

Pipeline behavior:
- Does NOT write any JSON to disk.
- Returns a single JSON-serializable dict (or dataclass) that includes:
    - passed: bool  (source of truth for status)
    - status: "good" or "bad"
    - issues/details/stats/messages for UI and metadata

Status rule:
- "good" if passed == True, else "bad"
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Dict, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class ValidationPipelineOutput:
    passed: bool
    status: str                    # "good" or "bad"
    analyze_success: bool
    validate_success: bool
    message: str                   # combined human-readable message
    analyze_message: str
    validate_message: str
    issues: list
    details: dict
    stats: dict                    # percentages (from validation_result["stats"])
    summary: str                   # optional long summary (can be empty)
    video_path: str
    created_at: str                # ISO8601 UTC timestamp


class VideoQualityValidator:
    """Validates visual quality directly from video files."""

    # Quality thresholds (from Safari SDK standards)
    MIN_CLARITY = 20  # Laplacian variance threshold
    MIN_EXPOSURE = 60  # Minimum mean pixel intensity
    MAX_EXPOSURE = 200  # Maximum mean pixel intensity
    MIN_CONTRAST = 25  # Minimum standard deviation

    # Validation thresholds (percentage of frames that can fail)
    MAX_BLURRY_PCT = 10.0
    MAX_EXPOSURE_PCT = 10.0
    MAX_LOW_CONTRAST_PCT = 10.0

    def __init__(self, video_path: str):
        """
        Initialize validator for a video file.

        Args:
            video_path: Path to MP4 video file
        """
        self.video_path = Path(video_path)
        if not self.video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

    def analyze_video_quality(
        self,
        sample_rate: int = 30,
        start_frame: int = 0,
        end_frame: int = None,
        progress_callback=None,
    ) -> Tuple[bool, str, Dict]:
        """
        Analyze visual quality of video frames.

        Args:
            sample_rate: Analyze every Nth frame (default: 30 for ~1 fps sampling at 30fps video)
            start_frame: Start frame index (default: 0)
            end_frame: End frame index (default: None, meaning end of video)
            progress_callback: Optional callback function(current, total) for progress updates

        Returns:
            Tuple of (success, message, stats_dict)
        """
        try:
            cap = cv2.VideoCapture(str(self.video_path))

            if not cap.isOpened():
                return False, "Unable to open video file.", {}

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)

            start_frame_int = int(start_frame)
            if end_frame is not None:
                end_frame_int = int(end_frame)
                actual_end_frame = min(end_frame_int, total_frames)
            else:
                actual_end_frame = total_frames

            # Approx total frames analyzed for progress reporting
            total_to_analyze = (actual_end_frame - start_frame_int + sample_rate - 1) // sample_rate

            stats = {
                "clarity": [],
                "exposure": [],
                "contrast": [],
                "num_images": 0,
                "blurry": 0,
                "under_exposed": 0,
                "over_exposed": 0,
                "low_contrast": 0,
                "total_frames": total_frames,
                "fps": fps,
                "sample_rate": sample_rate,
                "frames_analyzed": total_to_analyze,
            }

            frame_idx = 0
            analyzed_count = 0

            # Skip to start frame if needed
            if start_frame_int > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame_int)
                frame_idx = start_frame_int

            while True:
                if frame_idx >= actual_end_frame:
                    break

                if not cap.grab():
                    break

                if (frame_idx - start_frame_int) % sample_rate == 0:
                    ret, frame = cap.retrieve()
                    if not ret:
                        break

                    try:
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                        # 1) Clarity
                        clarity_score = cv2.Laplacian(gray, cv2.CV_64F).var()
                        stats["clarity"].append(clarity_score)
                        if clarity_score < self.MIN_CLARITY:
                            stats["blurry"] += 1

                        # 2) Exposure
                        mean_intensity = float(gray.mean())
                        stats["exposure"].append(mean_intensity)
                        if mean_intensity < self.MIN_EXPOSURE:
                            stats["under_exposed"] += 1
                        elif mean_intensity > self.MAX_EXPOSURE:
                            stats["over_exposed"] += 1

                        # 3) Contrast
                        contrast = float(gray.std())
                        stats["contrast"].append(contrast)
                        if contrast < self.MIN_CONTRAST:
                            stats["low_contrast"] += 1

                        analyzed_count += 1
                        stats["num_images"] = analyzed_count

                        if progress_callback:
                            progress_callback(analyzed_count, total_to_analyze)

                    except Exception as e:
                        print(f"  ⚠️ Failed to analyze frame {frame_idx}: {e}")

                frame_idx += 1

            cap.release()

            if analyzed_count == 0:
                return False, "No frames were analyzed.", {}

            # Convert lists to numpy arrays for summary calculations
            stats["clarity"] = np.array(stats["clarity"])
            stats["exposure"] = np.array(stats["exposure"])
            stats["contrast"] = np.array(stats["contrast"])

            message = (
                "Quality analysis completed.\n\n"
                f"Analyzed {analyzed_count}/{actual_end_frame - start_frame_int} frames "
                f"(range: {start_frame_int}-{actual_end_frame}, sampling every {sample_rate} frames)"
            )

            return True, message, stats

        except Exception as e:
            return False, f"Error occurred during analysis:\n\n{str(e)}", {}

    def validate_quality(self, stats: Dict) -> Tuple[bool, str, Dict]:
        """
        Validate quality statistics against thresholds.

        Args:
            stats: Stats dictionary from analyze_video_quality

        Returns:
            Tuple of (success, message, validation_result)
        """
        num_images = stats.get("num_images", 0)

        if num_images == 0:
            return False, "No image data available for validation.", {}

        blurry_pct = 100 * stats.get("blurry", 0) / num_images
        under_exposed_pct = 100 * stats.get("under_exposed", 0) / num_images
        over_exposed_pct = 100 * stats.get("over_exposed", 0) / num_images
        low_contrast_pct = 100 * stats.get("low_contrast", 0) / num_images
        exposure_pct = under_exposed_pct + over_exposed_pct

        issues = []
        details = {"clarity": [], "exposure": [], "contrast": []}

        if blurry_pct > self.MAX_BLURRY_PCT:
            issue = f"Clarity: {blurry_pct:.1f}% of frames are blurry (threshold: {self.MAX_BLURRY_PCT}%)"
            issues.append(issue)
            details["clarity"].append(issue)

        if exposure_pct > self.MAX_EXPOSURE_PCT:
            issue = f"Exposure: {exposure_pct:.1f}% of frames have exposure issues (threshold: {self.MAX_EXPOSURE_PCT}%)"
            issues.append(issue)
            details["exposure"].append(issue)

            if under_exposed_pct > 0:
                details["exposure"].append(f"  - Under-exposed: {under_exposed_pct:.1f}%")
            if over_exposed_pct > 0:
                details["exposure"].append(f"  - Over-exposed: {over_exposed_pct:.1f}%")

        if low_contrast_pct > self.MAX_LOW_CONTRAST_PCT:
            issue = f"Contrast: {low_contrast_pct:.1f}% of frames have low contrast (threshold: {self.MAX_LOW_CONTRAST_PCT}%)"
            issues.append(issue)
            details["contrast"].append(issue)

        validation_result = {
            "passed": len(issues) == 0,
            "issues": issues,
            "details": details,
            "stats": {
                "blurry_pct": blurry_pct,
                "exposure_pct": exposure_pct,
                "under_exposed_pct": under_exposed_pct,
                "over_exposed_pct": over_exposed_pct,
                "low_contrast_pct": low_contrast_pct,
            },
        }

        if validation_result["passed"]:
            msg = "✓ Validation passed!\n\nAll visual quality checks meet the standards."
        else:
            msg = "✗ Validation failed\n\nThe following issues were found:\n\n"
            for issue in issues:
                msg += f"  • {issue}\n"
            msg += f"\nA total of {len(issues)} issues were found."

        return True, msg, validation_result

    def get_quality_summary(self, stats: Dict, validation_result: Dict) -> str:
        """
        Get a formatted summary of visual quality metrics.

        NOTE: This uses numpy arrays (clarity/exposure/contrast) from analysis.
        Only call this if you want a long human-readable summary.
        """
        num_images = stats.get("num_images", 0)
        if num_images == 0:
            return "No image data found."

        clarity_arr = stats.get("clarity", np.array([]))
        exposure_arr = stats.get("exposure", np.array([]))
        contrast_arr = stats.get("contrast", np.array([]))

        val_stats = validation_result.get("stats", {})
        blurry_pct = val_stats.get("blurry_pct", 0)
        under_exposed_pct = val_stats.get("under_exposed_pct", 0)
        over_exposed_pct = val_stats.get("over_exposed_pct", 0)
        low_contrast_pct = val_stats.get("low_contrast_pct", 0)
        exposure_pct = under_exposed_pct + over_exposed_pct

        summary = "=" * 60 + "\n"
        summary += "Visual Quality Analysis Summary\n"
        summary += "=" * 60 + "\n\n"

        summary += "Video Information:\n"
        summary += f"  Total frames: {stats.get('total_frames', 0)}\n"
        summary += f"  Frame rate: {stats.get('fps', 0):.2f} fps\n"
        summary += f"  Frames analyzed: {num_images} (sampled every {stats.get('sample_rate', 1)} frames)\n\n"

        summary += "─" * 60 + "\n"
        summary += "Clarity Analysis (Laplacian Variance)\n"
        summary += "─" * 60 + "\n"
        summary += f"  Mean: {np.mean(clarity_arr):.2f}\n"
        summary += f"  Median: {np.median(clarity_arr):.2f}\n"
        summary += f"  Min: {np.min(clarity_arr):.2f}\n"
        summary += f"  Max: {np.max(clarity_arr):.2f}\n"
        summary += f"  Std Dev: {np.std(clarity_arr):.2f}\n"
        summary += f"  Blurry frames: {stats.get('blurry', 0)} ({blurry_pct:.1f}%)\n"
        summary += f"  Rating: {'✓ Excellent' if blurry_pct < 5 else ('⚠ Good' if blurry_pct < 15 else '✗ Needs improvement')}\n"

        summary += "\n" + "─" * 60 + "\n"
        summary += "Exposure Analysis (Mean Pixel Intensity)\n"
        summary += "─" * 60 + "\n"
        summary += f"  Mean: {np.mean(exposure_arr):.2f}\n"
        summary += f"  Median: {np.median(exposure_arr):.2f}\n"
        summary += f"  Min: {np.min(exposure_arr):.2f}\n"
        summary += f"  Max: {np.max(exposure_arr):.2f}\n"
        summary += f"  Std Dev: {np.std(exposure_arr):.2f}\n"
        summary += f"  Under-exposed: {stats.get('under_exposed', 0)} ({under_exposed_pct:.1f}%)\n"
        summary += f"  Over-exposed: {stats.get('over_exposed', 0)} ({over_exposed_pct:.1f}%)\n"
        summary += f"  Rating: {'✓ Excellent' if exposure_pct < 5 else ('⚠ Good' if exposure_pct < 15 else '✗ Needs improvement')}\n"

        summary += "\n" + "─" * 60 + "\n"
        summary += "Contrast Analysis (Pixel Intensity Std Dev)\n"
        summary += "─" * 60 + "\n"
        summary += f"  Mean: {np.mean(contrast_arr):.2f}\n"
        summary += f"  Median: {np.median(contrast_arr):.2f}\n"
        summary += f"  Min: {np.min(contrast_arr):.2f}\n"
        summary += f"  Max: {np.max(contrast_arr):.2f}\n"
        summary += f"  Std Dev: {np.std(contrast_arr):.2f}\n"
        summary += f"  Low contrast: {stats.get('low_contrast', 0)} ({low_contrast_pct:.1f}%)\n"
        summary += f"  Rating: {'✓ Excellent' if low_contrast_pct < 5 else ('⚠ Good' if low_contrast_pct < 15 else '✗ Needs improvement')}\n"

        return summary

    def run(
        self,
        sample_rate: int = 30,
        start_frame: int = 0,
        end_frame: int = None,
        include_summary: bool = False,
        progress_callback=None,
    ) -> ValidationPipelineOutput:
        """
        Runs analysis + validation and returns a single structured output.
        `passed` is the source of truth for status.
        """
        created_at = datetime.now(timezone.utc).isoformat()

        analyze_success, analyze_msg, stats = self.analyze_video_quality(
            sample_rate=sample_rate,
            start_frame=start_frame,
            end_frame=end_frame,
            progress_callback=progress_callback,
        )

        if not analyze_success:
            return ValidationPipelineOutput(
                passed=False,
                status="bad",
                analyze_success=False,
                validate_success=False,
                message=analyze_msg,
                analyze_message=analyze_msg,
                validate_message="",
                issues=[],
                details={},
                stats={},
                summary="",
                video_path=str(self.video_path),
                created_at=created_at,
            )

        validate_success, validate_msg, validation_result = self.validate_quality(stats)

        if not validate_success:
            combined = f"{analyze_msg}\n\n{validate_msg}"
            return ValidationPipelineOutput(
                passed=False,
                status="bad",
                analyze_success=True,
                validate_success=False,
                message=combined,
                analyze_message=analyze_msg,
                validate_message=validate_msg,
                issues=[],
                details={},
                stats={},
                summary="",
                video_path=str(self.video_path),
                created_at=created_at,
            )

        passed = bool(validation_result.get("passed", False))
        status = "good" if passed else "bad"

        summary = ""
        if include_summary:
            try:
                summary = self.get_quality_summary(stats, validation_result)
            except Exception:
                summary = ""

        combined = f"{analyze_msg}\n\n{validate_msg}"

        return ValidationPipelineOutput(
            passed=passed,
            status=status,
            analyze_success=True,
            validate_success=True,
            message=combined,
            analyze_message=analyze_msg,
            validate_message=validate_msg,
            issues=validation_result.get("issues", []),
            details=validation_result.get("details", {}),
            stats=validation_result.get("stats", {}),
            summary=summary,
            video_path=str(self.video_path),
            created_at=created_at,
        )


def validate_video_file(
    video_path: str,
    sample_rate: int = 30,
    start_frame: int = 0,
    end_frame: int = None,
    include_summary: bool = False,
    progress_callback=None,
) -> dict:
    """
    Convenience function for the web backend:
    returns a JSON-serializable dict.

    The frontend/backend should treat `passed` as the source of truth.
    """
    validator = VideoQualityValidator(video_path)
    output = validator.run(
        sample_rate=sample_rate,
        start_frame=start_frame,
        end_frame=end_frame,
        include_summary=include_summary,
        progress_callback=progress_callback,
    )
    return asdict(output)
