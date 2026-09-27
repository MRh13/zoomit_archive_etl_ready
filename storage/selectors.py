"""CSS selectors shared by every Zoomit-family site.

Filmzi, Zoomit, Zoomg, Pedal, Kojaro and Zoomon all render the same
styled-components markup. Hashed suffixes such as ``lmWlKg`` change per
build, so selectors below match stable prefixes and structural hooks.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Archive list (anchor_list)
# ---------------------------------------------------------------------------

# The vertical stack that holds one card per article on /archive.
ARCHIVE_ARTICLE_LIST_SELECTOR = "div.flex.flex-col.px-4.gap-4"

# Direct article cards inside that stack.
ARCHIVE_ARTICLE_CARD_SELECTOR = ":scope > div > a[href]"

# Fallback when the stack wrapper is missing but cards are still present.
ARCHIVE_ARTICLE_CARD_FALLBACK_SELECTOR = (
    "a.cursor-pointer.block.w-full[href]"
)

ARCHIVE_CARD_DESCRIPTION_SELECTOR = "p"
ARCHIVE_CARD_TITLE_SELECTOR = (
    "span.typography__StyledDynamicTypographyComponent-sc-4caf251e-0"
)
ARCHIVE_CARD_IMAGE_SELECTOR = "img[alt]"
# Nested ``span.fa > span.fa`` duplicates the same timestamp; skip inner ones.
ARCHIVE_CARD_META_SELECTOR = "span.fa:not(span.fa span.fa)"

# Wait target used by Selenium before parsing an archive page.
ARCHIVE_READY_SELECTOR = "div.flex.flex-col.px-4.gap-4 a[href]"

# ``/{category}/{numericId}-{english-slug}/`` on any of the family domains.
ARTICLE_PATH_RE = re.compile(
    r"^(?:https?://[^/]+)?/([^/]+)/(\d+)-([^/]+)/?$"
)

# ---------------------------------------------------------------------------
# Article page
# ---------------------------------------------------------------------------

ARTICLE_ROOT_SELECTOR = "article"
ARTICLE_TITLE_SELECTOR = "h1.typography__StyledDynamicTypographyComponent-sc-4caf251e-0"
ARTICLE_LEAD_SELECTOR = "p.article-lead"
ARTICLE_AUTHOR_SELECTOR = "span.flJYlr"
ARTICLE_AUTHOR_LINK_SELECTOR = "a[href*='/author/']"
ARTICLE_PUBLISHED_TIME_SELECTOR = "time"
ARTICLE_TIME_META_SELECTOR = "span.fZFZNx.fa"
ARTICLE_BREADCRUMB_SELECTOR = "nav ol a"
ARTICLE_PARAGRAPH_SELECTOR = (
    "p.article-lead, [class*='ParagraphElement__ParagraphBase']"
)
ARTICLE_COVER_SELECTOR = "[class*='ArticleCover'] img"
ARTICLE_FIGURE_IMAGE_SELECTOR = "article figure img, figure img"
ARTICLE_READY_SELECTOR = "h1"

TYPOGRAPHY_CLASS_PREFIX = (
    "typography__StyledDynamicTypographyComponent-sc-4caf251e-0"
)
FLEX_CLASS_PREFIX = "flex__Flex-sc-96510e75-0"
INNER_ARTICLE_CLASS_PREFIX = "BlockContainer__InnerArticleContainer"
