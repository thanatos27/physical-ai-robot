"""DetectionEvent → Observation の変換。"""

from __future__ import annotations

from .models import DetectionEvent, Observation, ObservedObject


class ObservationAdapter:
    def adapt(self, event: DetectionEvent) -> Observation:
        return Observation(
            timestamp=event.timestamp,
            objects=tuple(
                ObservedObject(
                    type=d.class_name,
                    confidence=d.confidence,
                    bounding_box=d.bbox,
                )
                for d in event.detections
            ),
        )
