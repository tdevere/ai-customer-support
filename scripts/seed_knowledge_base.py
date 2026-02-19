"""
Seed the Azure AI Search knowledge base with support articles.

Usage
-----
    python scripts/seed_knowledge_base.py [--wipe]

Options
-------
    --wipe      Drop and recreate the index before uploading documents.
                Useful when the index schema changes.

Prerequisites
-------------
    AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_KEY must be set (or use .env).
    AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be set for embeddings.
"""

import argparse
import os
import sys

# Make sure project root is on the path when running from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
)

from shared.config import settings
from shared.rag import rag

# ---------------------------------------------------------------------------
# Index schema
# ---------------------------------------------------------------------------

INDEX_NAME = settings.azure_search_index
VECTOR_DIM = 1536  # text-embedding-ada-002


def _get_index_client() -> SearchIndexClient:
    return SearchIndexClient(
        endpoint=settings.azure_search_endpoint,
        credential=AzureKeyCredential(settings.azure_search_key),
    )


def _build_index() -> SearchIndex:
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
        profiles=[
            VectorSearchProfile(
                name="hnsw-profile", algorithm_configuration_name="hnsw"
            )
        ],
    )

    fields = [
        SimpleField(
            name="id", type=SearchFieldDataType.String, key=True, filterable=True
        ),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(
            name="topic",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SimpleField(name="url", type=SearchFieldDataType.String),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=VECTOR_DIM,
            vector_search_profile_name="hnsw-profile",
        ),
    ]

    return SearchIndex(name=INDEX_NAME, fields=fields, vector_search=vector_search)


def ensure_index(wipe: bool = False) -> None:
    client = _get_index_client()
    existing = [idx.name for idx in client.list_indexes()]

    if wipe and INDEX_NAME in existing:
        print(f"  Deleting existing index '{INDEX_NAME}'…")
        client.delete_index(INDEX_NAME)
        existing = []

    if INDEX_NAME not in existing:
        print(f"  Creating index '{INDEX_NAME}'…")
        client.create_index(_build_index())
    else:
        print(f"  Index '{INDEX_NAME}' already exists – skipping creation.")


# ---------------------------------------------------------------------------
# Sample knowledge-base articles
# ---------------------------------------------------------------------------

ARTICLES = [
    # ---- Billing ----
    {
        "title": "How to Read Your Invoice",
        "topic": "billing",
        "url": "https://support.example.com/billing/read-invoice",
        "content": (
            "Your monthly invoice lists all charges for the current billing period. "
            "The 'Subscription' line shows your base plan cost. "
            "'Add-ons' reflect any optional features enabled during the month. "
            "'Usage charges' apply if you exceeded your plan limits. "
            "Taxes are calculated based on your billing address. "
            "You can download a PDF copy from Settings > Billing > Invoice History."
        ),
    },
    {
        "title": "Understanding Subscription Plans",
        "topic": "billing",
        "url": "https://support.example.com/billing/subscription-plans",
        "content": (
            "We offer three plans: Starter ($9/mo), Professional ($49/mo), and Enterprise (custom). "
            "Starter includes up to 1,000 operations per month. "
            "Professional includes 25,000 operations and priority email support. "
            "Enterprise includes unlimited operations, SLA, and dedicated support. "
            "All plans are billed monthly or annually (10% discount for annual). "
            "You can upgrade at any time; proration is applied to your next invoice."
        ),
    },
    {
        "title": "How to Cancel Your Subscription",
        "topic": "billing",
        "url": "https://support.example.com/billing/cancel-subscription",
        "content": (
            "To cancel, go to Settings > Billing > Cancel Plan. "
            "Cancellations take effect at the end of the current billing period. "
            "You will not be charged again after cancellation. "
            "Data is retained for 30 days post-cancellation, then permanently deleted. "
            "If you cancel by mistake, you can reactivate any time before the period ends. "
            "Annual plan refunds are available within 14 days of renewal."
        ),
    },
    {
        "title": "Payment Methods and Failed Payments",
        "topic": "billing",
        "url": "https://support.example.com/billing/payment-methods",
        "content": (
            "We accept Visa, Mastercard, American Express, and PayPal. "
            "To update your payment method go to Settings > Billing > Payment Method. "
            "If a payment fails, we retry three times over 7 days. "
            "You will receive an email notification for each failed attempt. "
            "Your account is suspended (not deleted) after 3 failures. "
            "Reactivate by updating your payment method and paying the outstanding balance."
        ),
    },
    # ---- Returns ----
    {
        "title": "Return Policy Overview",
        "topic": "returns",
        "url": "https://support.example.com/returns/policy",
        "content": (
            "We accept returns within 30 days of the delivery date for most items. "
            "Items must be unused, in original packaging, with tags attached. "
            "Digital downloads and customised products are non-returnable. "
            "Defective items can be returned at any time within the warranty period (1 year). "
            "To start a return, go to Orders > Select Order > Request Return. "
            "A prepaid return shipping label will be emailed within 1 business day."
        ),
    },
    {
        "title": "How to Track Your Refund",
        "topic": "returns",
        "url": "https://support.example.com/returns/track-refund",
        "content": (
            "Refunds are processed within 5-7 business days once we receive the returned item. "
            "You will receive a confirmation email when the refund is initiated. "
            "Bank transfers may take an additional 3-5 business days to appear. "
            "Credit card refunds appear on your next statement. "
            "PayPal refunds are instant once processed on our end. "
            "If you haven't received your refund after 10 business days, contact support."
        ),
    },
    {
        "title": "Exchanging an Item",
        "topic": "returns",
        "url": "https://support.example.com/returns/exchanges",
        "content": (
            "Exchanges are available for different sizes or colours of the same product. "
            "To request an exchange, follow the returns process and select 'Exchange' instead of 'Refund'. "
            "Specify the replacement item in the comments. "
            "Exchanges are subject to stock availability. "
            "If the replacement is out of stock, a full refund will be issued. "
            "Exchanges ship free of charge."
        ),
    },
    {
        "title": "Damaged or Incorrect Items",
        "topic": "returns",
        "url": "https://support.example.com/returns/damaged-items",
        "content": (
            "If you received a damaged or incorrect item, contact us within 7 days of delivery. "
            "Attach photos of the damage or incorrect item to your support ticket. "
            "We will ship a replacement at no cost via express shipping. "
            "You do not need to return the damaged item in most cases. "
            "For high-value items, we may request the item be returned before shipping a replacement. "
            "All replacements are shipped within 1-2 business days of approval."
        ),
    },
    # ---- Technical ----
    {
        "title": "Common Login Issues and Fixes",
        "topic": "technical",
        "url": "https://support.example.com/technical/login-issues",
        "content": (
            "If you cannot log in, first try resetting your password via 'Forgot Password'. "
            "Check that Caps Lock is off and you are using the correct email address. "
            "Clear your browser cache and cookies, then try again. "
            "If using SSO, confirm your organisation's identity provider is reachable. "
            "Error 401 means invalid credentials; error 403 means your account is suspended. "
            "For persistent issues, try a different browser or incognito mode."
        ),
    },
    {
        "title": "API Rate Limits and Error 429",
        "topic": "technical",
        "url": "https://support.example.com/technical/rate-limits",
        "content": (
            "Our API enforces rate limits to ensure fair usage: 100 requests/minute on Starter, "
            "1000 requests/minute on Professional, and custom limits on Enterprise. "
            "When you exceed the limit you receive HTTP 429 (Too Many Requests). "
            "The response includes a 'Retry-After' header indicating seconds until the limit resets. "
            "Implement exponential backoff in your client to handle 429 gracefully. "
            "Rate limits are per API key, not per IP address."
        ),
    },
    {
        "title": "Webhook Configuration and Troubleshooting",
        "topic": "technical",
        "url": "https://support.example.com/technical/webhooks",
        "content": (
            "Webhooks deliver real-time event notifications to your endpoint via HTTP POST. "
            "Configure endpoints in Settings > Developer > Webhooks. "
            "Each event payload is signed using HMAC-SHA256 with your webhook secret. "
            "Verify the X-Hub-Signature-256 header on every incoming request. "
            "We retry delivery up to 5 times with exponential backoff on non-2xx responses. "
            "View delivery history and replay events from the Webhooks dashboard."
        ),
    },
    {
        "title": "Data Export and GDPR Requests",
        "topic": "technical",
        "url": "https://support.example.com/technical/data-export",
        "content": (
            "You can export all your account data from Settings > Privacy > Export Data. "
            "The export includes account details, usage history, and all stored content. "
            "Export files are provided in JSON format and emailed within 24 hours. "
            "For GDPR deletion requests, go to Settings > Privacy > Delete Account. "
            "Deletion is permanent and irreversible; all data is removed within 30 days. "
            "We retain anonymised usage statistics for up to 2 years for analytics."
        ),
    },
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the AAN support knowledge base.")
    parser.add_argument(
        "--wipe", action="store_true", help="Drop and recreate the index first."
    )
    args = parser.parse_args()

    if not settings.azure_search_endpoint or not settings.azure_search_key:
        print(
            "ERROR: AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_KEY must be set.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
        print(
            "ERROR: AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be set.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Target index : {INDEX_NAME}")
    print(f"Search       : {settings.azure_search_endpoint}")
    print()

    print("Step 1: Ensuring index exists…")
    ensure_index(wipe=args.wipe)
    print()

    print(f"Step 2: Uploading {len(ARTICLES)} articles…")
    for i, article in enumerate(ARTICLES, 1):
        try:
            doc_id = rag.add_document(
                content=article["content"],
                title=article["title"],
                topic=article["topic"],
                url=article.get("url"),
            )
            print(f"  [{i:02d}/{len(ARTICLES)}] ✓  {article['title']}  (id={doc_id})")
        except Exception as exc:
            print(
                f"  [{i:02d}/{len(ARTICLES)}] ✗  {article['title']}: {exc}",
                file=sys.stderr,
            )

    print()
    print("Done.")


if __name__ == "__main__":
    main()
