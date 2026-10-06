"""TheParkingAnalysts brand: the mark, the favicon and the wordmark, in one place.

The mark is the familiar blue parking sign -- a white P on a rounded square -- with a small
rising bar chart in the corner for the analysis. The wordmark sets the name in the site's
display face, Barlow Semi Condensed: "The" muted, "Parking" bold, "Analysts" in the accent
colour. The inline mark takes its colour from CSS (currentColor), so it follows light and dark
themes; the favicon has the colour fixed because it is shown outside the page.
"""

NAME = "TheParkingAnalysts"
DOMAIN = "theparkinganalysts.com"

_GLYPH = ('<path d="M10 25.5V7.5h6.6a5.4 5.4 0 0 1 0 10.8H10" fill="none" stroke="#fff" stroke-width="3.6" stroke-linejoin="round"/>'
          '<g fill="#fff" opacity=".85"><rect x="20.4" y="22.6" width="2.5" height="2.9" rx=".5"/>'
          '<rect x="23.9" y="20.4" width="2.5" height="5.1" rx=".5"/><rect x="27.4" y="17.6" width="2.5" height="7.9" rx=".5"/></g>')

MARK_SVG = f'<svg class="wm-mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false"><rect width="32" height="32" rx="7" fill="currentColor"/>{_GLYPH}</svg>'

FAVICON_SVG = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#1d4f9c"/>{_GLYPH}</svg>'

WORDMARK_TEXT = '<span class="wm-text"><span class="wm-the">The</span><span class="wm-p">Parking</span><span class="wm-a">Analysts</span></span>'

# Styles for the wordmark; uses the page's own tokens (--ink, --ink-3, --accent, --font-display).
WORDMARK_CSS = (".wm{display:inline-flex;align-items:center;gap:.5em;text-decoration:none;color:var(--ink);"
                "font:600 1.15rem/1 var(--font-display);letter-spacing:-.01em;white-space:nowrap}"
                ".wm .wm-mark{width:1.55em;height:1.55em;flex:none;color:var(--accent)}"
                ".wm .wm-the{color:var(--ink-3);font-weight:500}.wm .wm-p{font-weight:700}.wm .wm-a{color:var(--accent);font-weight:600}")


def wordmark(href: str = "/", cls: str = "wm") -> str:
    return f'<a class="{cls}" href="{href}" aria-label="{NAME}, home">{MARK_SVG}{WORDMARK_TEXT}</a>'
