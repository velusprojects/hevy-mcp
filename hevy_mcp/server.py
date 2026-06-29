from __future__ import annotations

import logging
import os

import httpx

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from hevy_mcp.utils.hevy import hevy_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

PORT = int(os.environ.get("PORT", 8000))

mcp = FastMCP("Hevy MCP", host="0.0.0.0", port=PORT)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ExerciseSet(BaseModel):
    index: int
    set_type: str = Field(description="e.g. normal, warmup, failure, dropset")
    weight_kg: float | None = None
    reps: int | None = None
    distance_meters: float | None = None
    duration_seconds: int | None = None
    rpe: float | None = None


class Exercise(BaseModel):
    index: int
    title: str
    exercise_template_id: str
    notes: str = ""
    sets: list[ExerciseSet] = []


class WorkoutSummary(BaseModel):
    id: str
    title: str
    start_time: str
    end_time: str


class WorkoutDetail(BaseModel):
    id: str
    title: str
    description: str
    start_time: str
    end_time: str
    exercises: list[Exercise]


class WorkoutCount(BaseModel):
    count: int


class RoutineSummary(BaseModel):
    id: str
    title: str
    folder_id: int | None = None


class RoutineDetail(BaseModel):
    id: str
    title: str
    folder_id: int | None = None
    exercises: list[Exercise]


class ExerciseTemplate(BaseModel):
    id: str
    title: str
    type: str
    primary_muscle_group: str
    secondary_muscle_groups: list[str] = []
    is_custom: bool


class ExerciseTemplateList(BaseModel):
    templates: list[ExerciseTemplate]
    page: int
    page_count: int


class ActionResult(BaseModel):
    success: bool
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_set(s: dict, idx: int) -> ExerciseSet:
    return ExerciseSet(
        index=s.get("index", idx),
        set_type=s.get("set_type", s.get("type", "normal")),
        weight_kg=s.get("weight_kg"),
        reps=s.get("reps"),
        distance_meters=s.get("distance_meters"),
        duration_seconds=s.get("duration_seconds"),
        rpe=s.get("rpe"),
    )


def _parse_exercise(e: dict, idx: int) -> Exercise:
    return Exercise(
        index=e.get("index", idx),
        title=e.get("title", ""),
        exercise_template_id=e.get("exercise_template_id", ""),
        notes=e.get("notes") or "",
        sets=[_parse_set(s, i) for i, s in enumerate(e.get("sets", []))],
    )


def _build_exercise_payload(
    exercises: list[dict], for_routine: bool = False
) -> list[dict]:
    """Convert user-provided exercise dicts to Hevy API format.

    Hevy's routine and workout endpoints accept different set fields:
    workout sets take ``rpe``; routine sets take ``custom_metric`` and reject
    ``rpe`` entirely. Pass ``for_routine=True`` when building a routine.
    """
    result = []
    for ex in exercises:
        entry = {
            "exercise_template_id": ex["exercise_template_id"],
            "superset_id": ex.get("superset_id"),
            "notes": ex.get("notes", ""),
            "sets": [],
        }
        if for_routine:
            entry["rest_seconds"] = ex.get("rest_seconds")
        for s in ex.get("sets", []):
            set_entry = {
                "type": s.get("type", "normal"),
                "weight_kg": s.get("weight_kg"),
                "reps": s.get("reps"),
                "distance_meters": s.get("distance_meters"),
                "duration_seconds": s.get("duration_seconds"),
            }
            if for_routine:
                set_entry["custom_metric"] = s.get("custom_metric")
            else:
                set_entry["rpe"] = s.get("rpe")
            entry["sets"].append(set_entry)
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@mcp.custom_route("/health_check", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Phase 1 — Read tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_workout_count() -> WorkoutCount:
    """Get the total number of logged workouts."""
    data = await hevy_client.get("/workouts/count")
    return WorkoutCount(count=data.get("workout_count", 0))


@mcp.tool()
async def list_workouts(
    page: int = Field(default=1, description="Page number (1-indexed)"),
    page_size: int = Field(default=5, description="Number of workouts per page"),
) -> list[WorkoutSummary]:
    """List workouts with pagination."""
    data = await hevy_client.get("/workouts", params={"page": page, "pageSize": page_size})
    return [
        WorkoutSummary(
            id=w["id"],
            title=w.get("title", ""),
            start_time=w.get("start_time", ""),
            end_time=w.get("end_time", ""),
        )
        for w in data.get("workouts", [])
    ]


@mcp.tool()
async def get_workout(
    workout_id: str = Field(description="The workout ID to retrieve"),
) -> WorkoutDetail:
    """Get full details of a specific workout."""
    data = await hevy_client.get(f"/workouts/{workout_id}")
    w = data
    return WorkoutDetail(
        id=w["id"],
        title=w.get("title", ""),
        description=w.get("description", ""),
        start_time=w.get("start_time", ""),
        end_time=w.get("end_time", ""),
        exercises=[_parse_exercise(e, i) for i, e in enumerate(w.get("exercises", []))],
    )


@mcp.tool()
async def list_routines(
    page: int = Field(default=1, description="Page number (1-indexed)"),
    page_size: int = Field(default=5, description="Number of routines per page"),
) -> list[RoutineSummary]:
    """List routines with pagination."""
    data = await hevy_client.get("/routines", params={"page": page, "pageSize": page_size})
    return [
        RoutineSummary(
            id=r["id"],
            title=r.get("title", ""),
            folder_id=r.get("folder_id"),
        )
        for r in data.get("routines", [])
    ]


@mcp.tool()
async def get_routine(
    routine_id: str = Field(description="The routine ID to retrieve"),
) -> RoutineDetail:
    """Get full details of a specific routine."""
    data = await hevy_client.get(f"/routines/{routine_id}")
    r = data.get("routine", data)
    return RoutineDetail(
        id=r["id"],
        title=r.get("title", ""),
        folder_id=r.get("folder_id"),
        exercises=[_parse_exercise(e, i) for i, e in enumerate(r.get("exercises", []))],
    )


@mcp.tool()
async def search_exercises(
    query: str = Field(description="Search query for exercise templates"),
    page: int = Field(default=1, description="Page number (1-indexed)"),
) -> ExerciseTemplateList:
    """Search exercise templates by name."""
    # Hevy API has no search param, so pull the FULL template library across
    # all pages and filter the whole set — not just one page (which only ever
    # matched titles that happened to fall on that page).
    all_templates = await hevy_client.get_paginated(
        "/exercise_templates",
        params={"pageSize": 100},
    )
    query_lower = query.lower()
    templates = [
        ExerciseTemplate(
            id=t["id"],
            title=t["title"],
            type=t.get("type", ""),
            primary_muscle_group=t.get("primary_muscle_group", ""),
            secondary_muscle_groups=t.get("secondary_muscle_groups", []),
            is_custom=t.get("is_custom", False),
        )
        for t in all_templates
        if query_lower in t.get("title", "").lower()
    ]
    # All matches are returned in one shot now, so pagination is collapsed.
    return ExerciseTemplateList(
        templates=templates,
        page=1,
        page_count=1,
    )


# ---------------------------------------------------------------------------
# Phase 2 — Write tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_workout(
    title: str = Field(description="Title for the workout"),
    start_time: str = Field(description="ISO 8601 start time (e.g. 2024-01-15T10:00:00Z)"),
    end_time: str = Field(description="ISO 8601 end time (e.g. 2024-01-15T11:00:00Z)"),
    description: str = Field(default="", description="Optional workout description"),
    exercises: list[dict] = Field(
        description=(
            "List of exercises. Each dict needs: exercise_template_id (str), "
            "sets (list of dicts with type, weight_kg, reps, etc.), "
            "optional: notes (str), superset_id (int)"
        )
    ),
) -> ActionResult:
    """Log a new workout."""
    payload = {
        "workout": {
            "title": title,
            "description": description,
            "start_time": start_time,
            "end_time": end_time,
            "exercises": _build_exercise_payload(exercises),
        }
    }
    try:
        data = await hevy_client.post("/workouts", json=payload)
        workout_id = data.get("id", "unknown")
        return ActionResult(success=True, message=f"Workout created: {workout_id}")
    except Exception as exc:
        return ActionResult(success=False, message=str(exc))


@mcp.tool()
async def update_workout(
    workout_id: str = Field(description="ID of the workout to update"),
    title: str = Field(description="Updated title"),
    start_time: str = Field(description="ISO 8601 start time"),
    end_time: str = Field(description="ISO 8601 end time"),
    description: str = Field(default="", description="Optional workout description"),
    exercises: list[dict] = Field(
        description=(
            "Updated list of exercises. Each dict needs: exercise_template_id (str), "
            "sets (list of dicts with type, weight_kg, reps, etc.), "
            "optional: notes (str), superset_id (int)"
        )
    ),
) -> ActionResult:
    """Update an existing workout."""
    payload = {
        "workout": {
            "title": title,
            "description": description,
            "start_time": start_time,
            "end_time": end_time,
            "exercises": _build_exercise_payload(exercises),
        }
    }
    try:
        await hevy_client.put(f"/workouts/{workout_id}", json=payload)
        return ActionResult(success=True, message=f"Workout {workout_id} updated")
    except Exception as exc:
        return ActionResult(success=False, message=str(exc))


@mcp.tool()
async def create_routine(
    title: str = Field(description="Title for the routine"),
    folder_id: int | None = Field(default=None, description="Optional folder ID"),
    notes: str = Field(default="", description="Optional routine-level notes/description"),
    exercises: list[dict] = Field(
        description=(
            "List of exercises. Each dict needs: exercise_template_id (str), "
            "sets (list of dicts with type, weight_kg, reps, etc.), "
            "optional: notes (str), superset_id (int)"
        )
    ),
) -> ActionResult:
    """Create a new routine."""
    payload = {
        "routine": {
            "title": title,
            "folder_id": folder_id,
            "notes": notes or " ",
            "exercises": _build_exercise_payload(exercises, for_routine=True),
        }
    }
    try:
        data = await hevy_client.post("/routines", json=payload)
        routine = data.get("routine", data)
        if isinstance(routine, list):
            routine = routine[0] if routine else {}
        routine_id = routine.get("id", "unknown") if isinstance(routine, dict) else "unknown"
        return ActionResult(success=True, message=f"Routine created: {routine_id}")
    except httpx.HTTPStatusError as exc:
        body = exc.response.text if exc.response is not None else ""
        return ActionResult(success=False, message=f"{exc} | Hevy says: {body}")
    except Exception as exc:
        return ActionResult(success=False, message=str(exc))


@mcp.tool()
async def update_routine(
    routine_id: str = Field(description="ID of the routine to update"),
    title: str = Field(description="Updated title"),
    folder_id: int | None = Field(default=None, description="Optional folder ID"),
    notes: str = Field(default="", description="Optional routine-level notes/description"),
    exercises: list[dict] = Field(
        description=(
            "Updated list of exercises. Each dict needs: exercise_template_id (str), "
            "sets (list of dicts with type, weight_kg, reps, etc.), "
            "optional: notes (str), superset_id (int)"
        )
    ),
) -> ActionResult:
    """Update an existing routine."""
    payload = {
        "routine": {
            "title": title,
            "notes": notes or " ",
            "exercises": _build_exercise_payload(exercises, for_routine=True),
        }
    }
    try:
        await hevy_client.put(f"/routines/{routine_id}", json=payload)
        return ActionResult(success=True, message=f"Routine {routine_id} updated")
    except httpx.HTTPStatusError as exc:
        body = exc.response.text if exc.response is not None else ""
        return ActionResult(success=False, message=f"{exc} | Hevy says: {body}")
    except Exception as exc:
        return ActionResult(success=False, message=str(exc))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main():
    load_dotenv()
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
