"""
Data models for the competitive product knowledge base.

The schema is intentionally dynamic: dimensions are discovered by the
expert agent from the source documents rather than hard-coded.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    """Reference to a location in a source document."""

    doc_id: str = Field(description="Unique identifier of the source document")
    file_name: str = Field(description="Name of the source file")
    page_or_section: Optional[str] = Field(
        default=None, description="Page number, section heading, or paragraph hint"
    )
    quote: Optional[str] = Field(
        default=None, description="Relevant verbatim quote from the document"
    )
    location_hint: Optional[str] = Field(
        default=None, description="Additional hint for locating the content"
    )


class FactItem(BaseModel):
    """A single fact extracted from source documents."""

    item_id: str = Field(description="Unique identifier for this fact")
    content: str = Field(description="Summarized factual content")
    source_refs: list[SourceRef] = Field(
        default_factory=list, description="Source references supporting this fact"
    )
    status: str = Field(
        default="confirmed",
        description="One of: confirmed, pending_verification, external_supplement, not_mentioned, conflict",
    )
    confidence: str = Field(
        default="high",
        description="Confidence level: high, medium, or low",
    )
    added_by: str = Field(
        default="expert_agent",
        description="Agent or human that added this item",
    )
    added_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp when this item was added",
    )
    note: Optional[str] = Field(
        default=None,
        description="Optional note, e.g., reason for low confidence or conflict context",
    )


class Dimension(BaseModel):
    """A knowledge dimension discovered dynamically from source documents."""

    dimension_id: str = Field(description="Unique identifier for this dimension")
    dimension_name: str = Field(
        description="Human-readable name of the dimension, discovered from the text"
    )
    items: list[FactItem] = Field(
        default_factory=list, description="Facts belonging to this dimension"
    )


class ProductProfile(BaseModel):
    """Complete profile of a single competitive product."""

    product_id: str = Field(description="Unique identifier for this product")
    product_name: str = Field(description="Name of the product")
    company_name: Optional[str] = Field(
        default=None, description="Company that owns the product"
    )
    summary: Optional[FactItem] = Field(
        default=None, description="High-level summary of the product"
    )
    dimensions: list[Dimension] = Field(
        default_factory=list,
        description="Dynamically discovered dimensions for this product",
    )
    is_own_product: bool = Field(
        default=False,
        description="Whether this product is our own product being analyzed",
    )


class SourceDocument(BaseModel):
    """Metadata about a source document."""

    doc_id: str = Field(description="Unique identifier")
    file_name: str = Field(description="Original file name")
    file_type: str = Field(description="File extension or MIME type hint")
    uploaded_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp when the document was processed",
    )


class ConflictRecord(BaseModel):
    """Record of a factual conflict that requires human resolution."""

    conflict_id: str = Field(description="Unique identifier")
    dimension: str = Field(description="Dimension where the conflict occurred")
    product_id: str = Field(description="Product involved")
    conflicting_items: list[FactItem] = Field(
        description="Items that contradict each other"
    )
    resolution: Optional[dict[str, Any]] = Field(
        default=None,
        description="Human expert resolution: decision, chosen item, resolver, timestamp",
    )


class ComparisonDimension(BaseModel):
    """A normalized dimension used to align facts across products."""

    dimension_id: str = Field(description="Unique identifier for the canonical dimension")
    dimension_name: str = Field(description="Human-readable canonical dimension name")
    description: Optional[str] = Field(
        default=None, description="Short description of what this dimension covers"
    )
    original_dimension_names: list[str] = Field(
        default_factory=list,
        description="Raw dimension names from product profiles mapped to this canonical dimension",
    )


class ComparisonCell(BaseModel):
    """One cell in the comparison matrix: a product on a canonical dimension."""

    cell_id: str = Field(description="Unique identifier for this cell")
    dimension_id: str = Field(description="Canonical dimension identifier")
    product_id: str = Field(description="Product identifier")
    summary: str = Field(description="Concise synthesis of this product on this dimension")
    fact_ids: list[str] = Field(
        default_factory=list, description="References to FactItem.item_id"
    )
    status_summary: str = Field(
        default="", description="E.g. 'confirmed x3, external_supplement x1'"
    )
    confidence: str = Field(
        default="medium", description="Aggregate confidence: high, medium, low"
    )


class ComparisonMatrix(BaseModel):
    """Aligned comparison matrix across products and canonical dimensions."""

    dimensions: list[ComparisonDimension] = Field(description="Canonical comparison dimensions")
    cells: list[ComparisonCell] = Field(description="Matrix cells")
    product_ids: list[str] = Field(description="Product identifiers included in the matrix")


class ScoreCriterion(BaseModel):
    """A scoring criterion with weight for quantitative comparison."""

    criterion_id: str = Field(description="Unique identifier for the criterion")
    name: str = Field(description="Human-readable criterion name")
    description: str = Field(description="What this criterion measures")
    weight: float = Field(
        ge=0.0, le=1.0, description="Weight in the total score (0-1)"
    )


class CriterionScore(BaseModel):
    """A product's score on a single criterion."""

    criterion_id: str = Field(description="Criterion identifier")
    score: float = Field(ge=1.0, le=10.0, description="Score from 1 to 10")
    rationale: str = Field(description="Why this score was given")
    fact_ids: list[str] = Field(
        default_factory=list, description="Supporting fact item_ids"
    )


class ProductScore(BaseModel):
    """Quantitative score and ranking for a product."""

    product_id: str = Field(description="Product identifier")
    product_name: str = Field(description="Product name")
    total_score: float = Field(description="Weighted total score")
    rank: int = Field(description="Rank among all products, 1 = highest")
    criterion_scores: list[CriterionScore] = Field(
        description="Per-criterion scores and rationales"
    )
    overall_rationale: str = Field(
        description="Overall assessment of this product's competitive position"
    )


class SwotItem(BaseModel):
    """One item in a SWOT analysis."""

    item_id: str = Field(description="Unique identifier")
    category: str = Field(
        description="One of: strength, weakness, opportunity, threat"
    )
    content: str = Field(description="SWOT statement")
    related_product_ids: list[str] = Field(
        default_factory=list,
        description="Products this item relates to",
    )
    dimension_id: Optional[str] = Field(
        default=None, description="Related canonical dimension identifier"
    )
    fact_ids: list[str] = Field(
        default_factory=list, description="Supporting fact item_ids"
    )


class GapItem(BaseModel):
    """A competitive gap where one product trails others."""

    item_id: str = Field(description="Unique identifier")
    dimension_id: Optional[str] = Field(
        default=None, description="Related canonical dimension identifier"
    )
    description: str = Field(description="Description of the gap")
    impact: str = Field(description="high, medium, or low")
    own_product_id: Optional[str] = Field(
        default=None, description="Own product that has the gap"
    )
    compared_to_product_ids: list[str] = Field(
        default_factory=list,
        description="Competitors that outperform in this gap",
    )
    fact_ids: list[str] = Field(
        default_factory=list, description="Supporting fact item_ids"
    )


class RecommendationItem(BaseModel):
    """A prioritized strategic recommendation."""

    item_id: str = Field(description="Unique identifier")
    priority: str = Field(description="high, medium, or low")
    title: str = Field(description="Short recommendation title")
    description: str = Field(description="Detailed recommendation")
    rationale: str = Field(description="Why this recommendation matters")
    related_gap_ids: list[str] = Field(
        default_factory=list, description="Related gap item_ids"
    )
    related_product_ids: list[str] = Field(
        default_factory=list, description="Products this recommendation concerns"
    )
    dimension_id: Optional[str] = Field(
        default=None, description="Related canonical dimension identifier"
    )
    expected_impact: Optional[str] = Field(
        default=None, description="Expected business or competitive impact"
    )


class AnalysisReport(BaseModel):
    """Structured competitive analysis report produced by AnalysisAgent."""

    report_id: str = Field(description="Unique identifier for this report")
    created_at: str = Field(description="ISO timestamp of creation")
    own_product_id: Optional[str] = Field(
        default=None, description="ID of the product marked as our own"
    )
    comparison_matrix: ComparisonMatrix = Field(description="Aligned fact matrix")
    product_scores: list[ProductScore] = Field(description="Quantitative scoring and ranking")
    swot: list[SwotItem] = Field(description="SWOT analysis items")
    gaps: list[GapItem] = Field(description="Competitive gap items")
    recommendations: list[RecommendationItem] = Field(description="Prioritized recommendations")


class ProductPosition(BaseModel):
    """Narrative positioning summary for one product in the final report."""

    product_id: str = Field(description="Product identifier")
    product_name: str = Field(description="Product name")
    positioning: str = Field(description="One-paragraph market positioning")
    key_strengths: list[str] = Field(default_factory=list)
    key_weaknesses: list[str] = Field(default_factory=list)


class KeyFinding(BaseModel):
    """A key finding in the final report."""

    finding_id: str = Field(description="Unique identifier")
    title: str = Field(description="Short finding title")
    detail: str = Field(description="Detailed explanation")
    evidence: list[str] = Field(default_factory=list, description="Supporting fact summaries")
    related_product_ids: list[str] = Field(default_factory=list)
    related_dimension_ids: list[str] = Field(default_factory=list)


class ReportOutput(BaseModel):
    """Structured competitive analysis report produced by ReportAgent."""

    report_id: str = Field(description="Unique identifier for this report")
    created_at: str = Field(description="ISO timestamp of creation")
    title: str = Field(description="Report title")
    executive_summary: str = Field(description="High-level executive summary")
    market_overview: str = Field(description="Market and competitive landscape overview")
    product_positions: list[ProductPosition] = Field(description="Per-product positioning")
    key_findings: list[KeyFinding] = Field(description="Top findings")
    swot_summary: str = Field(description="SWOT synthesis")
    gap_summary: str = Field(description="Gap analysis synthesis")
    strategic_recommendations: list[str] = Field(description="Prioritized strategic recommendations")
    risk_and_conflicts: str = Field(description="Risks, conflicts and limitations")
    next_steps: list[str] = Field(description="Suggested next actions")
    full_markdown: str = Field(description="Complete Markdown report text")


class KnowledgeBase(BaseModel):
    """Top-level knowledge base container."""

    knowledge_base_id: str = Field(description="Unique identifier for the KB")
    created_at: str = Field(description="ISO timestamp of creation")
    updated_at: str = Field(description="ISO timestamp of last update")
    source_documents: list[SourceDocument] = Field(
        default_factory=list, description="Documents used to build this KB"
    )
    analyzed_products: list[str] = Field(
        default_factory=list, description="Product names included in this KB"
    )
    products: list[ProductProfile] = Field(
        default_factory=list, description="Product profiles"
    )
    conflicts_and_clarifications: list[ConflictRecord] = Field(
        default_factory=list, description="Unresolved or resolved conflicts"
    )
    own_product_id: Optional[str] = Field(
        default=None, description="ID of the product marked as our own"
    )
    analysis: Optional[AnalysisReport] = Field(
        default=None, description="Competitive analysis output produced by AnalysisAgent"
    )
    report: Optional[ReportOutput] = Field(
        default=None, description="Final structured report produced by ReportAgent"
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class SearchResult(BaseModel):
    """A single web search result with extracted facts."""

    result_id: str = Field(description="Unique identifier for this result")
    query: str = Field(description="Search query that produced this result")
    product_name: str = Field(
        description="Product this result is associated with"
    )
    title: str = Field(description="Page title")
    url: str = Field(description="Page URL")
    snippet: str = Field(default="", description="Search engine snippet")
    page_content: str = Field(default="", description="Fetched page plain text")
    extracted_facts: list[FactItem] = Field(
        default_factory=list, description="Facts extracted from the page"
    )
    searched_at: str = Field(description="ISO timestamp of the search")
