"""Pydantic I/O schemas."""
from typing import Dict, Optional
from pydantic import BaseModel


class SourceStat(BaseModel):
    rating: float
    reviews: int


class PlaceBase(BaseModel):
    id: str
    name: str
    cuisine: str
    address: str
    district: Optional[str] = None
    sector: Optional[str] = None
    lat: float
    lng: float


class Verdict(BaseModel):
    verdict: str
    explanation: str
    sources: Dict[str, SourceStat] = {}
    weighted_avg: Optional[float] = None
    total_reviews: int = 0
    mismatch: Optional[float] = None


class VerdictNamed(Verdict):
    name: str


class PlaceCard(PlaceBase):
    verdict: str
    explanation: str
    sources: Dict[str, SourceStat] = {}


class PlaceDetail(PlaceBase):
    verdict: Verdict
