from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Optional
from memory.fractal_memory import add_node, list_nodes, search_nodes, link_nodes

router = APIRouter(prefix="/memory", tags=["fractal-memory"])


class AddRequest(BaseModel):
    content: str
    tags: List[str] = Field(default=[])
    emotion: str = Field(default="neutral")
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = Field(default="manual")


class SearchRequest(BaseModel):
    query: str


class LinkRequest(BaseModel):
    id_from: str
    id_to: str


@router.post("/add")
def memory_add(req: AddRequest):
    node = add_node(
        content=req.content,
        tags=req.tags,
        emotion=req.emotion,
        importance=req.importance,
        source=req.source,
    )
    return {"status": "ok", "node": node}


@router.get("/list")
def memory_list():
    return {"status": "ok", "nodes": list_nodes()}


@router.post("/search")
def memory_search(req: SearchRequest):
    results = search_nodes(req.query)
    return {"status": "ok", "count": len(results), "results": results}


@router.post("/link")
def memory_link(req: LinkRequest):
    result = link_nodes(req.id_from, req.id_to)
    if "error" in result:
        return {"status": "error", "detail": result["error"]}
    return {"status": "ok", "node": result}

