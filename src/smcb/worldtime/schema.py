"""Strict contracts for temporal edits and model timeline submissions."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorldTimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TimelineSegment(WorldTimeModel):
    video_start_frame: int = Field(ge=0)
    video_end_frame: int = Field(ge=0)
    world_start_time: float = Field(ge=0)
    world_end_time: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_segment(self) -> TimelineSegment:
        if self.video_end_frame < self.video_start_frame:
            raise ValueError("timeline segment ends before it starts")
        if not math.isfinite(self.world_start_time) or not math.isfinite(self.world_end_time):
            raise ValueError("timeline world times must be finite")
        return self


class Timeline(WorldTimeModel):
    schema_version: Literal["0.1"] = "0.1"
    fps: int = Field(gt=0)
    video_frame_count: int = Field(gt=0)
    world_duration: float = Field(gt=0)
    segments: list[TimelineSegment] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_coverage(self) -> Timeline:
        expected_start = 0
        for segment in self.segments:
            if segment.video_start_frame != expected_start:
                raise ValueError("timeline segments must cover video frames contiguously")
            expected_start = segment.video_end_frame + 1
            if max(segment.world_start_time, segment.world_end_time) > self.world_duration + 1e-8:
                raise ValueError("timeline world time exceeds master duration")
        if expected_start != self.video_frame_count:
            raise ValueError("timeline segments do not cover video_frame_count")
        return self


EditKind = Literal["normal", "reverse", "freeze", "replay"]


class EditSpan(WorldTimeModel):
    kind: EditKind
    master_start_frame: int = Field(ge=0)
    frame_count: int = Field(gt=0)
    step: Literal[-1, 0, 1]


class TemporalEditProgram(WorldTimeModel):
    schema_version: Literal["0.1"] = "0.1"
    preset: EditKind
    fps: int = Field(gt=0)
    master_frame_count: int = Field(gt=0)
    spans: list[EditSpan] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_master_indices(self) -> TemporalEditProgram:
        for span in self.spans:
            final_index = span.master_start_frame + span.step * (span.frame_count - 1)
            if not (
                0 <= span.master_start_frame < self.master_frame_count
                and 0 <= final_index < self.master_frame_count
            ):
                raise ValueError("edit span leaves the master frame range")
        if sum(span.frame_count for span in self.spans) != self.master_frame_count:
            raise ValueError("demo edit programs must preserve the 144-frame observation length")
        return self
