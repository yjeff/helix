"""重复运行与置信区间聚合。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
import statistics

from .runtime.state import RunResult


def t95(df: int) -> float:
    table = {
        1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
        6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
        16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
        21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
        26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
    }
    return table.get(df, 1.96)


@dataclass(slots=True)
class ReplicaMetric:
    label: str
    mean: float
    half_width: float
    runs: int
    minimum: float
    maximum: float


def _metric(label: str, values: list[float]) -> ReplicaMetric:
    if not values:
        return ReplicaMetric(label, 0.0, 0.0, 0, 0.0, 0.0)
    mean = statistics.mean(values)
    half = 0.0
    if len(values) > 1:
        half = t95(len(values) - 1) * statistics.stdev(values) / math.sqrt(
            len(values))
    return ReplicaMetric(
        label=label,
        mean=mean,
        half_width=half,
        runs=len(values),
        minimum=min(values),
        maximum=max(values),
    )


@dataclass
class ReplicaResult:
    """N 次独立运行的聚合结果。"""

    results: list[RunResult]
    seeds: list[int]
    confidence: float = 0.95

    @property
    def n(self) -> int:
        return len(self.results)

    def _metrics(self, getter) -> dict[str, ReplicaMetric]:
        labels = sorted({
            label for result in self.results for label in getter(result)
        })
        metrics: dict[str, ReplicaMetric] = {}
        for label in labels:
            values = [item for result in self.results
                      for key, item in getter(result).items() if key == label]
            metrics[label] = _metric(label, values)
        return metrics

    def observations(self) -> dict[str, ReplicaMetric]:
        return self._metrics(lambda result: {
            item.label: item.mean
            for item in result.observations if item.count
        })

    def queues(self) -> dict[str, ReplicaMetric]:
        return self._metrics(lambda result: {
            item.label: item.average_length for item in result.queues
        })

    def services(self) -> dict[str, ReplicaMetric]:
        return self._metrics(lambda result: {
            item.activity: item.average_utilization
            for item in result.services
        })

    def resources(self) -> dict[str, ReplicaMetric]:
        return self._metrics(lambda result: {
            item.name: item.average_held for item in result.resources
        })

    def awaits(self) -> dict[str, ReplicaMetric]:
        return self._metrics(lambda result: {
            item.label: item.average_length for item in result.awaits
        })

    def manifest(self) -> dict:
        if not self.results:
            return {}
        manifest = self.results[0].manifest()
        manifest.update({
            "replications": self.n,
            "seeds": list(self.seeds),
            "confidence": self.confidence,
        })
        return manifest

    def write_manifest(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.manifest(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")

    def report(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Helix REPLICA SUMMARY",
            "",
            f"**REPLICATIONS**  {self.n}",
            f"**CONFIDENCE**  {self.confidence:.0%}",
            f"**SEEDS**  {self.seeds[0]}..{self.seeds[-1]}"
            if self.seeds else "**SEEDS**  -",
            "",
        ]
        sections = [
            ("OBSERVATIONS", self.observations()),
            ("QUEUES", self.queues()),
            ("ACTIVITIES", self.services()),
            ("RESOURCES", self.resources()),
            ("WAIT FILES", self.awaits()),
        ]
        for title, metrics in sections:
            if not metrics:
                continue
            lines += [
                f"## {title}",
                "",
                "| LABEL | MEAN | HALF-WIDTH | MIN | MAX | RUNS |",
                "|---|---:|---:|---:|---:|---:|",
            ]
            for item in metrics.values():
                lines.append(
                    f"| {item.label} | {item.mean:.4f} | "
                    f"±{item.half_width:.4f} | {item.minimum:.4f} | "
                    f"{item.maximum:.4f} | {item.runs} |")
            lines.append("")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
