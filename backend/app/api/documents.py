"""Documents and cited passages: GET /api/v1/documents, /{source_ref}, /{id}/chunks/{chunk_id}.

Every read runs inside `guarded` (app.api.guard): the policy decides first, then the policy row
filter and RLS apply together inside the query, and the decide event plus a query event with
the row count are audited on the way out. The detail routes answer 404 for anything not
visible — including callers whose action was denied — so a probe can never distinguish a
restricted document from a non-existent one.
"""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import ConnDep, CurrentContext
from app.api.guard import guarded
from app.knowledge import passages

router = APIRouter(prefix="/api/v1/documents", tags=["data"])


class DocumentOut(BaseModel):
    source_ref: str
    title: str
    classification_code: str


class PassageOut(BaseModel):
    chunk_id: str
    document_id: str
    document_ref: str
    document_title: str
    text: str
    page: int | None
    section: str | None
    classification_code: str
    compartments: list[str]


@router.get("", response_model=list[DocumentOut])
def list_documents(ctx: CurrentContext, conn: ConnDep) -> list[DocumentOut]:
    with guarded(ctx, conn, "read", "document") as scope:
        documents = passages.list_documents(scope)
        scope.read("document", len(documents))
    return [DocumentOut(**asdict(document)) for document in documents]


@router.get("/{source_ref}", response_model=DocumentOut)
def get_document(source_ref: str, ctx: CurrentContext, conn: ConnDep) -> DocumentOut:
    # 404 — not 403 — whenever the row is not visible, including a denied
    # action: never confirm that a restricted document exists.
    with guarded(ctx, conn, "read", "document", on_deny="not_found") as scope:
        found = passages.list_documents(scope, source_ref)
        scope.read("document", len(found))
    if not found:
        raise HTTPException(status_code=404, detail="not found")
    return DocumentOut(**asdict(found[0]))


@router.get("/{document_id}/chunks/{chunk_id}", response_model=PassageOut)
def get_document_chunk(
    document_id: str, chunk_id: str, ctx: CurrentContext, conn: ConnDep
) -> PassageOut:
    """Cited-passage viewer: open the exact page/section a citation points at.

    Same authorization order and the same policy row filter + RLS as every
    other classified read. Anything not visible — including a caller whose
    action was denied, or a malformed id — answers 404 rather than 403, so a
    probe can never confirm that a restricted passage exists. `document_id`
    accepts the user-facing source_ref a citation carries, or the document's
    internal uuid.
    """
    with guarded(ctx, conn, "read", "chunk", on_deny="not_found") as scope:
        passage = passages.visible_passage(scope, document_id, chunk_id)
        scope.read("chunk", 0 if passage is None else 1)
    if passage is None:
        raise HTTPException(status_code=404, detail="not found")
    return PassageOut(**asdict(passage))
