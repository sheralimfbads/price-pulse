
import logging
from datetime import date
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import queries
from app.db import get_connection
from app.schemas import (
    HealthLive,
    HealthReady,
    LatestMovers,
    Mover,
    Overview,
    PaginatedPrices,
    PaginatedProducts,
    PriceObservation,
    Product,
)


logger = logging.getLogger("pricepulse.api")

APP_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="PricePulse API",
    version="1.0.0",
    description=(
        "Read-only API for official monthly average prices in Uzbekistan. "
        "Analytical prices come from PostgreSQL views; this service does "
        "not ingest or recompute source data."
    ),
)

app.mount(
    "/static",
    StaticFiles(directory=APP_DIR / "static"),
    name="static",
)
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50
MOVER_LIMIT_MAX = 20


def parse_month(value: str | None, field_name: str) -> date | None:
    if value is None or value == "":
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} must be an ISO date (YYYY-MM-DD).",
        ) from exc
    if parsed.day != 1:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} must be the first day of a month.",
        )
    return parsed


def database_http_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="The analytics database is unavailable. Try again later.",
    )


@app.exception_handler(psycopg.Error)
async def handle_database_error(request: Request, exc: psycopg.Error):
    logger.exception("Database error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "The analytics database is unavailable. Try again later."
        },
    )


@app.get("/health/live", response_model=HealthLive, tags=["health"])
def health_live() -> HealthLive:
    return HealthLive()


@app.get("/health/ready", response_model=HealthReady, tags=["health"])
def health_ready(conn=Depends(get_connection)) -> HealthReady:
    try:
        with conn.cursor() as cur:
            cur.execute(queries.READY_SQL)
            row = cur.fetchone()
    except psycopg.Error:
        logger.exception("Readiness check failed")
        raise database_http_error() from None

    if not row or not row["ready"]:
        raise HTTPException(
            status_code=503,
            detail="Required analytics objects are not available.",
        )
    return HealthReady()


@app.get("/health", response_model=HealthReady, tags=["health"], include_in_schema=False)
def health_alias(conn=Depends(get_connection)) -> HealthReady:
    return health_ready(conn=conn)


@app.get("/api/v1/overview", response_model=Overview, tags=["analytics"])
def get_overview(conn=Depends(get_connection)) -> Overview:
    with conn.cursor() as cur:
        cur.execute(queries.OVERVIEW_SQL)
        row = cur.fetchone()
    return Overview.model_validate(row)


@app.get("/api/v1/products", response_model=PaginatedProducts, tags=["products"])
def list_products(
    q: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    conn=Depends(get_connection),
) -> PaginatedProducts:
    search = q.strip() if q and q.strip() else None
    params = {
        "search": search,
        "search_like": f"%{search}%" if search else None,
        "limit": limit,
        "offset": offset,
    }
    with conn.cursor() as cur:
        cur.execute(queries.PRODUCTS_COUNT_SQL, params)
        total = int(cur.fetchone()["total"])
        cur.execute(queries.PRODUCTS_SQL, params)
        items = [Product.model_validate(row) for row in cur.fetchall()]
    return PaginatedProducts(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get(
    "/api/v1/products/{product_code}/prices",
    response_model=PaginatedPrices,
    tags=["products"],
)
def get_product_prices(
    product_code: str,
    from_month: str | None = Query(default=None),
    to_month: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    conn=Depends(get_connection),
) -> PaginatedPrices:
    start = parse_month(from_month, "from_month")
    end = parse_month(to_month, "to_month")
    if start and end and start > end:
        raise HTTPException(
            status_code=422,
            detail="from_month must be on or before to_month.",
        )

    with conn.cursor() as cur:
        cur.execute(
            queries.PRODUCT_SQL,
            {"product_code": product_code},
        )
        product_row = cur.fetchone()
        if product_row is None:
            raise HTTPException(status_code=404, detail="Product not found.")

        params = {
            "product_code": product_code,
            "from_month": start,
            "to_month": end,
            "limit": limit,
            "offset": offset,
        }
        cur.execute(queries.PRODUCT_PRICES_COUNT_SQL, params)
        total = int(cur.fetchone()["total"])
        cur.execute(queries.PRODUCT_PRICES_SQL, params)
        items = [PriceObservation.model_validate(row) for row in cur.fetchall()]

    return PaginatedPrices(
        product=Product.model_validate(product_row),
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get(
    "/api/v1/analytics/latest-movers",
    response_model=LatestMovers,
    tags=["analytics"],
)
def get_latest_movers(
    limit: int = Query(default=5, ge=1, le=MOVER_LIMIT_MAX),
    conn=Depends(get_connection),
) -> LatestMovers:
    with conn.cursor() as cur:
        cur.execute(queries.LATEST_MONTH_SQL)
        latest_row = cur.fetchone()
        latest_month = latest_row["latest_month"] if latest_row else None
        if latest_month is None:
            return LatestMovers(
                comparison_month=None,
                latest_month=None,
                increases=[],
                decreases=[],
            )

        cur.execute(
            queries.LATEST_MOVERS_SQL,
            {
                "month_start": latest_month,
                "direction": "increase",
                "limit": limit,
            },
        )
        increases = [
            Mover(
                **{k: v for k, v in row.items() if k not in {"increase_rank", "decrease_rank"}},
                rank=int(row["increase_rank"]),
            )
            for row in cur.fetchall()
        ]
        cur.execute(
            queries.LATEST_MOVERS_SQL,
            {
                "month_start": latest_month,
                "direction": "decrease",
                "limit": limit,
            },
        )
        decreases = [
            Mover(
                **{k: v for k, v in row.items() if k not in {"increase_rank", "decrease_rank"}},
                rank=int(row["decrease_rank"]),
            )
            for row in cur.fetchall()
        ]

    comparison_month = None
    if increases:
        comparison_month = increases[0].comparison_month_start
    elif decreases:
        comparison_month = decreases[0].comparison_month_start

    return LatestMovers(
        comparison_month=comparison_month,
        latest_month=latest_month,
        increases=increases,
        decreases=decreases,
    )


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"title": "PricePulse"},
    )
