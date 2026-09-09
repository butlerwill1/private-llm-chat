"""Local-only hardware telemetry for the personal Windows application.

This module deliberately collects operational measurements only.  It never
receives a prompt, response, conversation identifier, or HTTP request body.
"""

import asyncio
import csv
import io
import json
import shutil
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import BaseModel


class Metric(BaseModel):
    value: float | int | str | None = None
    unit: str | None = None
    status: str = "ok"
    detail: str | None = None


class LoadedModel(BaseModel):
    name: str
    vram_bytes: int | None = None
    context_length: int | None = None
    expires_at: str | None = None


class SystemMonitorSnapshot(BaseModel):
    sampled_at: datetime
    gpu_name: Metric
    gpu_temperature: Metric
    gpu_utilization: Metric
    gpu_power: Metric
    vram_total: Metric
    vram_used: Metric
    vram_free: Metric
    disk_free: Metric
    disk_total: Metric
    ollama_status: Metric
    cpu_temperature: Metric
    loaded_models: tuple[LoadedModel, ...] = ()


UNAVAILABLE = Metric(status="unavailable")


class LocalSystemMonitor:
    """Samples only local tools and loopback Ollama with bounded waits."""

    def __init__(self, ollama_base_url: str, model_store: Path, cpu_sensor_url: str) -> None:
        self._ollama_base_url = ollama_base_url.rstrip("/").removesuffix("/v1")
        self._model_store = model_store
        self._cpu_sensor_url = cpu_sensor_url

    async def snapshot(self) -> SystemMonitorSnapshot:
        gpu_task = asyncio.create_task(self._gpu_metrics())
        ollama_task = asyncio.create_task(self._loaded_models())
        cpu_task = asyncio.create_task(self._cpu_temperature())
        gpu, loaded_models, cpu_temperature = await asyncio.gather(gpu_task, ollama_task, cpu_task)
        disk_target = self._model_store if self._model_store.exists() else self._model_store.anchor
        disk = shutil.disk_usage(disk_target)
        return SystemMonitorSnapshot(
            sampled_at=datetime.now(UTC),
            gpu_name=gpu.get("name", UNAVAILABLE),
            gpu_temperature=gpu.get("temperature", UNAVAILABLE),
            gpu_utilization=gpu.get("utilization", UNAVAILABLE),
            gpu_power=gpu.get("power", UNAVAILABLE),
            vram_total=gpu.get("total", UNAVAILABLE),
            vram_used=gpu.get("used", UNAVAILABLE),
            vram_free=gpu.get("free", UNAVAILABLE),
            disk_free=Metric(value=disk.free, unit="bytes"),
            disk_total=Metric(value=disk.total, unit="bytes"),
            ollama_status=Metric(
                value="reachable" if loaded_models is not None else "unreachable",
                status="ok" if loaded_models is not None else "unavailable",
            ),
            cpu_temperature=cpu_temperature,
            loaded_models=() if loaded_models is None else loaded_models,
        )

    async def _gpu_metrics(self) -> dict[str, Metric]:
        fields = (
            "name,temperature.gpu,utilization.gpu,power.draw,"
            "memory.total,memory.used,memory.free"
        )
        try:
            process = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                f"--query-gpu={fields}",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=2)
            if process.returncode != 0:
                return {}
            row = next(csv.reader(io.StringIO(stdout.decode("utf-8", "replace"))))
            name, temp, util, power, total, used, free = (part.strip() for part in row)
            return {
                "name": Metric(value=name),
                "temperature": Metric(value=float(temp), unit="°C"),
                "utilization": Metric(value=float(util), unit="%"),
                "power": Metric(value=float(power), unit="W"),
                "total": Metric(value=int(float(total) * 1024 * 1024), unit="bytes"),
                "used": Metric(value=int(float(used) * 1024 * 1024), unit="bytes"),
                "free": Metric(value=int(float(free) * 1024 * 1024), unit="bytes"),
            }
        except (FileNotFoundError, TimeoutError, StopIteration, ValueError, csv.Error):
            return {}

    async def _loaded_models(self) -> tuple[LoadedModel, ...] | None:
        try:
            async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
                response = await client.get(f"{self._ollama_base_url}/api/ps")
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, Mapping) or not isinstance(body.get("models"), list):
                return None
            models: list[LoadedModel] = []
            for item in body["models"]:
                if isinstance(item, Mapping) and isinstance(item.get("name"), str):
                    models.append(
                        LoadedModel(
                            name=item["name"],
                            vram_bytes=item.get("size_vram")
                            if isinstance(item.get("size_vram"), int)
                            else None,
                            context_length=item.get("context_length")
                            if isinstance(item.get("context_length"), int)
                            else None,
                            expires_at=item.get("expires_at")
                            if isinstance(item.get("expires_at"), str)
                            else None,
                        )
                    )
            return tuple(models)
        except (httpx.HTTPError, ValueError):
            return None

    async def _cpu_temperature(self) -> Metric:
        """Read Libre Hardware Monitor's optional loopback JSON tree."""
        try:
            async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
                response = await client.get(self._cpu_sensor_url)
            response.raise_for_status()
            value = self._find_cpu_temperature(response.json())
            return Metric(value=value, unit="°C") if value is not None else self._cpu_unavailable()
        except (httpx.HTTPError, ValueError):
            return self._cpu_unavailable()

    @staticmethod
    def _find_cpu_temperature(value: object) -> float | None:
        if isinstance(value, Mapping):
            name = value.get("Text") or value.get("text") or value.get("Name") or value.get("name")
            reading = value.get("Value") or value.get("value")
            if isinstance(name, str) and "cpu package" in name.lower() and isinstance(reading, str):
                try:
                    return float(reading.replace("°C", "").strip())
                except ValueError:
                    pass
            for child in value.values():
                found = LocalSystemMonitor._find_cpu_temperature(child)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = LocalSystemMonitor._find_cpu_temperature(child)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _cpu_unavailable() -> Metric:
        return UNAVAILABLE.model_copy(
            update={
                "detail": (
                    "Install and enable Libre Hardware Monitor's local web server "
                    "to expose CPU temperature."
                )
            }
        )


class TelemetryStore:
    """Append-only, local SQLite storage for non-sensitive metric samples."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS samples "
                "(sampled_at TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS samples_sampled_at ON samples(sampled_at)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS inference_events "
                "(occurred_at TEXT NOT NULL, payload TEXT NOT NULL)"
            )

    def append(self, snapshot: SystemMonitorSnapshot) -> None:
        with sqlite3.connect(self._path) as connection:
            connection.execute(
                "INSERT INTO samples VALUES (?, ?)",
                (snapshot.sampled_at.isoformat(), snapshot.model_dump_json()),
            )

    def status(self) -> tuple[int, int]:
        with sqlite3.connect(self._path) as connection:
            row = connection.execute("SELECT COUNT(*) FROM samples").fetchone()
            count = 0 if row is None else int(row[0])
        return count, self._path.stat().st_size if self._path.exists() else 0

    def record_inference(self, payload: Mapping[str, object]) -> None:
        """Persist non-sensitive local inference timing and token metadata only."""
        with sqlite3.connect(self._path) as connection:
            connection.execute(
                "INSERT INTO inference_events VALUES (?, ?)",
                (datetime.now(UTC).isoformat(), json.dumps(dict(payload))),
            )

    def export_json(self) -> str:
        with sqlite3.connect(self._path) as connection:
            rows = connection.execute("SELECT payload FROM samples ORDER BY sampled_at").fetchall()
            events = connection.execute(
                "SELECT payload FROM inference_events ORDER BY occurred_at"
            ).fetchall()
        return json.dumps(
            {
                "samples": [json.loads(row[0]) for row in rows],
                "local_inference_events": [json.loads(row[0]) for row in events],
            }
        )
