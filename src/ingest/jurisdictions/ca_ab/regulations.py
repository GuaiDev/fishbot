"""Alberta sportfishing regulations — PDF ingestion STUB.

TODO: Implement PDF download and parse.

The Alberta Guide to Sportfishing Regulations is published annually as a PDF.
Find the current year's link at:
  https://mywildalberta.ca/fishing/regulations/

Direct URL pattern (update annually):
  https://mywildalberta.ca/images/GFW/Guide_Sportfishing_Regulations.pdf

Implementation plan (same pattern as MNRF regulations adapter):
  1. Fetch the mywildalberta.ca/fishing page
  2. Extract the PDF link with BeautifulSoup or regex
  3. Download PDF, cache 365 days
  4. Parse with pdfplumber — split by Wildlife Management Zone number
  5. Write to regulation_chunks with jurisdiction='CA-AB', regulation_year=YEAR

Alberta has ~100 Wildlife Management Units (WMUs) in a 2-digit + letter scheme
(e.g. 202, 300A, 512). Use section index as the integer zone field; include
zone_name for the WMU identifier.

Table: regulation_chunks (shared schema)
"""

import logging

logger = logging.getLogger(__name__)


def fetch_regulations() -> list[dict]:
    """Stub — returns empty list with a TODO warning.

    See module docstring for implementation plan.
    TODO: https://mywildalberta.ca/fishing/regulations/
    """
    logger.warning(
        "AB regulations: adapter not yet implemented — returning 0 chunks. "
        "Find the current-year PDF at https://mywildalberta.ca/fishing/regulations/ "
        "and implement using the same pdfplumber pattern as ca_on/regulations.py."
    )
    return []
